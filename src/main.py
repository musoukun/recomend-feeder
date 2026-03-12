"""Main entry point: scrape Twitter timeline and generate RSS feed."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from scraper import scrape_timeline
from feed_generator import generate_rss

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

    # Generate RSS
    # For GitHub Pages, output to docs/ directory
    output_dir = Path(__file__).parent.parent / "docs"
    output_dir.mkdir(exist_ok=True)
    output_path = str(output_dir / "feed.xml")

    generate_rss(tweets, output_path=output_path)
    logger.info("Done! Feed available at %s", output_path)


if __name__ == "__main__":
    main()
