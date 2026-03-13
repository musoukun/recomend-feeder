"""Main entry point: scrape Twitter timeline, classify, and generate RSS feeds."""

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from scraper import scrape_timeline
from classifier import classify_tweets
from feed_generator import generate_feeds
from spreadsheet import push_to_spreadsheet

BLACKLIST_FILE = Path(__file__).parent / "blacklist.json"


def load_blacklist() -> set[str]:
    """Load blacklisted handles from blacklist.json."""
    try:
        handles = json.loads(BLACKLIST_FILE.read_text("utf-8"))
        # Normalize: ensure all start with @, lowercase
        return {h.lower().lstrip("@") for h in handles}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def filter_blacklist(tweets: list[dict], blacklist: set[str]) -> list[dict]:
    """Remove tweets from blacklisted handles."""
    filtered = [t for t in tweets if t.get("handle", "").lower().lstrip("@") not in blacklist]
    removed = len(tweets) - len(filtered)
    if removed > 0:
        logger.info("Blacklist: removed %d tweets", removed)
    return filtered

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    tweet_count = int(os.getenv("TWEET_COUNT", "50"))
    headless = os.getenv("HEADLESS", "true").lower() == "true"

    # Scrape
    logger.info("Starting Twitter scrape...")
    tweets = scrape_timeline(
        tweet_count=tweet_count,
        headless=headless,
    )

    if not tweets:
        logger.warning("No tweets scraped. Feed will not be updated.")
        sys.exit(0)

    # Blacklist filter
    blacklist = load_blacklist()
    if blacklist:
        tweets = filter_blacklist(tweets, blacklist)

    # Classify
    logger.info("Classifying %d tweets with Gemini...", len(tweets))
    classify_tweets(tweets)

    # Generate category-specific RSS feeds
    output_dir = Path(__file__).parent.parent / "docs"
    generate_feeds(tweets, output_dir=output_dir)

    # スプレッドシートに蓄積
    logger.info("Pushing %d tweets to spreadsheet...", len(tweets))
    push_to_spreadsheet(tweets, sheet="twitter")

    logger.info("Done!")


if __name__ == "__main__":
    main()
