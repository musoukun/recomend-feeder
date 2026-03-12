"""Twitter timeline scraper using nodriver (undetected browser)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import nodriver as uc

logger = logging.getLogger(__name__)

AUTH_DIR = Path(__file__).parent.parent / "auth"
COOKIE_FILE = AUTH_DIR / "cookies.dat"
PROFILE_DIR = AUTH_DIR / "browser_profile"


async def _scrape_timeline(tweet_count: int = 50, headless: bool = True) -> list[dict]:
    """Scrape Twitter timeline. Prompts for login if needed."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    browser = await uc.start(
        user_data_dir=str(PROFILE_DIR),
        headless=False,  # Always start visible first
    )

    # Load saved cookies if available
    if COOKIE_FILE.exists():
        try:
            await browser.cookies.load(str(COOKIE_FILE))
            logger.info("Cookies loaded from %s", COOKIE_FILE)
        except Exception as e:
            logger.warning("Failed to load cookies: %s", e)

    tab = await browser.get("https://x.com/home")
    await tab.sleep(8)

    # Check if logged in
    current_url = await tab.evaluate("window.location.href")
    logger.info("Current URL: %s", current_url)

    if "/login" in current_url or "/i/flow/login" in current_url:
        print("\n=== Twitterにログインしてください ===")
        print("ブラウザでログイン後、ターミナルでEnterを押してください。\n")
        await asyncio.get_event_loop().run_in_executor(
            None, input, "ログイン完了したらEnterを押してください: "
        )
        # Re-check URL after login
        current_url = await tab.evaluate("window.location.href")
        if "/login" in current_url or "/i/flow/login" in current_url:
            logger.error("ログインできませんでした。")
            browser.stop()
            return []

    # Save cookies for next time
    try:
        await browser.cookies.save(str(COOKIE_FILE))
        logger.info("Cookies saved to %s", COOKIE_FILE)
    except Exception as e:
        logger.warning("Failed to save cookies: %s", e)

    logger.info("Logged in. Scraping timeline (target: %d tweets)...", tweet_count)

    # Wait for tweets to load
    try:
        await tab.select('article[data-testid="tweet"]', timeout=30)
    except Exception:
        logger.error("No tweets found on timeline.")
        browser.stop()
        return []

    tweets = []
    seen_urls = set()

    for scroll in range(20):
        if len(tweets) >= tweet_count:
            break

        # Get all tweet articles via JS
        raw_tweets = await tab.evaluate('''() => {
            const articles = document.querySelectorAll('article[data-testid="tweet"]');
            return Array.from(articles).map(article => {
                const authorEl = article.querySelector('div[data-testid="User-Name"] a span');
                const author = authorEl ? authorEl.textContent : 'Unknown';

                let handle = '';
                const handleEls = article.querySelectorAll('div[data-testid="User-Name"] a');
                for (const el of handleEls) {
                    const href = el.getAttribute('href');
                    if (href && href.startsWith('/')) {
                        handle = '@' + href.replace(/^\//, '').split('/')[0];
                        break;
                    }
                }

                const textEl = article.querySelector('div[data-testid="tweetText"]');
                const text = textEl ? textEl.textContent : '';

                const timeEl = article.querySelector('a time');
                let url = '';
                let timestamp = '';
                if (timeEl) {
                    const parentA = timeEl.parentElement;
                    url = 'https://x.com' + (parentA.getAttribute('href') || '');
                    timestamp = timeEl.getAttribute('datetime') || '';
                }

                const images = [];
                const imgEls = article.querySelectorAll('div[data-testid="tweetPhoto"] img');
                for (const img of imgEls) {
                    const src = img.getAttribute('src');
                    if (src && src.includes('pbs.twimg.com')) {
                        images.push(src);
                    }
                }

                return { author, handle, text, url, timestamp, images };
            });
        }''')

        for tweet in raw_tweets:
            if tweet["text"] and tweet["url"] and tweet["url"] not in seen_urls:
                seen_urls.add(tweet["url"])
                tweets.append(tweet)

        # Scroll down
        await tab.evaluate("window.scrollBy(0, 800)")
        await tab.sleep(2)

    browser.stop()
    logger.info("Scraped %d tweets", len(tweets))
    return tweets


def scrape_timeline(tweet_count: int = 50, headless: bool = True) -> list[dict]:
    """Sync wrapper for scraping."""
    return uc.loop().run_until_complete(_scrape_timeline(tweet_count, headless))
