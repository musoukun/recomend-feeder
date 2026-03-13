"""Daily AI Report: scrape Twitter list -> 3 reports (tech / career / YouTube)."""

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from scraper import scrape_timeline
from classifier import classify_tweets
from feed_generator import generate_feeds
from spreadsheet import push_to_spreadsheet
from report_generator import (
    generate_tech_report,
    generate_career_report,
    generate_youtube_report,
    post_to_discord_webhook,
    save_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BLACKLIST_FILE = Path(__file__).parent / "blacklist.json"
WEBHOOKS_FILE = Path(__file__).parent / "webhooks.json"


def load_blacklist() -> set[str]:
    try:
        handles = json.loads(BLACKLIST_FILE.read_text("utf-8"))
        return {h.lower().lstrip("@") for h in handles}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def load_webhook_config() -> list[dict]:
    """Load webhook config from webhooks.json."""
    try:
        if WEBHOOKS_FILE.exists():
            config = json.loads(WEBHOOKS_FILE.read_text("utf-8"))
            logger.info("Loaded %d webhook destinations", len(config))
            return config
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to load webhooks.json: %s", e)
    return []


def post_report_to_webhooks(
    report_type: str,
    report_md: str,
    webhook_config: list[dict],
) -> None:
    """Post a report to all webhooks that subscribe to this report type."""
    for entry in webhook_config:
        if report_type in entry.get("reports", []):
            name = entry.get("name", "unknown")
            webhook_url = entry.get("webhook", "")
            if not webhook_url:
                continue
            logger.info("Posting %s report to %s", report_type, name)
            post_to_discord_webhook(report_md, webhook_url)


def load_youtube_summaries() -> list[dict]:
    """Load recent YouTube summaries for report."""
    summaries_file = Path(__file__).parent.parent / "video_summaries.json"
    try:
        if summaries_file.exists():
            all_summaries = json.loads(summaries_file.read_text(encoding="utf-8"))
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
    tweet_count = int(os.getenv("REPORT_TWEET_COUNT", "30"))
    today_str = date.today().isoformat()

    # Load webhook config
    webhook_config = load_webhook_config()

    # 1. Scrape Twitter list
    logger.info("Scraping Twitter list: %s (target: %d)", list_url, tweet_count)
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

    # 4. Generate category RSS feeds
    output_dir = Path(__file__).parent.parent / "docs"
    generate_feeds(tweets, output_dir=output_dir)

    # 5. Push to spreadsheet
    if tweets:
        logger.info("Pushing %d tweets to spreadsheet...", len(tweets))
        push_to_spreadsheet(tweets, sheet="twitter")

    # 6. Split tweets by category
    tech_tweets = [t for t in tweets if t.get("category") == "ai-tech"]
    career_tweets = [t for t in tweets if t.get("category") == "ai-career"]
    logger.info("Tech: %d, Career: %d", len(tech_tweets), len(career_tweets))

    # 7. Generate & post reports
    reports = {}

    if tech_tweets:
        logger.info("Generating AI tech report...")
        tech_report = generate_tech_report(tech_tweets)
        if tech_report:
            save_report(tech_report, "tech", today_str)
            reports["tech"] = tech_report

    if career_tweets:
        logger.info("Generating AI career report...")
        career_report = generate_career_report(career_tweets)
        if career_report:
            save_report(career_report, "career", today_str)
            reports["career"] = career_report

    youtube_summaries = load_youtube_summaries()
    if youtube_summaries:
        logger.info("Generating YouTube report (%d videos)...", len(youtube_summaries))
        yt_report = generate_youtube_report(youtube_summaries)
        if yt_report:
            save_report(yt_report, "youtube", today_str)
            reports["youtube"] = yt_report

    # 8. Post to webhooks
    if webhook_config:
        for report_type, report_md in reports.items():
            post_report_to_webhooks(report_type, report_md, webhook_config)
    else:
        logger.info("No webhooks.json found, skipping Discord posting")

    logger.info("Done!")


if __name__ == "__main__":
    main()
