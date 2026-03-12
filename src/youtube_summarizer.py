"""YouTube video summarizer: extract subtitles via yt-dlp and summarize with Gemini."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# YouTube URL pattern
YT_URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})'
)

# YouTube feed URL pattern in markdown links
MD_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')


def load_feeds_from_md(md_path: str | Path) -> list[dict]:
    """Load YouTube RSS feed URLs from a markdown file.

    Parses markdown links like [Channel Name](https://www.youtube.com/feeds/videos.xml?channel_id=xxx)

    Returns list of dicts with 'name' and 'feed_url'.
    """
    md_path = Path(md_path)
    if not md_path.exists():
        logger.error("Feed list not found: %s", md_path)
        return []

    feeds = []
    text = md_path.read_text(encoding="utf-8")
    for match in MD_LINK_PATTERN.finditer(text):
        name = match.group(1)
        url = match.group(2)
        if "youtube.com/feeds/" in url:
            feeds.append({"name": name, "feed_url": url})

    logger.info("Loaded %d YouTube feeds from %s", len(feeds), md_path)
    return feeds


def fetch_videos_from_feeds(feeds: list[dict]) -> list[dict]:
    """Fetch video entries from YouTube RSS feeds.

    Returns list of dicts with 'video_id', 'url', 'title', 'channel', 'published'.
    """
    import xml.etree.ElementTree as ET
    import urllib.request

    videos = []
    seen_ids = set()

    for feed in feeds:
        feed_url = feed["feed_url"]
        channel_name = feed["name"]
        logger.info("Fetching feed: %s (%s)", channel_name, feed_url)

        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
        except Exception as e:
            logger.warning("Failed to fetch feed %s: %s", channel_name, e)
            continue

        # YouTube Atom feed namespace
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

        for entry in root.findall("atom:entry", ns):
            video_id_elem = entry.find("yt:videoId", ns)
            if video_id_elem is None:
                continue
            video_id = video_id_elem.text
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)

            title_elem = entry.find("atom:title", ns)
            published_elem = entry.find("atom:published", ns)

            videos.append({
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": title_elem.text if title_elem is not None else "",
                "channel": channel_name,
                "published": published_elem.text if published_elem is not None else "",
            })

    logger.info("Found %d videos from %d feeds", len(videos), len(feeds))
    return videos


def extract_youtube_urls(feed_path: str | Path) -> list[dict]:
    """Extract YouTube URLs from an RSS feed XML file.

    Returns list of dicts with 'video_id', 'url', 'title' (from feed entry).
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(feed_path)
    root = tree.getroot()
    videos = []
    seen_ids = set()

    # Search all text content for YouTube URLs
    for elem in root.iter():
        texts = []
        if elem.text:
            texts.append(elem.text)
        if elem.tail:
            texts.append(elem.tail)
        for attr_val in elem.attrib.values():
            texts.append(attr_val)

        for text in texts:
            for match in YT_URL_PATTERN.finditer(text):
                video_id = match.group(1)
                if video_id not in seen_ids:
                    seen_ids.add(video_id)
                    videos.append({
                        "video_id": video_id,
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                    })

    logger.info("Found %d YouTube videos in feed", len(videos))
    return videos


def get_video_metadata(url: str) -> dict | None:
    """Get video title, channel, duration via yt-dlp --dump-json."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-download", url],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8",
        )
        if result.returncode != 0:
            logger.warning("yt-dlp metadata failed for %s: %s", url, result.stderr[:200])
            return None
        data = json.loads(result.stdout)
        return {
            "title": data.get("title", ""),
            "channel": data.get("channel", data.get("uploader", "")),
            "duration": data.get("duration", 0),
            "upload_date": data.get("upload_date", ""),
            "view_count": data.get("view_count", 0),
            "thumbnail": data.get("thumbnail", ""),
        }
    except Exception as e:
        logger.warning("Failed to get metadata for %s: %s", url, e)
        return None


def get_subtitles(url: str, lang: str = "ja") -> str | None:
    """Download subtitles using yt-dlp. Falls back to auto-generated subs.

    Returns subtitle text or None.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = str(Path(tmpdir) / "sub")

        # Try manual subs first, then auto-generated
        for sub_flag in [["--write-subs"], ["--write-auto-subs"]]:
            result = subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    *sub_flag,
                    "--sub-langs", f"{lang},en",
                    "--sub-format", "vtt",
                    "--skip-download",
                    "-o", out_template,
                    url,
                ],
                capture_output=True, text=True, timeout=60,
                encoding="utf-8",
            )

            # Find downloaded subtitle file
            sub_files = list(Path(tmpdir).glob("*.vtt"))
            if not sub_files:
                sub_files = list(Path(tmpdir).glob("*.srt"))
            if sub_files:
                raw = sub_files[0].read_text(encoding="utf-8", errors="replace")
                cleaned = _clean_subtitles(raw)
                if cleaned.strip():
                    logger.info("Got subtitles for %s (%d chars)", url, len(cleaned))
                    return cleaned

    logger.warning("No subtitles found for %s", url)
    return None


