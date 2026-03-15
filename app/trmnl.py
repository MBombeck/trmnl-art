"""TRMNL webhook integration."""

import logging
from datetime import datetime

import requests

from app.config import APP_URL, TRMNL_WEBHOOK_URL

log = logging.getLogger("trmnl-art.trmnl")


def push_to_trmnl(description: str) -> bool:
    """Push the current image to TRMNL via webhook.

    Points TRMNL to our own served image URL at /current.png
    which is pre-processed and optimized for e-ink.
    """
    if not TRMNL_WEBHOOK_URL:
        log.error("TRMNL_WEBHOOK_UUID not configured")
        return False

    # Point TRMNL at our pre-processed image
    image_url = f"{APP_URL}/current.png"

    payload = {
        "merge_variables": {
            "image_url": image_url,
            "description": description,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    }

    try:
        r = requests.post(
            TRMNL_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            log.info(f"Pushed to TRMNL: {description}")
            return True
        log.error(f"TRMNL push failed ({r.status_code}): {r.text}")
        return False
    except Exception as e:
        log.error(f"TRMNL push error: {e}")
        return False
