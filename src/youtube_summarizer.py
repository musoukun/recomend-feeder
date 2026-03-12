"""YouTube video summarizer: YouTube RSS → Gemini direct YouTube URL summarization → Spreadsheet."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# YouTube feed URL pattern in markdown links
MD_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')

# 処理済み動画IDの保存先
PROCESSED_FILE = Path(__file__).parent.parent / "processed_videos.json"


# --- 処理済み動画管理 ---

def load_processed_ids() -> set[str]:
    """Load previously processed video IDs."""
    try:
        if PROCESSED_FILE.exists():
            return set(json.loads(PROCESSED_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return set()


def save_processed_ids(ids: set[str]) -> None:
    """Save processed video IDs."""
    PROCESSED_FILE.write_text(
        json.dumps(sorted(ids), ensure_ascii=False),
        encoding="utf-8",
    )


# --- フィード読み込み ---

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


def fetch_videos_from_feeds(feeds: list[dict], max_per_channel: int = 5) -> list[dict]:
    """Fetch video entries from YouTube RSS feeds.

    Args:
        feeds: List of feed dicts with 'name' and 'feed_url'.
        max_per_channel: Maximum number of videos per channel (default 5).

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

        count = 0
        for entry in root.findall("atom:entry", ns):
            if count >= max_per_channel:
                break
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
            count += 1

    logger.info("Found %d videos from %d feeds (max %d per channel)", len(videos), len(feeds), max_per_channel)
    return videos


# --- Gemini で YouTube URL を直接要約 ---

SUMMARY_PROMPT = """専門家でもない人でもわかるように、平易な言葉でどんなことを伝えたいか要約して。最後に総論も平易な言葉で書いて。日本語で書いて。"""


def summarize_video(url: str, title: str = "") -> str | None:
    """Summarize a YouTube video by passing its URL directly to Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return None

    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_uri(
                    file_uri=url,
                    mime_type="video/mp4",
                ),
                f"この動画を要約してください。\n動画タイトル: {title}",
            ],
            config=types.GenerateContentConfig(
                system_instruction=SUMMARY_PROMPT,
                temperature=0.3,
                max_output_tokens=2000,
            ),
        )
        summary = response.text
        logger.info("Generated summary (%d chars) for %s", len(summary), url)
        return summary
    except Exception as e:
        logger.error("Summarization failed for %s: %s", url, e)
        return None


def process_videos(videos: list[dict], push_fn=None) -> list[dict]:
    """Process a list of videos: summarize with Gemini (YouTube URL direct).

    Skips already-processed videos. On each successful summary, immediately
    pushes to spreadsheet via push_fn and saves the processed ID.

    Args:
        videos: List of dicts with 'video_id', 'url', 'title', 'channel'.
        push_fn: Callable that takes a list[dict] and pushes to spreadsheet.

    Returns:
        List of newly processed video dicts with 'summary'.
    """
    processed_ids = load_processed_ids()
    results = []

    # Filter out already-processed videos
    new_videos = [v for v in videos if v["video_id"] not in processed_ids]
    skipped = len(videos) - len(new_videos)
    if skipped > 0:
        logger.info("Skipping %d already-processed videos", skipped)

    if not new_videos:
        logger.info("No new videos to process")
        return []

    for i, video in enumerate(new_videos):
        url = video["url"]
        logger.info("Processing (%d/%d): %s [%s]", i + 1, len(new_videos), video.get("title", ""), url)

        # Rate limit delay
        if i > 0:
            time.sleep(2)

        summary = summarize_video(url, title=video.get("title", ""))
        if summary:
            video["summary"] = summary
            video["has_subtitles"] = True

            # 即座にスプレッドシートに送信
            if push_fn:
                push_fn([video])

            processed_ids.add(video["video_id"])
            save_processed_ids(processed_ids)
        else:
            video["summary"] = "要約の生成に失敗しました"
            video["has_subtitles"] = False

        results.append(video)

    logger.info("Processed %d new videos", len(results))
    return results
