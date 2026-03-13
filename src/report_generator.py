"""Generate daily AI news reports (tech / career / YouTube)."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

REPORT_OUTPUT_DIR = Path(__file__).parent.parent / "docs"
REPORT_ARCHIVE_DIR = REPORT_OUTPUT_DIR / "reports"

# --- レポート種別ごとのプロンプト ---

PROMPT_AI_TECH = """あなたはAI・テクノロジー分野の専門ニュースレター編集者です。
Xのツイートを元に、AI・テック関連ニュースのレポートを作成してください。

## 構成
1. 見出し: 「AI Tech Report - YYYY年MM月DD日」
2. Highlights: 最も注目すべきトピック3つを1文ずつ箇条書き
3. トピック別セクション: 関連ツイートをトピックごとにグループ化
   - トピック見出し
   - 3〜5文の要約（何が出た・何が変わった・なぜ注目か）
   - ソース: [著者名](URL) 形式

## ルール
- ソースにない情報を追加しない
- 「重要」「画期的」等の評価語で押し切らない。事実と数字で語る
- 初出の専門用語は平易に説明する
- 常体（だ・である）で書く
- 1トピック3〜5文。簡潔に
- トピック数は3〜8程度
- 全体で1500〜3000文字を目安
- Markdownフォーマット
- 各トピック末尾にソースURL必須"""

PROMPT_AI_CAREER = """あなたはAI時代の働き方・雇用動向を追う専門編集者です。
Xのツイートを元に、AI×雇用・働き方に関する「論点整理レポート」を作成してください。

## 構成
1. 見出し: 「AI Career Report - YYYY年MM月DD日」
2. 概要: 今日はどんな論点が話題になっているか2〜3文で俯瞰
3. 論点別セクション: 対立する意見や異なる視点をグループ化
   - 論点見出し（例:「AIは仕事を奪うのか、退屈な仕事から解放するのか」）
   - こういう意見がある、一方でこういう見方もある、という形で整理
   - 各意見の背景や根拠も簡潔に添える
   - ソース: [著者名](URL) 形式

## ルール
- 編集者自身の結論は出さない。「こういう見方がある」形式で中立に整理する
- ソースにない情報を追加しない
- 賛否両論ある場合は両方の視点を公平に扱う
- 1つの意見しかないトピックでもセクションにしてよい
- 初出の専門用語は平易に説明する
- 常体（だ・である）で書く
- 1論点3〜5文。簡潔に
- 論点数は2〜6程度
- 全体で1000〜2500文字を目安
- Markdownフォーマット
- 各論点末尾にソースURL必須"""

PROMPT_YOUTUBE = """あなたはAI・テクノロジー分野の専門ニュースレター編集者です。
YouTube動画の要約を元に、注目動画のまとめレポートを作成してください。

## 構成
1. 見出し: 「YouTube AI Picks - YYYY年MM月DD日」
2. 概要: 今回の注目ポイントを2〜3文で
3. 動画ごとのセクション:
   - 動画タイトル + チャンネル名
   - 3〜5文で要点（何がわかるか、なぜ見る価値があるか）
   - [チャンネル名 - タイトル](URL) 形式でリンク

## ルール
- ソースにない情報を追加しない
- 「必見」「おすすめ」等の評価語で押し切らない。内容で語る
- 初出の専門用語は平易に説明する
- 常体（だ・である）で書く
- 1動画3〜5文
- 全体で1000〜2500文字を目安
- Markdownフォーマット"""


def generate_report(
    system_prompt: str,
    user_prompt: str,
    report_name: str = "report",
) -> str | None:
    """Generate a report using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return None

    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
                max_output_tokens=8000,
            ),
        )
        report = response.text
        logger.info("Generated %s (%d chars)", report_name, len(report))
        return report
    except Exception as e:
        logger.error("%s generation failed: %s", report_name, e)
        return None


def generate_tech_report(tweets: list[dict]) -> str | None:
    """Generate AI tech report from tweets."""
    if not tweets:
        return None
    prompt = _build_tweets_prompt(tweets, "AI・テック")
    return generate_report(PROMPT_AI_TECH, prompt, "tech report")


def generate_career_report(tweets: list[dict]) -> str | None:
    """Generate AI career/employment report from tweets."""
    if not tweets:
        return None
    prompt = _build_tweets_prompt(tweets, "AI×雇用・働き方")
    return generate_report(PROMPT_AI_CAREER, prompt, "career report")


def generate_youtube_report(summaries: list[dict]) -> str | None:
    """Generate YouTube summary report."""
    if not summaries:
        return None
    today_str = date.today().strftime("%Y年%m月%d日")
    parts = [f"以下のYouTube動画要約から{today_str}のレポートを作成してください。\n"]
    for v in summaries:
        parts.append(f"- **{v.get('channel', '')} - {v.get('title', '')}**")
        parts.append(f"  URL: {v.get('url', '')}")
        summary = v.get("summary", "")
        parts.append(f"  要約: {summary[:800]}")
        parts.append("")
    return generate_report(PROMPT_YOUTUBE, "\n".join(parts), "youtube report")


def _build_tweets_prompt(tweets: list[dict], topic: str) -> str:
    today_str = date.today().strftime("%Y年%m月%d日")
    parts = [f"以下のXツイートから{today_str}の{topic}レポートを作成してください。\n"]
    for i, t in enumerate(tweets):
        parts.append(f"{i+1}. {t['author']} ({t['handle']}): {t['text'][:500]}")
        parts.append(f"   URL: {t['url']}")
        if t.get("summary"):
            parts.append(f"   要約: {t['summary']}")
        parts.append("")
    return "\n".join(parts)


# --- 保存 ---

def save_report(report_md: str, filename: str, date_str: str | None = None) -> Path:
    """Save report to docs/reports/YYYY-MM-DD-{filename}.md."""
    if date_str is None:
        date_str = date.today().isoformat()

    REPORT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    archive_path = REPORT_ARCHIVE_DIR / f"{date_str}-{filename}.md"
    archive_path.write_text(report_md, encoding="utf-8")
    logger.info("Report saved: %s", archive_path)
    return archive_path


# --- Discord Webhook ---

def post_to_discord_webhook(report_md: str, webhook_url: str) -> bool:
    """Post report to Discord via webhook. Splits if >2000 chars."""
    import urllib.request

    chunks = _split_report(report_md, max_len=1900)

    for i, chunk in enumerate(chunks):
        payload = json.dumps({"content": chunk})
        req = urllib.request.Request(
            webhook_url,
            data=payload.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "RecommendFeeder/1.0",
            },
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
