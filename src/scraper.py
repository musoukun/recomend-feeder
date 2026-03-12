"""Twitter timeline scraper using Playwright."""
from __future__ import annotations

import json
import os
import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

logger = logging.getLogger(__name__)

AUTH_DIR = Path(__file__).parent.parent / "auth"
COOKIE_FILE = AUTH_DIR / "cookies.json"


def save_cookies(page: Page) -> None:
    """Save browser cookies for session reuse."""
    AUTH_DIR.mkdir(exist_ok=True)
    cookies = page.context.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2))
    logger.info("Cookies saved to %s", COOKIE_FILE)


def load_cookies(page: Page) -> bool:
    """Load saved cookies if available."""
    if COOKIE_FILE.exists():
        cookies = json.loads(COOKIE_FILE.read_text())
        page.context.add_cookies(cookies)
        logger.info("Cookies loaded from %s", COOKIE_FILE)
        return True
    return False


def login_twitter(page: Page, username: str, password: str) -> None:
    """Log in to Twitter with username and password."""
    logger.info("Logging in to Twitter as %s", username)
    page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=60000)

    # Wait for any input field on the login form
    username_input = page.wait_for_selector(
        'input[autocomplete="username"], input[name="text"], input[type="text"]',
        timeout=30000,
    )
    time.sleep(1)
    username_input.click()
    page.keyboard.type(username, delay=50)
    time.sleep(0.5)

    # Click Next button
    next_btn = page.query_selector('[role="button"]:has-text("Next"), button:has-text("Next")')
    if next_btn:
        next_btn.click()
    else:
        page.keyboard.press("Enter")

    # Wait for either password field or verification step
    try:
        page.wait_for_selector(
            'input[type="password"], input[data-testid="ocfEnterTextTextInput"]',
            timeout=30000,
        )
    except Exception:
        # Debug: screenshot what's on screen
        screenshot_path = str(AUTH_DIR / "debug_login.png")
        AUTH_DIR.mkdir(exist_ok=True)
        page.screenshot(path=screenshot_path)
        logger.error("Login flow stuck. Screenshot saved to %s", screenshot_path)
        raise

    # Sometimes Twitter asks for phone/email verification
    verification_input = page.query_selector('input[data-testid="ocfEnterTextTextInput"]')
    if verification_input:
        logger.warning("Twitter is requesting additional verification.")
        verification_input.fill(username)
        page.click('button:has-text("Next")')
        page.wait_for_selector('input[type="password"]', timeout=30000)

    # Enter password
    page.fill('input[type="password"]', password)
    page.click('button[data-testid="LoginForm_Login_Button"]')

    # Verify login success
    page.wait_for_url("**/home", timeout=30000)
    logger.info("Login successful")
    save_cookies(page)


def scrape_timeline(
    username: str,
    password: str,
    tweet_count: int = 50,
    headless: bool = True,
) -> list[dict]:
    """
    Scrape Twitter timeline and return list of tweet dicts.

    Returns:
        List of dicts with keys: author, handle, text, url, timestamp, images
    """
    tweets = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Try cookie-based session first
        cookie_loaded = load_cookies(page)
        if cookie_loaded:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            # Check if we're actually logged in
            if "/login" in page.url or "/i/flow/login" in page.url:
                logger.info("Cookies expired, performing fresh login")
                login_twitter(page, username, password)
            else:
                logger.info("Session restored from cookies")
        else:
            login_twitter(page, username, password)

        # Scroll and collect tweets
        logger.info("Scraping timeline (target: %d tweets)...", tweet_count)
        seen_urls = set()
        scroll_attempts = 0
        max_scroll_attempts = 20

        while len(tweets) < tweet_count and scroll_attempts < max_scroll_attempts:
            # Find tweet articles
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

            # Scroll down
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)
            scroll_attempts += 1

        # Update cookies after scraping
        save_cookies(page)
        browser.close()

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
