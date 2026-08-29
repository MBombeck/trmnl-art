"""Multi-source gallery manager — list, save, delete images with metadata.

- Deleted images are tracked in a blacklist so they never reappear.
- A sha256 hash index (data/gallery-hashes.json) prevents duplicate images
  from being written twice into the same gallery.
- run_startup_migration() dedupes existing files by content hash and repairs
  images that are not 800x480 or carry baked-in uniform borders.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from app.config import (
    DATA_DIR,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    HASHES_FILE,
    MIGRATION_LOG_FILE,
)
from app.util import read_json, sha256_hex, write_bytes_atomic, write_json_atomic

log = logging.getLogger("trmnl-art.gallery")

SOURCES = ("goat-art", "rijksmuseum", "nasa")

GALLERY_DIRS = {
    "goat-art": DATA_DIR / "goat-gallery",
    "rijksmuseum": DATA_DIR / "rijksmuseum-gallery",
    "nasa": DATA_DIR / "nasa-gallery",
}

BLACKLIST_FILE = DATA_DIR / "deleted-images.json"

_DATE_SUFFIX_RE = re.compile(r"_\d{8}$")


def ensure_dirs():
    """Create all gallery directories."""
    for d in GALLERY_DIRS.values():
        d.mkdir(parents=True, exist_ok=True)


# --- Blacklist ---


def _load_blacklist() -> dict[str, list[str]]:
    """Load the deletion blacklist {source: [stem1, stem2, ...]}."""
    return read_json(BLACKLIST_FILE, {}) or {}


def _save_blacklist(bl: dict[str, list[str]]):
    write_json_atomic(BLACKLIST_FILE, bl)


def is_blacklisted(source: str, stem: str) -> bool:
    """Check if an image stem is blacklisted for a source."""
    bl = _load_blacklist()
    return stem in bl.get(source, [])


# --- Hash index (content dedupe) ---


def _load_hash_index() -> dict[str, dict[str, str]]:
    """Load {source: {sha256: filename}}."""
    return read_json(HASHES_FILE, {}) or {}


def _save_hash_index(idx: dict[str, dict[str, str]]):
    write_json_atomic(HASHES_FILE, idx)


def _rebuild_hash_index() -> dict[str, dict[str, str]]:
    """Rebuild the hash index from the files on disk (atomic write)."""
    idx: dict[str, dict[str, str]] = {}
    for src, d in GALLERY_DIRS.items():
        idx[src] = {}
        if not d.exists():
            continue
        for f in sorted(d.glob("*.png")):
            try:
                idx[src][sha256_hex(f.read_bytes())] = f.name
            except OSError as e:
                log.warning(f"Hash index: cannot read {f}: {e}")
    _save_hash_index(idx)
    return idx


# --- Listing / CRUD ---


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


def save_image(source: str, filename: str, img_bytes: bytes, title: str) -> str | None:
    """Save an image + metadata to the source gallery.

    Content-hash aware: when an identical image already exists in this
    gallery, nothing is written and the existing filename is returned.
    Blacklisted stems are skipped (returns None).
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source: {source}")
    stem = Path(filename).stem
    if is_blacklisted(source, stem):
        log.info(f"Skipping blacklisted image: {filename}")
        return None
    gallery_dir = GALLERY_DIRS[source]
    gallery_dir.mkdir(parents=True, exist_ok=True)

    digest = sha256_hex(img_bytes)
    idx = _load_hash_index()
    existing = idx.get(source, {}).get(digest)
    if existing and (gallery_dir / existing).exists():
        log.info(f"Dedupe: identical image already in {source} gallery as {existing}, skipping write")
        return existing

    img_path = gallery_dir / filename
    write_bytes_atomic(img_path, img_bytes)

    meta_path = gallery_dir / f"{stem}.json"
    write_json_atomic(meta_path, {
        "title": title,
        "source": source,
        "pushed_at": datetime.now().isoformat(),
        "filename": filename,
    })

    idx.setdefault(source, {})[digest] = filename
    _save_hash_index(idx)

    log.info(f"Saved to {source} gallery: {filename} ({len(img_bytes) / 1024:.0f} KB)")
    return filename


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
    try:
        digest = sha256_hex(img_path.read_bytes())
    except OSError:
        digest = None
    img_path.unlink()
    meta_path = gallery_dir / f"{stem}.json"
    if meta_path.exists():
        meta_path.unlink()

    # Drop from hash index
    if digest:
        idx = _load_hash_index()
        if idx.get(source, {}).get(digest) == filename:
            del idx[source][digest]
            _save_hash_index(idx)

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
    return read_json(img_path.with_suffix(".json"), {}) or {}


