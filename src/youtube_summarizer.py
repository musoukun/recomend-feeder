"""YouTube video summarizer: YouTube RSS → transcript/Gemini summarization → Spreadsheet."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types
from youtube_transcript_api import YouTubeTranscriptApi

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


# --- トランスクリプト取得 ---

def get_transcript(video_id: str) -> str | None:
    """Fetch transcript using youtube-transcript-api.

    Tries: ja → en → any available language.
    Returns transcript text or None.
    """
    ytt_api = YouTubeTranscriptApi()

    try:
        transcript_list = ytt_api.list(video_id)
    except Exception as e:
        logger.warning("Failed to list transcripts for %s: %s", video_id, e)
        return None

    # 優先順: ja手動 → en手動 → ja自動 → en自動 → any
    transcript = None
    try:
        transcript = transcript_list.find_manually_created_transcript(['ja', 'en'])
    except Exception:
        try:
            transcript = transcript_list.find_generated_transcript(['ja', 'en'])
        except Exception:
            try:
                transcript = transcript_list.find_transcript(['ja', 'en'])
            except Exception:
                # 何でもいいので最初のものを取得
                for t in transcript_list:
                    transcript = t
                    break

    if transcript is None:
        logger.warning("No transcript available for %s", video_id)
        return None

    try:
        fetched = transcript.fetch()
        text = " ".join(snippet.text for snippet in fetched)
        logger.info("Got transcript for %s (%d chars, lang=%s)", video_id, len(text), transcript.language_code)
        return text
    except Exception as e:
        logger.warning("Failed to fetch transcript for %s: %s", video_id, e)
        return None


# --- Gemini 要約 ---

SUMMARY_PROMPT = """## What I do
記事や情報を読み取り、平易な言葉で、紹介文を出力する
## When to use me
- 記事やドキュメントの要点を構造化して伝えたいとき
- 特定のトピックの「すごい点」「注意点」などを抜き出して紹介したいとき
- 複数の情報や選択肢を整理・比較したいとき

## タイトル
- 必ずタイトルを付ける
- 短く、内容が一言で伝わるものにする（目安：20〜30字程度）
- 「～する時代に」「～はもう～かもしれない」「～の紹介」「～は～になるか」のような、軽く引きのあるトーン
- 大げさな煽りや疑問形の乱用はしない

## 冒頭の要約
- 最初の2〜3行で「これは何で、何が起きているのか」を説明する
- **固有名詞・専門用語が初出する場合は、必ず平易な言葉で「それは何か」を説明してから使う**。読者に前提知識がないものとして書く
- 冒頭で読む価値があるか決まるので、密度を上げる

## 構成パターン
ユーザーの指示から意図を読み取り、以下のいずれかの構成を自動選択する。

### 紹介（「すごい点を紹介して」「ポイントを教えて」など）
1. 冒頭要約（上記ルールに従う）
2. 番号付きセクションで深掘り。各セクションは以下で構成する
   - 何が変わったのか／何が起きているのか（事実）
   - なぜそれが重要なのか（意味）
   - **読者がイメージできる平易な具体例**（裏付け）

### 整理（「整理して」「まとめて」「要点を出して」など）
1. 冒頭要約
2. 番号付きセクションで要点を分類・構造化する
3. 各セクションは「何の話か」「具体的にどういうことか」を簡潔にまとめる

### 比較（「比較して」「違いを教えて」「どっちがいいか」など）
1. 冒頭で比較軸（何を基準に比べるか）を提示する
2. 番号付きセクション、または表で差分を整理する
3. 判断が分かれるポイントは「こういう場合はA、こういう場合はB」のように条件付きで書く。一方的な結論は出さない

## 厳守ルール

