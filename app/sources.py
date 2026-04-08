"""Image sources: Rijksmuseum and NASA Image Library."""

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
)

log = logging.getLogger("trmnl-art.sources")

RIJKS_SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"
IIIF_BASE = "https://iiif.micr.io"
NASA_IMAGES_URL = "https://images-api.nasa.gov/search"

# Search terms that reliably return deep-space imagery
NASA_SEARCH_QUERIES = [
    "hubble galaxy",
    "webb nebula",
    "james webb deep field",
    "hubble nebula",
    "spiral galaxy",
    "supernova remnant",
    "planetary nebula",
    "galaxy cluster",
    "hubble deep field",
    "webb galaxy",
    "andromeda galaxy",
    "orion nebula",
    "crab nebula",
    "eagle nebula pillars",
    "saturn cassini",
    "jupiter juno",
    "mars surface rover",
    "earth from space",
]


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


# --- NASA Image Library ---


def fetch_nasa_image() -> tuple[bytes, str] | None:
    """Fetch a random deep-space image from NASA Image Library.

    Searches with curated space-related queries and picks an unshown image.
    No API key required. Returns (image_bytes, description) or None.
    """
    history = load_history()
    shown_ids = set(history.get("nasa", []))

    # Pick a random search query
    query = random.choice(NASA_SEARCH_QUERIES)

    try:
        r = requests.get(
            NASA_IMAGES_URL,
            params={"q": query, "media_type": "image", "page_size": 50},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error(f"NASA Image Library search failed: {e}")
        return None

    items = data.get("collection", {}).get("items", [])
    if not items:
        log.warning(f"No results for query '{query}'")
        return None

    # Filter to unshown images that have usable links
    candidates = []
    for item in items:
        item_data = item.get("data", [{}])[0]
        nasa_id = item_data.get("nasa_id", "")
        if not nasa_id or nasa_id in shown_ids:
            continue
        # Need image links
        links = item.get("links", [])
        if not links:
            continue
        candidates.append((item_data, links))

    if not candidates:
        # All shown for this query — reset history and try again
        log.info(f"All images shown for '{query}', resetting NASA history")
        history["nasa"] = []
        save_history(history)
        shown_ids = set()
        candidates = [
            (item.get("data", [{}])[0], item.get("links", []))
            for item in items
            if item.get("links") and item.get("data", [{}])[0].get("nasa_id")
        ]

    if not candidates:
        log.error("No usable NASA images found")
        return None

    # Pick a random candidate
    item_data, links = random.choice(candidates)
    nasa_id = item_data["nasa_id"]
    title = item_data.get("title", "NASA Space Image")

    # Get the best image URL — prefer ~large, fallback to preview href
    image_url = _get_nasa_image_url(nasa_id, links)
    if not image_url:
        log.error(f"No downloadable URL for {nasa_id}")
        return None

    try:
        r = requests.get(image_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Failed to download NASA image {nasa_id}: {e}")
        return None

    # Track by nasa_id
    history.setdefault("nasa", []).append(nasa_id)
    save_history(history)

    log.info(f"NASA: {title} [{nasa_id}] ({len(r.content) / 1024:.0f} KB)")
    return r.content, title


def _get_nasa_image_url(nasa_id: str, links: list[dict]) -> str | None:
    """Get the best image URL for a NASA image.

    Tries: large > medium > preview thumbnail from links.
    """
    # Try fetching the asset manifest for high-res versions
    try:
        r = requests.get(
            f"https://images-assets.nasa.gov/image/{nasa_id}/collection.json",
            timeout=10,
        )
        if r.status_code == 200:
            assets = r.json()
            # Prefer ~large.jpg, then ~medium.jpg, then ~orig.jpg
            for suffix in ("~large.jpg", "~medium.jpg", "~orig.jpg"):
                for url in assets:
                    if url.endswith(suffix):
                        return url
            # Any jpg that isn't thumb
            for url in assets:
                if url.endswith(".jpg") and "~thumb" not in url:
                    return url
    except Exception:
        pass

    # Fallback: use the preview href from search results
    for link in links:
        href = link.get("href", "")
        if href and href.startswith("http"):
            return href

    return None