def _clean_subtitles(raw: str) -> str:
    """Remove VTT/SRT timestamps and formatting, deduplicate lines."""
    lines = raw.split("\n")
    cleaned = []
    seen = set()

    for line in lines:
        line = line.strip()
        # Skip VTT header, timestamps, sequence numbers, empty lines
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if re.match(r'^\d+$', line):
            continue
        if re.match(r'\d{2}:\d{2}', line):
            continue
        if line.startswith("NOTE"):
            continue
        # Remove HTML tags
        line = re.sub(r'<[^>]+>', '', line)
        if line and line not in seen:
            seen.add(line)
            cleaned.append(line)

    return "\n".join(cleaned)


SUMMARY_PROMPT = """専門家でもない人でもわかるように、リバースアウトラインを作って平易な言葉でどんなことを伝えたいか要約して。最後に総論も平易な言葉で書いて。字幕が英語でも日本語で書いて。"""


def summarize_transcript(transcript: str, title: str = "") -> str | None:
    """Summarize a video transcript using Gemini 2.5 Flash."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return None

    client = genai.Client(api_key=api_key)

    # Truncate very long transcripts (Gemini context limit)
    max_chars = 30000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n...(以下省略)"

    prompt = f"動画タイトル: {title}\n\n字幕テキスト:\n{transcript}"

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SUMMARY_PROMPT,
                temperature=0.3,
                max_output_tokens=2000,
            ),
        )
        summary = response.text
        logger.info("Generated summary (%d chars)", len(summary))
        return summary
    except Exception as e:
        logger.error("Summarization failed: %s", e)
        return None


def process_videos(videos: list[dict], lang: str = "ja") -> list[dict]:
    """Process a list of videos: get metadata, subtitles, and summaries.

    Args:
        videos: List of dicts with 'video_id' and 'url'.
        lang: Preferred subtitle language.

    Returns:
        List of dicts with added 'title', 'channel', 'summary', etc.
    """
    results = []

    for video in videos:
        url = video["url"]
        logger.info("Processing: %s", url)

        # Get metadata
        meta = get_video_metadata(url)
        if meta:
            video.update(meta)
        else:
            video.setdefault("title", "")
            video.setdefault("channel", "")

        # Get subtitles
        transcript = get_subtitles(url, lang=lang)
        if not transcript:
            logger.warning("Skipping %s (no subtitles)", url)
            video["summary"] = "字幕が取得できませんでした"
            video["has_subtitles"] = False
            results.append(video)
            continue

        video["has_subtitles"] = True

        # Summarize
        summary = summarize_transcript(transcript, title=video.get("title", ""))
        video["summary"] = summary or "要約の生成に失敗しました"
        results.append(video)

    logger.info("Processed %d/%d videos", len(results), len(videos))
    return results
