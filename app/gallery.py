"""Multi-source gallery manager — list, save, delete images with metadata."""

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


def ensure_dirs():
    """Create all gallery directories."""
    for d in GALLERY_DIRS.values():
        d.mkdir(parents=True, exist_ok=True)


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
    """Save an image + metadata to the source gallery."""
    if source not in SOURCES:
        raise ValueError(f"Unknown source: {source}")
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

    img_path.unlink()
    meta_path = gallery_dir / f"{img_path.stem}.json"
    if meta_path.exists():
        meta_path.unlink()

    log.info(f"Deleted from {source} gallery: {filename}")
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
