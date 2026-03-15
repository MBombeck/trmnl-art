"""Image sources: Rijksmuseum and NASA APOD."""

import json
import logging
import random
import time
from pathlib import Path

import requests

from app.config import (
    DATA_DIR,
    HISTORY_FILE,
    INDEX_FILE,
    MIN_LANDSCAPE_RATIO,
    NASA_API_KEY,
)

log = logging.getLogger("trmnl-art.sources")

RIJKS_SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"
IIIF_BASE = "https://iiif.micr.io"
NASA_APOD_URL = "https://api.nasa.gov/planetary/apod"


def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {"rijksmuseum": [], "nasa": []}


def save_history(history: dict):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))


# --- Rijksmuseum ---


def rijks_resolve_image(lod_id: str) -> dict | None:
    """Resolve LOD ID -> IIIF image info through the 3-step chain."""
    try:
        obj_id = lod_id.split("/")[-1]

        # Step 1: HumanMadeObject -> title, artist, VisualItem
        r = requests.get(lod_id, headers={"Accept": "application/ld+json"}, timeout=15)
        r.raise_for_status()
        obj = r.json()

        title = "Unknown"
        artist = "Unknown"
        for item in obj.get("identified_by", []):
            if item.get("type") == "Name" and item.get("content"):
                title = item["content"]
                break
        for ref in obj.get("produced_by", {}).get("referred_to_by", []):
            if ref.get("content"):
                artist = ref["content"]
                break

        shows = obj.get("shows", [])
        if not shows:
            return None
        vi_id = shows[0].get("id")
        if not vi_id:
            return None

        # Step 2: VisualItem -> DigitalObject
        time.sleep(0.3)
        r = requests.get(vi_id, headers={"Accept": "application/ld+json"}, timeout=15)
        r.raise_for_status()
        dsb = r.json().get("digitally_shown_by", [])
        if not dsb:
            return None

        # Step 3: DigitalObject -> IIIF URL
        time.sleep(0.3)
        r = requests.get(dsb[0]["id"], headers={"Accept": "application/ld+json"}, timeout=15)
        r.raise_for_status()
        ap = r.json().get("access_point", [])
        if not ap:
            return None
        iiif_id = ap[0]["id"].split("/")[3]

        # Check dimensions
        time.sleep(0.3)
        r = requests.get(f"{IIIF_BASE}/{iiif_id}/info.json", timeout=15)
        r.raise_for_status()
        info = r.json()
        w, h = info["width"], info["height"]

        return {
            "lod_id": lod_id,
            "obj_id": obj_id,
            "iiif_id": iiif_id,
            "title": title,
            "artist": artist,
            "width": w,
            "height": h,
            "is_landscape": w > h and (w / h) >= MIN_LANDSCAPE_RATIO,
        }
    except Exception as e:
        log.warning(f"Failed to resolve {lod_id}: {e}")
        return None


def build_rijksmuseum_index(max_pages: int = 50) -> list[dict]:
    """Build/extend the Rijksmuseum landscape painting index."""
    log.info("Building Rijksmuseum index...")
    index = []
    if INDEX_FILE.exists():
        index = json.loads(INDEX_FILE.read_text())
        log.info(f"Existing index: {len(index)} entries")

    known_ids = {e["lod_id"] for e in index}
    url = f"{RIJKS_SEARCH_URL}?type=painting&imageAvailable=true"

    for page in range(1, max_pages + 1):
        if not url:
            break
        log.info(f"Page {page}...")
        try:
            r = requests.get(url, headers={"Accept": "application/ld+json"}, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.error(f"Page {page} failed: {e}")
            break

        items = data.get("orderedItems", [])
        if not items:
            break

        for item in items:
            lod_id = item.get("id", "")
            if lod_id in known_ids:
                continue
            known_ids.add(lod_id)

            info = rijks_resolve_image(lod_id)
            if info and info["is_landscape"]:
                index.append(info)
                log.info(f"  + {info['title']} ({info['width']}x{info['height']}) [{info['artist']}]")

            time.sleep(0.5)

        # Save after each page
        INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False))

        nxt = data.get("next", {})
        url = nxt.get("id") if nxt else None

    log.info(f"Index complete: {len(index)} landscape paintings")
    return index


def fetch_rijksmuseum_image() -> tuple[bytes, str] | None:
    """Pick a random unshown landscape painting and download it.

    Returns (image_bytes, description) or None.
    """
    if not INDEX_FILE.exists():
        log.error("No Rijksmuseum index. Run build_rijksmuseum_index() first.")
        return None

    index = json.loads(INDEX_FILE.read_text())
    if not index:
        log.error("Empty index")
        return None

    history = load_history()
    shown = set(history.get("rijksmuseum", []))
    available = [p for p in index if p["iiif_id"] not in shown]

    if not available:
        log.info("All paintings shown, resetting history")
        history["rijksmuseum"] = []
        save_history(history)
        available = index

    painting = random.choice(available)

    # Download at 1200px wide (good quality for processing, not too large)
    image_url = f"{IIIF_BASE}/{painting['iiif_id']}/full/1200,/0/default.jpg"
    try:
        r = requests.get(image_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Failed to download {painting['title']}: {e}")
        return None

    desc = f"{painting['title']} — {painting['artist']}"
    history.setdefault("rijksmuseum", []).append(painting["iiif_id"])
    save_history(history)

    log.info(f"Rijksmuseum: {desc} ({len(r.content)/1024:.0f} KB)")
    return r.content, desc


# --- NASA APOD ---


def fetch_nasa_image() -> tuple[bytes, str] | None:
    """Get today's NASA APOD or a random unshown one.

    Returns (image_bytes, description) or None.
    """
    history = load_history()
    shown_dates = set(history.get("nasa", []))

    try:
        # Try today's APOD
        r = requests.get(NASA_APOD_URL, params={"api_key": NASA_API_KEY, "thumbs": "true"}, timeout=15)
        r.raise_for_status()
        apod = r.json()

        if apod.get("media_type") == "image" and apod.get("date") not in shown_dates:
            return _download_apod(apod, history)

        # Today is video or already shown — get random
        log.info("Today's APOD unavailable, fetching random...")
        r = requests.get(NASA_APOD_URL, params={"api_key": NASA_API_KEY, "count": 10, "thumbs": "true"}, timeout=15)
        r.raise_for_status()
        apods = r.json()

        if isinstance(apods, list):
            for apod in apods:
                if apod.get("media_type") == "image" and apod.get("date") not in shown_dates:
                    return _download_apod(apod, history)

        log.error("No suitable APOD found")
        return None

    except Exception as e:
        log.error(f"NASA APOD error: {e}")
        return None


def _download_apod(apod: dict, history: dict) -> tuple[bytes, str] | None:
    """Download an APOD image. Uses standard URL (not hdurl) for reasonable size."""
    image_url = apod.get("url", "")
    if not image_url or not image_url.startswith("http"):
        return None

    try:
        r = requests.get(image_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Failed to download APOD: {e}")
        return None

    desc = apod.get("title", "NASA APOD")
    history.setdefault("nasa", []).append(apod["date"])
    save_history(history)

    log.info(f"NASA APOD: {desc} ({apod['date']}, {len(r.content)/1024:.0f} KB)")
    return r.content, desc
