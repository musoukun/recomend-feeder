"""Generate RSS feeds from scraped tweets, split by category."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from feedgen.feed import FeedGenerator

from classifier import CATEGORY_LABELS, Category

logger = logging.getLogger(__name__)


def generate_feeds(tweets: list[dict], output_dir: str | Path) -> list[str]:
    """
    Generate category-specific RSS feeds + an all-in-one feed.

    Args:
        tweets: List of tweet dicts with 'category' key.
        output_dir: Directory to write feed XML files.

    Returns:
        List of generated file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    generated = []

    # All tweets feed
    path = _write_feed(
        tweets,
        title="Twitter Timeline - All",
        filename="feed.xml",
        output_dir=output_dir,
    )
    generated.append(path)

    # Group by category
    by_category = defaultdict(list)
    for tweet in tweets:
        by_category[tweet.get("category", Category.OTHER.value)].append(tweet)

    for category_value, category_tweets in by_category.items():
        try:
            cat = Category(category_value)
            label = CATEGORY_LABELS[cat]
        except (ValueError, KeyError):
            label = category_value

        path = _write_feed(
            category_tweets,
            title=f"Twitter Timeline - {label}",
            filename=f"feed-{category_value}.xml",
            output_dir=output_dir,
        )
        generated.append(path)

    logger.info("Generated %d feeds in %s", len(generated), output_dir)
    return generated


def _write_feed(
    tweets: list[dict],
    title: str,
    filename: str,
    output_dir: Path,
) -> str:
    """Write a single RSS feed file."""
    fg = FeedGenerator()
    fg.title(title)
    fg.link(href="https://x.com/home")
    fg.description(f"Auto-generated RSS feed: {title}")
    fg.language("ja")
    fg.lastBuildDate(datetime.now(timezone.utc))

    for tweet in tweets:
        fe = fg.add_entry()
        fe.id(tweet["url"])
        fe.title(f'{tweet["author"]} ({tweet["handle"]})')
        fe.link(href=tweet["url"])

        content_html = _build_content_html(tweet)
        fe.content(content_html, type="html")
        fe.description(tweet["text"][:200])

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

    output_path = str(output_dir / filename)
    fg.rss_file(output_path, pretty=True)
    logger.info("  %s (%d tweets)", filename, len(tweets))
    return output_path


def _build_content_html(tweet: dict) -> str:
    """Build HTML content for a tweet entry."""
    parts = []

    parts.append(
        f'<p><strong>{tweet["author"]}</strong> '
        f'<a href="https://x.com/{tweet["handle"].lstrip("@")}">{tweet["handle"]}</a></p>'
    )

    text_html = tweet["text"].replace("\n", "<br>")
    parts.append(f"<p>{text_html}</p>")

    for img_url in tweet.get("images", []):
        parts.append(f'<p><img src="{img_url}" style="max-width:100%;" /></p>')

    # Category badge
    category = tweet.get("category", "other")
    try:
        label = CATEGORY_LABELS[Category(category)]
    except (ValueError, KeyError):
        label = category
    parts.append(f'<p><span style="background:#e0e0e0;padding:2px 8px;border-radius:4px;font-size:0.85em;">{label}</span></p>')

    parts.append(f'<p><a href="{tweet["url"]}">View on Twitter</a></p>')

    return "\n".join(parts)
