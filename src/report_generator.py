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

# --- 共通の文体・構成ルール ---

STYLE_RULES = """
## 文体
- 友達に口頭で説明するくらいの温度感。「つまり○○ってこと」くらい噛み砕く
- 硬い表現を避ける。「推測し解決を試みた」→「気づいてハックした」のように日常の言葉に置き換える
- 読んだ人が「へぇ」「やばっ」と思える引っかかりを残す
- 体言止めや短文を混ぜてテンポを出す。1文は短めに
- 敬体（です・ます）は使わない

## 厳守ルール
- 元の情報にない数字・固有名詞・事例は足さない
- 「重要」「画期的」「効果的」などの評価語で押し切らない。事実と数字で語る
- 比喩表現（「包囲網」「狙い撃ち」「武器」など）は使わない。そのまま平易に書く
- 初出の固有名詞・専門用語には必ず「それは何か」の説明を添える
- 同じ内容の繰り返しや抽象まとめ（「まとめると」「要するに」）は入れない
- 読者への問いかけ（「いかがでしょうか」）は入れない
- 前置き宣言（「本記事では」「以下で解説します」）は入れない
- 締めの定型句（「参考になれば幸いです」）は入れない。言い切ったら終わる

## 書式
- 「。」の後は必ず改行する
- Markdownの見出し（##）、太字（**）、番号付きリストは使ってよい
- 装飾過多にしない。太字は1セクションにつき1〜2箇所まで
- 箇条書きの羅列だけで構成しない。文章として読めるセクションにする
- 各セクションは2〜3文程度。長くなりすぎない
- セクション数は3〜5程度
- 「例えば」で始まる具体例は入れない。事実だけ書く
- 1セクション100字以内を目安。超えたら削る"""

# --- レポート種別ごとのプロンプト ---

PROMPT_AI_TECH = f"""Xのツイートを元に、AI・テックニュースのニュースレターを作る。

## 構成
1. 冒頭に「## AI・テックレポート」と書く
2. 「今日のAI・テックトピックはこちら！」のような導入1行
2. 各トピックのハイライトを箇条書き（1トピック1行、キャッチーに）
   - 例: 「- ○○が△△になった！？これからの方式が変わるかも」
   - 例: 「- □□がリリース。何が変わったのか」
3. 「それぞれ見ていきます」のようなつなぎ1行
4. トピックごとの説明（番号付き）:
   - すごいところ・要点を2〜3文で簡潔に
   - ソース: [著者名](URL) 形式
5. **トピックは最大10件**ピックアップする。素材が10件未満なら全件取り上げる
6. 全体で500〜2500文字

## トーン
- 友達に「これ面白かったよ」と教える温度感
- 敬体（です・ます）OK。ただし堅くしない
- 「！」「？」は自然な範囲で使ってよい
{STYLE_RULES}"""

PROMPT_AI_CAREER = f"""Xのツイートを元に、AI×雇用・働き方のニュースレターを作る。

## 構成
1. 冒頭に「## AI×雇用・働き方レポート」と書く
2. 「今日の働き方トピックはこちら！」のような導入1行
2. 各論点のハイライトを箇条書き（1論点1行、キャッチーに）
   - 例: 「- AIで○○がどう変わる？賛否両論あり」
   - 例: 「- ○○業界でAI導入、現場はどうなってる？」
3. 「それぞれ見ていきます」のようなつなぎ1行
4. 論点ごとの説明（番号付き）:
   - 「こういう見方がある」「一方でこういう意見も」形式で中立に、2〜3文で
   - 編集者の結論は出さない
   - ソース: [著者名](URL) 形式
5. **論点は最大10件**ピックアップする。素材が10件未満なら全件取り上げる
6. 全体で500〜2500文字

## トーン
- 友達に「こんな話出てるよ」と教える温度感
- 敬体（です・ます）OK。ただし堅くしない
- 「！」「？」は自然な範囲で使ってよい
{STYLE_RULES}"""

PROMPT_YOUTUBE = f"""YouTube動画の要約を元に、カジュアルなニュースレター形式でまとめる。

## 構成
1. 冒頭に「## YouTubeレポート」と書く
2. 「今日のピックアップはこちら！」のような導入1行
2. 各動画のハイライトを箇条書き（1動画1行、キャッチーに）
   - 例: 「- ○○が△△になった！？これからの方式が変わるかも」
   - 例: 「- □□ Proがリリース。何が変わったのか」
3. 「それぞれ見ていきます」のようなつなぎ1行
4. 動画ごとの説明（番号付き）:
   - すごいところ・要点を2〜3文で簡潔に
   - 最終行: [チャンネル名 - タイトル](URL)
5. 全体で500〜1200文字

## トーン
- 友達に「これ面白かったよ」と教える温度感
- 敬体（です・ます）OK。ただし堅くしない
- 「！」「？」は自然な範囲で使ってよい
{STYLE_RULES}"""


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
        payload = json.dumps({"content": chunk, "flags": 4096}, ensure_ascii=False)
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
    """Split report so each chunk stays under max_len."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""

    for line in text.split("\n"):
        candidate = current + line + "\n"
        if len(candidate) > max_len:
            if current.strip():
                chunks.append(current.rstrip())
            current = line + "\n"
            # single line exceeds max_len — force split
            if len(current) > max_len:
                chunks.append(current.rstrip())
                current = ""
        else:
            current = candidate

    if current.strip():
        chunks.append(current.rstrip())

    return chunks
