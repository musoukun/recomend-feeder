"""Daily AI Report: scrape Twitter list + YouTube summaries -> unified report."""

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from scraper import scrape_timeline
from classifier import classify_tweets
from report_generator import (
    generate_daily_report,
    generate_report_feed,
    post_to_discord_webhook,
    save_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BLACKLIST_FILE = Path(__file__).parent / "blacklist.json"


def load_blacklist() -> set[str]:
    try:
        handles = json.loads(BLACKLIST_FILE.read_text("utf-8"))
        return {h.lower().lstrip("@") for h in handles}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def load_todays_youtube_summaries() -> list[dict]:
    """Load YouTube summaries from video_summaries.json (all recent)."""
    summaries_file = Path(__file__).parent.parent / "video_summaries.json"
    try:
        if summaries_file.exists():
            all_summaries = json.loads(summaries_file.read_text(encoding="utf-8"))
            # 直近10件を使用（日付フィルタなし、レポートに含める価値のあるもの）
            return all_summaries[:10]
    except Exception:
        pass
    return []


def main() -> None:
    load_dotenv()

    list_url = os.getenv(
        "TWITTER_LIST_URL",
        "https://x.com/i/lists/2032409039397966259",
    )
    tweet_count = int(os.getenv("REPORT_TWEET_COUNT", "100"))

    # 1. Scrape Twitter list
    logger.info("Scraping Twitter list: %s", list_url)
    tweets = scrape_timeline(
        tweet_count=tweet_count,
        headless=False,
        target_url=list_url,
    )

    if not tweets:
        logger.warning("No tweets scraped from list.")
        sys.exit(0)

    logger.info("Scraped %d tweets from list", len(tweets))

    # 2. Blacklist filter
    blacklist = load_blacklist()
    if blacklist:
        before = len(tweets)
        tweets = [
            t for t in tweets
            if t.get("handle", "").lower().lstrip("@") not in blacklist
        ]
        removed = before - len(tweets)
        if removed > 0:
            logger.info("Blacklist: removed %d tweets", removed)

    # 3. Classify & skip filter
    logger.info("Classifying %d tweets...", len(tweets))
    classify_tweets(tweets)
    logger.info("%d tweets after classification/skip filter", len(tweets))

    # 4. Load YouTube summaries
    youtube_summaries = load_todays_youtube_summaries()
    logger.info("Loaded %d YouTube summaries", len(youtube_summaries))

    # 5. Generate report
    logger.info("Generating daily report...")
    report_md = generate_daily_report(tweets, youtube_summaries)

    if not report_md:
        logger.error("Failed to generate report")
        sys.exit(1)

    # 6. Save report
    today_str = date.today().isoformat()
    save_report(report_md, today_str)

    # 7. Generate RSS feed
    generate_report_feed(report_md, today_str)

    # 8. Post to Discord (if webhook configured)
    webhook_url = os.getenv("DISCORD_REPORT_WEBHOOK")
    if webhook_url:
        post_to_discord_webhook(report_md, webhook_url)
    else:
        logger.info("DISCORD_REPORT_WEBHOOK not set, skipping Discord post")

    logger.info("Daily report complete!")


if __name__ == "__main__":
    main()
