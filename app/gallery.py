"""Multi-source gallery manager — list, save, delete images with metadata.

Deleted images are tracked in a blacklist so they never reappear
(not from seed data, not from scheduled pushes, not from the gallery source).
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import DATA_DIR

log = logging.getLogger("trmnl-art.gallery")

SOURCES = ("goat-art", "rijksmuseum", "nasa")

GALLERY_DIRS = {
    "goat-art": DATA_DIR / "goat-gallery",
    "rijksmuseum": DATA_DIR / "rijksmuseum-gallery",
    "nasa": DATA_DIR / "nasa-gallery",
}

BLACKLIST_FILE = DATA_DIR / "deleted-images.json"


def ensure_dirs():
    """Create all gallery directories."""
    for d in GALLERY_DIRS.values():
        d.mkdir(parents=True, exist_ok=True)


def _load_blacklist() -> dict[str, list[str]]:
    """Load the deletion blacklist {source: [stem1, stem2, ...]}."""
    if BLACKLIST_FILE.exists():
        try:
            return json.loads(BLACKLIST_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_blacklist(bl: dict[str, list[str]]):
    BLACKLIST_FILE.write_text(json.dumps(bl, indent=2, ensure_ascii=False))


def is_blacklisted(source: str, stem: str) -> bool:
    """Check if an image stem is blacklisted for a source."""
    bl = _load_blacklist()
    return stem in bl.get(source, [])


def list_images(source: str | None = None) -> list[dict]:
    """List gallery images, optionally filtered by source."""
    sources = [source] if source and source in SOURCES else list(SOURCES)
    result = []
    for src in sources:
        gallery_dir = GALLERY_DIRS[src]
        if not gallery_dir.exists():
            continue
        for img in sorted(gallery_dir.glob("*.png")):
            meta = _load_meta(img)
            result.append({
                "filename": img.name,
                "source": src,
                "title": meta.get("title", img.stem.replace("_", " ").title()),
                "pushed_at": meta.get("pushed_at", ""),
                "size_kb": round(img.stat().st_size / 1024, 1),
                "url": f"/api/galleries/{src}/{img.name}",
            })
    return result


def save_image(source: str, filename: str, img_bytes: bytes, title: str):
    """Save an image + metadata to the source gallery. Skips blacklisted images."""
    if source not in SOURCES:
        raise ValueError(f"Unknown source: {source}")
    stem = Path(filename).stem
    if is_blacklisted(source, stem):
        log.info(f"Skipping blacklisted image: {filename}")
        return
    gallery_dir = GALLERY_DIRS[source]
    gallery_dir.mkdir(parents=True, exist_ok=True)

    img_path = gallery_dir / filename
    img_path.write_bytes(img_bytes)

    meta_path = gallery_dir / f"{Path(filename).stem}.json"
    meta_path.write_text(json.dumps({
        "title": title,
        "source": source,
        "pushed_at": datetime.now().isoformat(),
        "filename": filename,
    }, indent=2, ensure_ascii=False))

    log.info(f"Saved to {source} gallery: {filename} ({len(img_bytes) / 1024:.0f} KB)")


def delete_image(source: str, filename: str) -> bool:
    """Delete an image + its metadata from a gallery."""
    if source not in SOURCES:
        return False
    gallery_dir = GALLERY_DIRS[source]
    img_path = (gallery_dir / filename).resolve()
    if not img_path.is_relative_to(gallery_dir.resolve()):
        return False
    if not img_path.exists() or img_path.suffix != ".png":
        return False

    stem = img_path.stem
    img_path.unlink()
    meta_path = gallery_dir / f"{stem}.json"
    if meta_path.exists():
        meta_path.unlink()

    # Add to blacklist so it never comes back
    bl = _load_blacklist()
    bl.setdefault(source, [])
    if stem not in bl[source]:
        bl[source].append(stem)
    _save_blacklist(bl)

    log.info(f"Deleted + blacklisted from {source} gallery: {filename}")
    return True


def get_image_path(source: str, filename: str) -> Path | None:
    """Get the full path to a gallery image, or None if not found."""
    if source not in SOURCES:
        return None
    gallery_dir = GALLERY_DIRS[source]
    path = (gallery_dir / filename).resolve()
    if not path.is_relative_to(gallery_dir.resolve()):
        return None
    if path.exists() and path.suffix == ".png":
        return path
    return None


def get_counts() -> dict[str, int]:
    """Get image count per source."""
    counts = {}
    for src, d in GALLERY_DIRS.items():
        counts[src] = len(list(d.glob("*.png"))) if d.exists() else 0
    counts["total"] = sum(counts.values())
    return counts


def _load_meta(img_path: Path) -> dict:
    """Load metadata JSON for an image, or return empty dict."""
    meta_path = img_path.with_suffix(".json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception:
            pass
    return {}
