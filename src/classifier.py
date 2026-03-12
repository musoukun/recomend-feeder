"""Tweet classifier using Gemini 2.5 Flash."""
from __future__ import annotations

import json
import logging
import os
from enum import Enum

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class Category(str, Enum):
    AI_TECH = "ai-tech"
    AI_CAREER = "ai-career"
    POLITICS = "politics"
    ROMANCE = "romance"
    ADULT = "adult"
    NEWS = "news"
    OTHER = "other"
    SKIP = "skip"


CATEGORY_LABELS = {
    Category.AI_TECH: "AI・テック",
    Category.AI_CAREER: "AI時代の働き方・雇用",
    Category.POLITICS: "政治",
    Category.ROMANCE: "恋愛",
    Category.ADULT: "アダルト",
    Category.NEWS: "ニュース",
    Category.OTHER: "その他",
}

SYSTEM_PROMPT = """あなたはツイートを分類し、要約するアシスタントです。
与えられたツイートのリストに対して、以下の2つを行ってください。

## 1. カテゴリ分類

カテゴリ:
- ai-tech: AI・機械学習・LLM・ChatGPT・画像生成・プログラミング・テクノロジー全般。具体的なツール・サービス・技術の話題（Claude Code, Gemini, MCP, k8s, セキュリティ脆弱性など）
- ai-career: AI時代の働き方・雇用。エンジニアの雇用動向、レイオフ、採用、キャリア、転職、企業の人員戦略、AI導入による組織変化、AIガバナンス、エンジニアの将来像など
- politics: 政治・選挙・政策・国際情勢
- romance: 恋愛・婚活・出会い
- adult: アダルト・性的コンテンツ
- news: ニュース・時事（政治・テック以外）
- other: 上記に当てはまらないもの（雑談・日常など）
- skip: 以下に該当するツイートは除外する

迷ったときの判断基準:
- ツールや技術そのものの紹介・使い方 → ai-tech
- 「AIで仕事がどう変わるか」「人間の役割」「組織・採用への影響」 → ai-career
- 両方の要素がある場合は、主題がどちらかで判断する

## 2. skipにする基準（重要）

以下に該当するツイートは category を "skip" にすること:
- 個人の感想・つぶやきレベルで、他の人が読んでも情報価値がないもの（例:「Claude依存症になった」「○○使ってみた、すごい」程度の感想）
- 具体的な情報・知見・ニュースを含まない、ただの雑感や共感狙いのツイート
- 宣伝・セルフプロモーション（自分のスクールやサービスの宣伝）
- 内輪ネタや文脈がないと意味が通じないリプライ

逆にskipしないもの:
- 具体的なツール・機能・設定方法の紹介
- 数字やデータを含むニュース・分析
- 業界動向や技術トレンドの考察（個人の感想でなく論点があるもの）

## 3. 要約（70文字以内）

各ツイートに対して「このツイートが伝えたいこと」を70文字以内で平易な言葉で要約してください。
- skipのツイートも一応要約を付けてよい（空文字でもよい）
- 要約は事実ベースで。感想や評価は入れない
- 「〜とのこと」「〜らしい」は使わない。言い切る

各ツイートに対してカテゴリと要約をJSON配列で返してください。"""


def classify_tweets(tweets: list[dict]) -> list[dict]:
    """
    Classify tweets into categories and generate summaries using Gemini 2.5 Flash.

    Adds 'category' and 'summary' keys to each tweet dict.
    Tweets with category 'skip' are removed from the list.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set. All tweets will be categorized as 'other'.")
        for tweet in tweets:
            tweet["category"] = Category.OTHER.value
            tweet["summary"] = ""
        return tweets

    client = genai.Client(api_key=api_key)

    # Process in batches to stay within token limits
    batch_size = 20
    for i in range(0, len(tweets), batch_size):
        batch = tweets[i : i + batch_size]
        _classify_batch(client, batch)

    # skipを除外
    before = len(tweets)
    tweets[:] = [t for t in tweets if t.get("category") != Category.SKIP.value]
    skipped = before - len(tweets)
    if skipped > 0:
        logger.info("Skipped %d low-value tweets", skipped)

    return tweets


def _classify_batch(client: genai.Client, batch: list[dict]) -> None:
    """Classify a batch of tweets."""
    # Build prompt with tweet texts
    tweet_texts = []
    for idx, tweet in enumerate(batch):
        tweet_texts.append(f"{idx}: {tweet['author']} ({tweet['handle']}): {tweet['text'][:300]}")

    prompt = "以下のツイートを分類・要約してください:\n\n" + "\n---\n".join(tweet_texts)

    # Define response schema
    response_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                },
                "summary": {
                    "type": "string",
                    "description": "70文字以内の要約",
                },
            },
            "required": ["index", "category", "summary"],
        },
    }

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_json_schema=response_schema,
                temperature=0.1,
                max_output_tokens=8000,
            ),
        )

        results = json.loads(response.text)
        for item in results:
            idx = item["index"]
            if 0 <= idx < len(batch):
                batch[idx]["category"] = item["category"]
                batch[idx]["summary"] = item.get("summary", "")

    except Exception as e:
        logger.error("Classification failed: %s", e)

    # Fill in any missing categories
    for tweet in batch:
        if "category" not in tweet:
            tweet["category"] = Category.OTHER.value
        if "summary" not in tweet:
            tweet["summary"] = ""
