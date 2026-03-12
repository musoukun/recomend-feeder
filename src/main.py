"""Main entry point: scrape Twitter timeline, classify, and generate RSS feeds."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from scraper import scrape_timeline
from classifier import classify_tweets
from feed_generator import generate_feeds

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    username = os.getenv("TWITTER_USERNAME")
    password = os.getenv("TWITTER_PASSWORD")
    tweet_count = int(os.getenv("TWEET_COUNT", "50"))
    headless = os.getenv("HEADLESS", "true").lower() == "true"

    if not username or not password:
        logger.error("TWITTER_USERNAME and TWITTER_PASSWORD must be set in .env")
        sys.exit(1)

    # Scrape
    logger.info("Starting Twitter scrape...")
    tweets = scrape_timeline(
        username=username,
        password=password,
        tweet_count=tweet_count,
        headless=headless,
    )

    if not tweets:
        logger.warning("No tweets scraped. Feed will not be updated.")
        sys.exit(0)

    # Classify
    logger.info("Classifying %d tweets with Gemini...", len(tweets))
    classify_tweets(tweets)

    # Generate category-specific RSS feeds
    output_dir = Path(__file__).parent.parent / "docs"
    generate_feeds(tweets, output_dir=output_dir)

    logger.info("Done!")


if __name__ == "__main__":
    main()
