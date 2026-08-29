# Dashboard & Gallery Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a web dashboard for managing all API controls, multi-source galleries with delete capability, and beautiful responsive frontend.

**Architecture:** New `gallery.py` handles CRUD for all three source galleries (goat-art, rijksmuseum, nasa). New `templates.py` contains all HTML/CSS/JS as Python string templates. `scheduler.py` is modified to persist every pushed image to its source gallery. `main.py` gets new routes for dashboard, gallery API, and delete operations.

**Tech Stack:** FastAPI, Pillow, vanilla JS (no framework), CSS Grid, fetch API

---

### Task 1: Gallery Manager — `app/gallery.py`

**Files:**
- Create: `app/gallery.py`

**What it does:** CRUD operations for multi-source image galleries. Each source (goat-art, rijksmuseum, nasa) has its own subdirectory under DATA_DIR. Images stored as PNG with companion JSON metadata.

- [ ] **Step 1: Create `app/gallery.py`**

```python
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
    """List gallery images, optionally filtered by source.
    
    Returns list of {filename, source, title, pushed_at, size_kb, url}.
    """
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
    
    log.info(f"Saved to {source} gallery: {filename} ({len(img_bytes)/1024:.0f} KB)")


def delete_image(source: str, filename: str) -> bool:
    """Delete an image + its metadata from a gallery. Returns True if deleted."""
    if source not in SOURCES:
        return False
    gallery_dir = GALLERY_DIRS[source]
    img_path = gallery_dir / filename
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
    path = GALLERY_DIRS[source] / filename
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
```

- [ ] **Step 2: Commit**

```bash
git add app/gallery.py
git commit -m "feat: add gallery manager with multi-source CRUD operations"
```

---

### Task 2: Config Updates — `app/config.py`

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add gallery directory constants**

Add after line 37 (`GOAT_GALLERY_DIR`):
```python
RIJKSMUSEUM_GALLERY_DIR = DATA_DIR / "rijksmuseum-gallery"
NASA_GALLERY_DIR = DATA_DIR / "nasa-gallery"
```

- [ ] **Step 2: Commit**

```bash
git add app/config.py
git commit -m "feat: add rijksmuseum and nasa gallery directory config"
```

---

### Task 3: Image Persistence in Scheduler — `app/scheduler.py`

**Files:**
- Modify: `app/scheduler.py`

**What it does:** After every successful image push, save the processed image to its source gallery.

- [ ] **Step 1: Modify `_run_job` to persist images**

After the line `CURRENT_IMAGE.write_bytes(png_bytes)` (line 58), add gallery save logic. Also need to generate a filename from the description.

Import `gallery` at top, then modify `_run_job`:

```python
from app.gallery import save_image
import re

def _make_filename(description: str) -> str:
    """Convert description to a safe filename."""
    name = re.sub(r'[^\w\s-]', '', description.lower())
    name = re.sub(r'[\s-]+', '_', name).strip('_')
    return f"{name}.png" if name else f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
```

In `_run_job`, after saving current image and before pushing to TRMNL:
```python
# Persist to source gallery
try:
    filename = _make_filename(description)
    save_image(source, filename, png_bytes, description)
except Exception as e:
    log.warning(f"Failed to save to gallery: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add app/scheduler.py
git commit -m "feat: persist every pushed image to source gallery"
```

---

### Task 4: Frontend Templates — `app/templates.py`

**Files:**
- Create: `app/templates.py`

This is the largest task. Contains all HTML/CSS/JS for dashboard and gallery as Python functions returning HTML strings.

- [ ] **Step 1: Create `app/templates.py` with dashboard and gallery HTML**

(Full code provided in implementation — dashboard with status cards, source selector, action buttons, job status; gallery with source filter dropdown, image grid with delete buttons, click-to-zoom)

- [ ] **Step 2: Commit**

```bash
git add app/templates.py
git commit -m "feat: add dashboard and gallery frontend templates"
```

---

### Task 5: New Routes in main.py

**Files:**
- Modify: `app/main.py`

**What it does:** Add routes for dashboard (/), gallery API, delete endpoint, source switching. Keep all existing endpoints.

- [ ] **Step 1: Add new imports and routes**

New routes:
- `GET /` — dashboard HTML
- `GET /gallery` — gallery HTML (replaces old gallery, now with source filter)
- `GET /api/galleries` — JSON list of all gallery images
- `GET /api/galleries/{source}` — JSON list for one source
- `GET /api/galleries/{source}/{filename}` — serve single image
- `DELETE /api/galleries/{source}/{filename}` — delete image
- `GET /api/source` — get current source
- `POST /api/source` — switch source (runtime only)

- [ ] **Step 2: Commit**

```bash
git add app/main.py
git commit -m "feat: add dashboard, gallery API, and delete routes"
```

---

### Task 6: Dockerfile Update

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Ensure new gallery dirs are created**

Add to the `RUN mkdir` line:
```dockerfile
RUN mkdir -p /app/data /app/data/goat-gallery /app/data/rijksmuseum-gallery /app/data/nasa-gallery
```

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "chore: add gallery directories to Dockerfile"
```

---

### Task 7: Push, Deploy & Verify

- [ ] **Step 1: Push to GitHub**
- [ ] **Step 2: Wait for Coolify auto-deploy**
- [ ] **Step 3: Verify health endpoint**
- [ ] **Step 4: Verify dashboard loads**
- [ ] **Step 5: Verify gallery loads with images**
- [ ] **Step 6: Verify delete works**
