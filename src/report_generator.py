"""Generate daily AI news report from tweets and YouTube summaries."""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

from feedgen.feed import FeedGenerator
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

REPORT_OUTPUT_DIR = Path(__file__).parent.parent / "docs"
REPORT_ARCHIVE_DIR = REPORT_OUTPUT_DIR / "reports"

REPORT_SYSTEM_PROMPT = """あなたはAI・テクノロジー分野の専門ニュースレター編集者です。
Twitter（X）のツイートとYouTube動画の要約を元に、1日のAI・テック関連ニュースをまとめたデイリーレポートを作成してください。

## レポート構成

1. 見出し: 「AI Daily Report - YYYY年MM月DD日」
2. Today's Highlights: その日の最も重要な3つのトピックを箇条書きで1文ずつ
3. トピック別セクション: 関連するツイート・動画をトピックごとにグループ化し、各トピックについて：
   - トピック見出し（内容を端的に表すもの）
   - 3〜5文の要約（何が起きているのか、なぜ重要か）
   - 情報ソース: [著者名](URL) 形式でリンク一覧
4. YouTube Pick: YouTube動画の要約がある場合、別セクションとして含める

## ルール

- ソースにない情報を追加しない
- 「重要」「画期的」等の評価語で押し切らない。事実で語る
- 初出の専門用語は平易に説明する
- 常体（だ・である）で書く
- 1トピックの記述は3〜5文。簡潔に
- トピック数は3〜8程度に収める
- 全体で1500〜3000文字を目安にする
- Markdownフォーマットで出力する
- 各トピックの末尾にソースURLを必ず含める"""


def generate_daily_report(
    tweets: list[dict],
    youtube_summaries: list[dict] | None = None,
) -> str | None:
    """Generate a daily report from tweets and YouTube summaries using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return None

    if not tweets and not youtube_summaries:
        logger.warning("No data for report generation")
        return None

    client = genai.Client(api_key=api_key)
    prompt = _build_report_prompt(tweets, youtube_summaries or [])

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=REPORT_SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=8000,
            ),
        )
        report = response.text
        logger.info("Generated daily report (%d chars)", len(report))
        return report
    except Exception as e:
        logger.error("Report generation failed: %s", e)
        return None


def _build_report_prompt(tweets: list[dict], youtube_summaries: list[dict]) -> str:
    """Build Gemini prompt with all source material."""
    today_str = date.today().strftime("%Y年%m月%d日")
    parts = [f"以下の情報源から{today_str}のAIデイリーレポートを作成してください。\n"]

    if tweets:
        parts.append("## Xツイート\n")
        for i, t in enumerate(tweets):
            parts.append(f"{i+1}. {t['author']} ({t['handle']}): {t['text'][:500]}")
            parts.append(f"   URL: {t['url']}")
            if t.get("summary"):
                parts.append(f"   要約: {t['summary']}")
            parts.append("")

    if youtube_summaries:
        parts.append("\n## YouTube動画要約\n")
        for v in youtube_summaries:
            parts.append(f"- **{v.get('channel', '')} - {v.get('title', '')}**")
            parts.append(f"  URL: {v.get('url', '')}")
            summary = v.get("summary", "")
            parts.append(f"  要約: {summary[:500]}")
            parts.append("")

    return "\n".join(parts)


def save_report(report_md: str, date_str: str | None = None) -> tuple[Path, Path]:
    """Save report to docs/daily-report.md and docs/reports/YYYY-MM-DD.md."""
    if date_str is None:
        date_str = date.today().isoformat()

    REPORT_OUTPUT_DIR.mkdir(exist_ok=True)
    REPORT_ARCHIVE_DIR.mkdir(exist_ok=True)

    # Latest report (overwritten daily)
    latest_path = REPORT_OUTPUT_DIR / "daily-report.md"
    latest_path.write_text(report_md, encoding="utf-8")

    # Archived report
    archive_path = REPORT_ARCHIVE_DIR / f"{date_str}.md"
    archive_path.write_text(report_md, encoding="utf-8")

    logger.info("Report saved: %s, %s", latest_path, archive_path)
    return latest_path, archive_path


def generate_report_feed(report_md: str, date_str: str | None = None) -> str:
    """Generate/update RSS feed for daily reports."""
    if date_str is None:
        date_str = date.today().isoformat()

    REPORT_OUTPUT_DIR.mkdir(exist_ok=True)
    feed_path = REPORT_OUTPUT_DIR / "feed-daily-report.xml"

    fg = FeedGenerator()
    fg.title("AI Daily Report")
    fg.link(href="https://musoukun.github.io/recomend-feeder/daily-report.md")
    fg.description("AIニュースのデイリーレポート")
    fg.language("ja")
    fg.lastBuildDate(datetime.now(timezone.utc))

    fe = fg.add_entry()
    fe.id(f"daily-report-{date_str}")
    fe.title(f"AI Daily Report - {date_str}")
    fe.link(href=f"https://musoukun.github.io/recomend-feeder/reports/{date_str}.md")

    report_html = report_md.replace("\n", "<br>")
    fe.content(report_html, type="html")
    fe.description(report_md[:200])
    fe.published(datetime.now(timezone.utc))

    output_path = str(feed_path)
    fg.rss_file(output_path, pretty=True)
    logger.info("Generated feed-daily-report.xml")
    return output_path


def post_to_discord_webhook(report_md: str, webhook_url: str) -> bool:
    """Post report to Discord via webhook. Splits if >2000 chars."""
    import urllib.request

    # Split on section boundaries
    chunks = _split_report(report_md, max_len=1900)

    for i, chunk in enumerate(chunks):
        payload = json.dumps({"content": chunk})
        req = urllib.request.Request(
            webhook_url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status not in (200, 204):
                    logger.error("Discord webhook failed: %d", resp.status)
                    return False
        except Exception as e:
            logger.error("Discord webhook error: %s", e)
            return False

        if i < len(chunks) - 1:
            import time
            time.sleep(1)

    logger.info("Posted report to Discord (%d messages)", len(chunks))
    return True


def _split_report(text: str, max_len: int = 1900) -> list[str]:
    """Split report on section boundaries (## headings)."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""

    for line in text.split("\n"):
        # Split before ## headings if adding this line would exceed limit
        if line.startswith("## ") and len(current) + len(line) > max_len and current:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"

        if len(current) > max_len:
            chunks.append(current.rstrip())
            current = ""

    if current.strip():
        chunks.append(current.rstrip())

    return chunks
