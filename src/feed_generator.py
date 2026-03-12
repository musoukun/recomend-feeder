"""Generate RSS feed from scraped tweets."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from feedgen.feed import FeedGenerator

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def generate_rss(tweets: list[dict], output_path: str | None = None) -> str:
    """
    Generate RSS XML from a list of tweet dicts.

    Args:
        tweets: List of dicts with keys: author, handle, text, url, timestamp, images
        output_path: Path to write the RSS file. Defaults to output/feed.xml

    Returns:
        Path to the generated RSS file.
    """
    fg = FeedGenerator()
    fg.title("Twitter Timeline Feed")
    fg.link(href="https://x.com/home")
    fg.description("Auto-generated RSS feed from Twitter timeline")
    fg.language("ja")
    fg.lastBuildDate(datetime.now(timezone.utc))

    for tweet in tweets:
        fe = fg.add_entry()
        fe.id(tweet["url"])
        fe.title(f'{tweet["author"]} ({tweet["handle"]})')
        fe.link(href=tweet["url"])

        # Build HTML content
        content_html = _build_content_html(tweet)
        fe.content(content_html, type="html")
        fe.description(tweet["text"][:200])

        # Parse timestamp
        if tweet.get("timestamp"):
            try:
                dt = datetime.fromisoformat(tweet["timestamp"].replace("Z", "+00:00"))
                fe.published(dt)
                fe.updated(dt)
            except ValueError:
                fe.published(datetime.now(timezone.utc))
        else:
            fe.published(datetime.now(timezone.utc))

        fe.author(name=f'{tweet["author"]} ({tweet["handle"]})')

    # Write to file
    if output_path is None:
        OUTPUT_DIR.mkdir(exist_ok=True)
        output_path = str(OUTPUT_DIR / "feed.xml")

    fg.rss_file(output_path, pretty=True)
    logger.info("RSS feed written to %s", output_path)
    return output_path


def _build_content_html(tweet: dict) -> str:
    """Build HTML content for a tweet entry."""
    parts = []

    # Author info
    parts.append(f'<p><strong>{tweet["author"]}</strong> <a href="https://x.com/{tweet["handle"].lstrip("@")}">{tweet["handle"]}</a></p>')

    # Tweet text (preserve line breaks)
    text_html = tweet["text"].replace("\n", "<br>")
    parts.append(f"<p>{text_html}</p>")

    # Images
    for img_url in tweet.get("images", []):
        parts.append(f'<p><img src="{img_url}" style="max-width:100%;" /></p>')

    # Link to original
    parts.append(f'<p><a href="{tweet["url"]}">View on Twitter</a></p>')

    return "\n".join(parts)
