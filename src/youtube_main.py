"""YouTube summarizer: md feed list → YouTube RSS → Gemini summary → Spreadsheet."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from youtube_summarizer import load_feeds_from_md, fetch_videos_from_feeds, process_videos
from spreadsheet import push_to_spreadsheet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    # Feed list markdown file
    default_md = Path(__file__).parent.parent / "youtube_feeds.md"
    md_path = os.getenv("YOUTUBE_FEEDS_MD", str(default_md))

    if not Path(md_path).exists():
        logger.error("Feed list not found: %s", md_path)
        sys.exit(1)

    # 1. Load feed URLs from markdown
    feeds = load_feeds_from_md(md_path)
    if not feeds:
        logger.error("No YouTube feeds found in %s", md_path)
        sys.exit(1)

    # 2. Fetch video entries from YouTube RSS feeds
    logger.info("Fetching videos from %d feeds...", len(feeds))
    videos = fetch_videos_from_feeds(feeds)

    if not videos:
        logger.info("No videos found.")
        sys.exit(0)

    logger.info("Found %d videos total", len(videos))

    # 3. Summarize with Gemini (YouTube URL direct)
    logger.info("Summarizing new videos with Gemini...")
    results = process_videos(videos)

    summarized = [v for v in results if v.get("has_subtitles")]
    logger.info("Successfully summarized %d/%d new videos", len(summarized), len(results))

    # 4. Push to Google Spreadsheet via GAS
    if summarized:
        logger.info("Pushing %d results to spreadsheet...", len(summarized))
        success = push_to_spreadsheet(summarized)
        if success:
            logger.info("Done! Results pushed to spreadsheet.")
        else:
            logger.error("Failed to push to spreadsheet.")
    else:
        logger.info("No new results to push.")


if __name__ == "__main__":
    main()