# --- Startup migration: content dedupe + size/border repair ---


def _pick_keeper(files: list[Path]) -> Path:
    """Choose which duplicate to keep: oldest mtime wins; when mtimes are
    close (<= 60s) prefer semantic names over *_YYYYMMDD date stems."""
    oldest = min(f.stat().st_mtime for f in files)
    close = [f for f in files if f.stat().st_mtime - oldest <= 60]
    semantic = [f for f in close if not _DATE_SUFFIX_RE.search(f.stem)]
    pool = semantic or close
    return min(pool, key=lambda f: (f.stat().st_mtime, f.name))


def run_startup_migration() -> dict:
    """One-time (idempotent) gallery cleanup, run at every startup.

    1. Dedupe: group files per gallery by sha256, keep one, delete the rest
       (including sidecar JSONs). Removed duplicates are NOT blacklisted.
    2. Repair: any image that is not exactly 800x480 or has uniform borders
       is trimmed + cover-fitted and re-saved under the same filename.
    3. Rebuild the hash index and write a summary to migration-log.json.
    """
    from app.processing import encode_png, open_rgb, resize_cover, trim_uniform_borders

    summary = {
        "ran_at": datetime.now().isoformat(),
        "duplicates_removed": 0,
        "repaired": 0,
        "removed_files": [],
        "repaired_files": [],
    }

    for src, d in GALLERY_DIRS.items():
        if not d.exists():
            continue

        # 1) Content dedupe
        by_hash: dict[str, list[Path]] = {}
        for f in sorted(d.glob("*.png")):
            try:
                by_hash.setdefault(sha256_hex(f.read_bytes()), []).append(f)
            except OSError as e:
                log.warning(f"Migration: cannot read {f}: {e}")
        for digest, files in by_hash.items():
            if len(files) < 2:
                continue
            keeper = _pick_keeper(files)
            for f in files:
                if f == keeper:
                    continue
                try:
                    f.unlink()
                    sidecar = f.with_suffix(".json")
                    if sidecar.exists():
                        sidecar.unlink()
                    summary["duplicates_removed"] += 1
                    summary["removed_files"].append(f"{src}/{f.name}")
                    log.info(f"Migration: removed duplicate {src}/{f.name} (kept {keeper.name})")
                except OSError as e:
                    log.warning(f"Migration: failed to remove {f}: {e}")

        # 2) Size/border repair
        for f in sorted(d.glob("*.png")):
            try:
                img = open_rgb(f.read_bytes())
            except Exception as e:
                log.warning(f"Migration: unreadable image {f}: {e}")
                continue
            trimmed = trim_uniform_borders(img)
            needs_fix = img.size != (DISPLAY_WIDTH, DISPLAY_HEIGHT) or trimmed.size != img.size
            if not needs_fix:
                continue
            if trimmed.size != (DISPLAY_WIDTH, DISPLAY_HEIGHT):
                trimmed = resize_cover(trimmed)
            write_bytes_atomic(f, encode_png(trimmed))
            summary["repaired"] += 1
            summary["repaired_files"].append(f"{src}/{f.name}")
            log.info(f"Migration: repaired {src}/{f.name} ({img.size} -> 800x480)")

    # 3) Rebuild index + persist summary
    _rebuild_hash_index()
    write_json_atomic(MIGRATION_LOG_FILE, summary)
    log.info(
        f"Gallery migration done: {summary['duplicates_removed']} duplicates removed, "
        f"{summary['repaired']} images repaired"
    )
    return summary


def get_migration_summary() -> dict | None:
    """Last migration summary (from data/migration-log.json) or None."""
    return read_json(MIGRATION_LOG_FILE, None)
