"""Google Spreadsheet writer via GAS Web App."""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


def push_to_spreadsheet(videos: list[dict]) -> bool:
    """Send video summaries to Google Spreadsheet via GAS Web App.

    Args:
        videos: List of video dicts with title, channel, url, summary, etc.

    Returns:
        True if successful.
    """
    gas_url = os.getenv("GAS_WEBAPP_URL")
    if not gas_url:
        logger.error("GAS_WEBAPP_URL not set in .env")
        return False

    rows = []
    for v in videos:
        rows.append({
            "video_id": v.get("video_id", ""),
            "title": v.get("title", ""),
            "channel": v.get("channel", ""),
            "url": v.get("url", ""),
            "duration": v.get("duration", 0),
            "upload_date": v.get("upload_date", ""),
            "summary": v.get("summary", ""),
            "has_subtitles": v.get("has_subtitles", False),
        })

    payload = json.dumps({"rows": rows}).encode("utf-8")

    req = urllib.request.Request(
        gas_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            logger.info("Spreadsheet response: %s", body[:200])
            return True
    except urllib.error.HTTPError as e:
        logger.error("GAS Web App error %d: %s", e.code, e.read().decode()[:200])
        return False
    except Exception as e:
        logger.error("Failed to push to spreadsheet: %s", e)
        return False
