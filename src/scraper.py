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
PROFILE_DIR = AUTH_DIR / "browser_profile"


async def _setup_login() -> None:
    """Open browser with persistent profile for manual Twitter login."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    browser = await uc.start(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
    )
    tab = await browser.get("https://x.com/login")

    print("\n=== ブラウザでTwitterにログインしてください ===")
    print("ログイン完了後、ホーム画面が表示されたらブラウザを閉じてください。\n")

    # Keep alive until user closes
    try:
        await tab
    except Exception:
        pass

    print("プロファイル保存完了!")


def setup_login() -> None:
    """Sync wrapper for manual login."""
    uc.loop().run_until_complete(_setup_login())


async def _scrape_timeline(tweet_count: int = 50, headless: bool = True) -> list[dict]:
    """Scrape Twitter timeline using saved browser profile."""
    if not PROFILE_DIR.exists():
        logger.error("プロファイルがありません。先に 'python main.py login' を実行してください。")
        return []

    browser = await uc.start(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
    )
    tab = await browser.get("https://x.com/home")
    await tab.sleep(5)

    # Check if logged in
    if "/login" in tab.url or "/i/flow/login" in tab.url:
        logger.error("Twitterにログインされていません。'python main.py login' を実行してください。")
        browser.stop()
        return []

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
