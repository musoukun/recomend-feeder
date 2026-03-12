"""Twitter timeline scraper using Playwright."""
from __future__ import annotations

import json
import os
import sys
import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

logger = logging.getLogger(__name__)

# Default Chrome user data directory on Windows
CHROME_PROFILE_DIR = os.getenv(
    "CHROME_PROFILE_DIR",
    str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"),
)


def scrape_timeline(
    tweet_count: int = 50,
    headless: bool = True,
) -> list[dict]:
    """
    Scrape Twitter timeline using the user's existing Chrome profile.
    Chrome must be closed before running this.

    Returns:
        List of dicts with keys: author, handle, text, url, timestamp, images
    """
    tweets = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            CHROME_PROFILE_DIR,
            headless=headless,
            channel="chrome",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Navigate to home timeline
        page.goto("https://x.com/home", timeout=60000)
        time.sleep(5)

        # Check if logged in
        if "/login" in page.url or "/i/flow/login" in page.url:
            logger.error(
                "Twitterにログインされていません。"
                "まず普通のChromeでx.comにログインしてから、Chromeを閉じて再実行してください。"
            )
            context.close()
            return []

        logger.info("Logged in. Scraping timeline (target: %d tweets)...", tweet_count)

        # Wait for tweets to load
        try:
            page.wait_for_selector('article[data-testid="tweet"]', timeout=30000)
        except Exception:
            logger.error("No tweets found on timeline.")
            context.close()
            return []

        seen_urls = set()
        scroll_attempts = 0
        max_scroll_attempts = 20

        while len(tweets) < tweet_count and scroll_attempts < max_scroll_attempts:
            articles = page.query_selector_all('article[data-testid="tweet"]')

            for article in articles:
                try:
                    tweet = _parse_tweet_article(article)
                    if tweet and tweet["url"] not in seen_urls:
                        seen_urls.add(tweet["url"])
                        tweets.append(tweet)
                        if len(tweets) >= tweet_count:
                            break
                except Exception as e:
                    logger.debug("Failed to parse tweet: %s", e)
                    continue

            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)
            scroll_attempts += 1

        context.close()

    logger.info("Scraped %d tweets", len(tweets))
    return tweets


def _parse_tweet_article(article) -> dict | None:
    """Parse a single tweet article element into a dict."""
    # Author name
    author_el = article.query_selector('div[data-testid="User-Name"] a span')
    author = author_el.text_content() if author_el else "Unknown"

    # Handle (@username)
    handle_els = article.query_selector_all('div[data-testid="User-Name"] a')
    handle = ""
    for el in handle_els:
        href = el.get_attribute("href")
        if href and href.startswith("/"):
            handle = "@" + href.strip("/").split("/")[0]
            break

    # Tweet text
    text_el = article.query_selector('div[data-testid="tweetText"]')
    text = text_el.text_content() if text_el else ""

    if not text:
        return None

    # Tweet URL (from timestamp link)
    time_link = article.query_selector("a time")
    url = ""
    timestamp = ""
    if time_link:
        parent_a = time_link.evaluate_handle("el => el.parentElement")
        url = "https://x.com" + (parent_a.get_attribute("href") or "")
        timestamp = time_link.get_attribute("datetime") or ""

    if not url:
        return None

    # Images
    images = []
    img_els = article.query_selector_all('div[data-testid="tweetPhoto"] img')
    for img in img_els:
        src = img.get_attribute("src")
        if src and "pbs.twimg.com" in src:
            images.append(src)

    return {
        "author": author,
        "handle": handle,
        "text": text,
        "url": url,
        "timestamp": timestamp,
        "images": images,
    }
