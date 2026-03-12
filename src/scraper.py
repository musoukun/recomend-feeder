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


async def _auto_login(tab, username: str, password: str) -> bool:
    """Attempt automatic Twitter login using nodriver."""
    try:
        # Wait for username input
        username_field = await tab.select('input[autocomplete="username"]', timeout=15)
        if not username_field:
            username_field = await tab.find("Phone, email, or username", best_match=True)

        if not username_field:
            logger.error("ユーザー名フィールドが見つかりません。")
            return False

        await username_field.send_keys(username)
        await tab.sleep(1)

        # Click Next
        next_btn = await tab.find("Next", best_match=True)
        if next_btn:
            await next_btn.click()
        await tab.sleep(3)

        # Check for additional verification (phone/email)
        verification_field = await tab.select('input[data-testid="ocfEnterTextTextInput"]', timeout=5)
        if verification_field:
            logger.info("追加認証を求められています。ユーザー名で応答します。")
            await verification_field.send_keys(username)
            next_btn2 = await tab.find("Next", best_match=True)
            if next_btn2:
                await next_btn2.click()
            await tab.sleep(3)

        # Enter password
        password_field = await tab.select('input[type="password"]', timeout=10)
        if not password_field:
            logger.error("パスワードフィールドが見つかりません。")
            return False

        await password_field.send_keys(password)
        await tab.sleep(1)

        # Click Log in
        login_btn = await tab.find("Log in", best_match=True)
        if login_btn:
            await login_btn.click()
        await tab.sleep(5)

        # Verify
        current_url = await tab.evaluate("window.location.href")
        if "/home" in current_url:
            logger.info("自動ログイン成功!")
            return True

        logger.warning("自動ログインに失敗。URL: %s", current_url)
        return False

    except Exception as e:
        logger.error("自動ログイン中にエラー: %s", e)
        return False


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
        logger.info("ログインしていません。自動ログインを試みます...")
        username = os.getenv("TWITTER_USERNAME")
        password = os.getenv("TWITTER_PASSWORD")

        if not username or not password:
            logger.error("TWITTER_USERNAME / TWITTER_PASSWORD が .env に設定されていません。")
            browser.stop()
            return []

        logged_in = await _auto_login(tab, username, password)
        if not logged_in:
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
    for attempt in range(15):
        count = await tab.evaluate(
            'document.querySelectorAll(\'article[data-testid="tweet"]\').length'
        )
        logger.info("Waiting for tweets... found %s (attempt %d)", count, attempt + 1)
        if count and count > 0:
            break
        await tab.sleep(2)
    else:
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

        if not raw_tweets:
            continue

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
