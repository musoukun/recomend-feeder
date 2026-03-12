"""Tweet classifier using Gemini 2.5 Flash."""

import json
import logging
import os
from enum import Enum

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class Category(str, Enum):
    AI = "ai"
    POLITICS = "politics"
    TECH = "tech"
    CHAT = "chat"
    ROMANCE = "romance"
    ADULT = "adult"
    NEWS = "news"
    OTHER = "other"


CATEGORY_LABELS = {
    Category.AI: "AI・機械学習",
    Category.POLITICS: "政治",
    Category.TECH: "テクノロジー",
    Category.CHAT: "雑談",
    Category.ROMANCE: "恋愛",
    Category.ADULT: "アダルト",
    Category.NEWS: "ニュース",
    Category.OTHER: "その他",
}

SYSTEM_PROMPT = """あなたはツイートを分類するアシスタントです。
与えられたツイートのリストを以下のカテゴリに分類してください。

カテゴリ:
- ai: AI・機械学習・LLM・ChatGPT・画像生成など
- politics: 政治・選挙・政策・国際情勢
- tech: テクノロジー・プログラミング・ガジェット（AI以外）
- chat: 雑談・日常・つぶやき
- romance: 恋愛・婚活・出会い
- adult: アダルト・性的コンテンツ
- news: ニュース・時事（政治以外）
- other: 上記に当てはまらないもの

各ツイートに対してカテゴリを1つ割り当ててJSON配列で返してください。"""


def classify_tweets(tweets: list[dict]) -> list[dict]:
    """
    Classify tweets into categories using Gemini 2.5 Flash.

    Adds a 'category' key to each tweet dict.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set. All tweets will be categorized as 'other'.")
        for tweet in tweets:
            tweet["category"] = Category.OTHER.value
        return tweets

    client = genai.Client(api_key=api_key)

    # Process in batches to stay within token limits
    batch_size = 20
    for i in range(0, len(tweets), batch_size):
        batch = tweets[i : i + batch_size]
        _classify_batch(client, batch)

    return tweets


def _classify_batch(client: genai.Client, batch: list[dict]) -> None:
    """Classify a batch of tweets."""
    # Build prompt with tweet texts
    tweet_texts = []
    for idx, tweet in enumerate(batch):
        tweet_texts.append(f"{idx}: {tweet['author']} ({tweet['handle']}): {tweet['text'][:300]}")

    prompt = "以下のツイートを分類してください:\n\n" + "\n---\n".join(tweet_texts)

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
            },
            "required": ["index", "category"],
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
                max_output_tokens=1000,
            ),
        )

        results = json.loads(response.text)
        for item in results:
            idx = item["index"]
            if 0 <= idx < len(batch):
                batch[idx]["category"] = item["category"]

    except Exception as e:
        logger.error("Classification failed: %s", e)

    # Fill in any missing categories
    for tweet in batch:
        if "category" not in tweet:
            tweet["category"] = Category.OTHER.value