### 内容面
- 元の情報にない数字・固有名詞・事例は足さない
- 曖昧な箇所は曖昧なまま出す。勝手に断定しない
- 「重要」「画期的」「効果的」などの評価語で押し切らない。事実と数字で語る
- **比喩表現（「包囲網」「狙い撃ち」「武器」など）は使わない**。何が起きているかをそのまま平易に書く
- **初出の固有名詞・専門用語には必ず「それは何か」の説明を添える**
- 同じ内容の繰り返しや抽象まとめ（「まとめると」「要するに」）は入れない
- 読者への問いかけ（「いかがでしょうか」「ご存知ですか」）は入れない
- 前置き宣言（「本記事では」「以下で解説します」）は入れない
- 締めの定型句（「参考になれば幸いです」「ぜひ試してみてください」）は入れない。言い切ったら終わる

### 分量
- **各セクションは3〜4文程度**を目安にする。長くなりすぎない
- 全体のセクション数は3〜5程度
- 短めを指示された場合はさらに絞る

### 書式
- Markdownの見出し（#）、太字（**）、番号付きリストは使ってよい
- ただし装飾過多にしない。太字は1セクションにつき1〜2箇所まで
- 箇条書きの羅列だけで構成しない。文章として読めるセクションにする
- 表は比較パターンのときだけ使う。それ以外では原則使わない

## 文体
- カジュアルだが密度が高い。雑談ではなく「わかってる人が手短に説明してる」温度感
- 敬体（です・ます）は使わない。常体（だ・である）ベース。ただし硬くなりすぎないように「〜になった」「〜できる」くらいの柔らかさは入れる
- 体言止めや短文を混ぜてテンポを出す
- 1文は短めに。だらだら接続しない

## 出力形式
- タイトル＋構造化された説明文のみを出力する
- 解説・前置き・「以下にまとめました」のような導入文は出さない"""


def summarize_with_transcript(transcript: str, title: str = "") -> str | None:
    """Summarize transcript text using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return None

    client = genai.Client(api_key=api_key)

    # 長すぎるトランスクリプトは切り詰め
    max_chars = 50000
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
                max_output_tokens=8000,
            ),
        )
        summary = response.text
        logger.info("Generated summary (%d chars)", len(summary))
        return summary
    except Exception as e:
        logger.error("Summarization failed: %s", e)
        return None


def summarize_with_video_url(url: str, title: str = "") -> str | None:
    """Fallback: summarize by passing YouTube URL directly to Gemini."""
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
                max_output_tokens=8000,
            ),
        )
        summary = response.text
        logger.info("Generated summary via video URL (%d chars) for %s", len(summary), url)
        return summary
    except Exception as e:
        logger.error("Video URL summarization failed for %s: %s", url, e)
        return None


def process_videos(videos: list[dict], push_fn=None) -> list[dict]:
    """Process videos: get transcript → Gemini summarize → push to spreadsheet.

    1. youtube-transcript-api でトランスクリプト取得 → テキストをGeminiで要約
    2. 字幕なしの場合、Gemini に YouTube URL を直接渡してフォールバック

    Skips already-processed videos. On each successful summary, immediately
    pushes to spreadsheet via push_fn and saves the processed ID.
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
        video_id = video["video_id"]
        title = video.get("title", "")
        logger.info("Processing (%d/%d): %s [%s]", i + 1, len(new_videos), title, url)

        # Rate limit delay
        if i > 0:
            time.sleep(2)

        # Step 1: トランスクリプト取得 → テキスト要約
        summary = None
        transcript = get_transcript(video_id)
        if transcript:
            summary = summarize_with_transcript(transcript, title=title)

        # Step 2: フォールバック — Gemini に動画URL直接
        if not summary:
            logger.info("Falling back to video URL summarization for %s", url)
            summary = summarize_with_video_url(url, title=title)

        if summary:
            video["summary"] = summary
            video["has_subtitles"] = True

            # 即座にスプレッドシートに送信
            if push_fn:
                push_fn([video])

            processed_ids.add(video_id)
            save_processed_ids(processed_ids)
        else:
            video["summary"] = "要約の生成に失敗しました"
            video["has_subtitles"] = False

        results.append(video)

    logger.info("Processed %d new videos", len(results))
    return results
