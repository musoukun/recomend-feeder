"""YouTube summarizer entry point: RSS feed → yt-dlp subtitles → Gemini summary → Spreadsheet."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from youtube_summarizer import extract_youtube_urls, process_videos
from spreadsheet import push_to_spreadsheet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    # Feed file to scan for YouTube URLs
    feed_dir = Path(__file__).parent.parent / "docs"
    feed_file = os.getenv("YOUTUBE_FEED_SOURCE", str(feed_dir / "feed.xml"))

    if not Path(feed_file).exists():
        logger.error("Feed file not found: %s", feed_file)
        sys.exit(1)

    # Subtitle language preference
    sub_lang = os.getenv("SUBTITLE_LANG", "ja")

    # 1. Extract YouTube URLs from RSS feed
    logger.info("Extracting YouTube URLs from %s", feed_file)
    videos = extract_youtube_urls(feed_file)

    if not videos:
        logger.info("No YouTube videos found in feed.")
        sys.exit(0)

    logger.info("Found %d YouTube videos", len(videos))

    # 2. Get subtitles and summarize
    logger.info("Processing videos (yt-dlp + Gemini)...")
    results = process_videos(videos, lang=sub_lang)

    summarized = [v for v in results if v.get("has_subtitles")]
    logger.info("Successfully summarized %d/%d videos", len(summarized), len(results))

    # 3. Push to Google Spreadsheet
    if results:
        logger.info("Pushing %d results to spreadsheet...", len(results))
        success = push_to_spreadsheet(results)
        if success:
            logger.info("Done! Results pushed to spreadsheet.")
        else:
            logger.error("Failed to push to spreadsheet.")
    else:
        logger.info("No results to push.")


if __name__ == "__main__":
    main()
