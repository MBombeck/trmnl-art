"""TRMNL Art Display — FastAPI application.

Serves pre-processed, e-ink optimized images to TRMNL display.
Supports multiple art sources: goat-art (default), rijksmuseum, nasa, or mixed.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.config import ART_SOURCE, CURRENT_IMAGE, DATA_DIR, GOAT_GALLERY_DIR, INDEX_FILE
from app.gallery import (
    GALLERY_DIRS,
    SOURCES,
    delete_image,
    ensure_dirs,
    get_counts,
    get_image_path,
    list_images,
)
from app.scheduler import get_status, run_goat_art, run_nasa, run_rijksmuseum, start_scheduler
from app.templates import render_dashboard, render_gallery

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("trmnl-art")

# Runtime-switchable source (starts from env config)
_runtime_source = ART_SOURCE


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GOAT_GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    ensure_dirs()

    # Copy seed data on first run (from Docker image to persistent volume)
    seed_dir = Path("/app/data-seed")
    if seed_dir.exists():
        import shutil
        # Copy Rijksmuseum index if needed
        if not INDEX_FILE.exists():
            src = seed_dir / "rijksmuseum-index.json"
            if src.exists():
                shutil.copy2(src, INDEX_FILE)
                log.info("Seeded rijksmuseum-index.json")

        # Copy goat gallery seed images (skip blacklisted)
        from app.gallery import is_blacklisted
        goat_seed = seed_dir / "goat-gallery"
        if goat_seed.exists():
            for f in goat_seed.iterdir():
                dest = GOAT_GALLERY_DIR / f.name
                if not dest.exists() and not is_blacklisted("goat-art", f.stem):
                    shutil.copy2(f, dest)
            count = len(list(GOAT_GALLERY_DIR.glob("*.png")))
            log.info(f"Goat gallery: {count} images")

    # Build Rijksmuseum index if source needs it and it doesn't exist
    if ART_SOURCE in ("rijksmuseum", "mixed") and not INDEX_FILE.exists():
        from app.sources import build_rijksmuseum_index
        log.info("No Rijksmuseum index found, building initial index (5 pages)...")
        build_rijksmuseum_index(max_pages=5)

    # If no current image exists, push one immediately
    if not CURRENT_IMAGE.exists():
        log.info("No current image, running initial job...")
        if ART_SOURCE == "goat-art":
            run_goat_art()
        elif ART_SOURCE == "nasa":
            run_nasa()
        elif ART_SOURCE == "rijksmuseum":
            run_rijksmuseum()
        else:
            hour = datetime.now().hour
            if 5 <= hour < 12:
                run_rijksmuseum()
            else:
                run_nasa()

    start_scheduler()
    log.info(f"TRMNL Art Display started (source: {ART_SOURCE})")
    yield
    log.info("TRMNL Art Display shutting down")


app = FastAPI(
    title="TRMNL Art Display",
    description="Serves e-ink optimized art to TRMNL display",
    version="3.0.0",
    lifespan=lifespan,
)


# --- Dashboard ---


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard — overview and controls."""
    status = get_status()
    counts = get_counts()
    return render_dashboard(status, counts)


# --- Gallery UI ---


@app.get("/gallery", response_class=HTMLResponse)
async def gallery(source: str = "all"):
    """Gallery — browse all images with source filter."""
    if source != "all" and source not in SOURCES:
        source = "all"
    images = list_images(source if source != "all" else None)
    counts = get_counts()
    return render_gallery(images, counts, source)


# --- Gallery API ---


@app.get("/api/galleries")
async def api_galleries():
    """List all gallery images grouped by source."""
    images = list_images()
    counts = get_counts()
    return {"images": images, "counts": counts}


@app.get("/api/galleries/{source}")
async def api_gallery_source(source: str):
    """List images for a single source."""
    if source not in SOURCES:
        return JSONResponse({"error": f"Unknown source: {source}"}, status_code=404)
    images = list_images(source)
    return {"source": source, "count": len(images), "images": images}


@app.get("/api/galleries/{source}/{filename}")
async def api_gallery_image(source: str, filename: str):
    """Serve a single gallery image."""
    path = get_image_path(source, filename)
    if not path:
        return JSONResponse({"error": "Image not found"}, status_code=404)
    return FileResponse(path, media_type="image/png")


@app.delete("/api/galleries/{source}/{filename}")
async def api_gallery_delete(source: str, filename: str):
    """Delete a single gallery image."""
    if delete_image(source, filename):
        return {"status": "ok", "message": f"Deleted {filename} from {source}"}
    return JSONResponse({"error": "Image not found"}, status_code=404)


# --- Source switching ---


@app.get("/api/source")
async def api_get_source():
    """Get current art source."""
    global _runtime_source
    return {"source": _runtime_source}


@app.post("/api/source")
async def api_set_source(request: Request):
    """Switch art source at runtime."""
    global _runtime_source
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    new_source = body.get("source", "")
    if new_source not in SOURCES:
        return JSONResponse({"error": f"Unknown source: {new_source}"}, status_code=400)
    _runtime_source = new_source
    log.info(f"Art source switched to: {new_source}")
    return {"status": "ok", "source": new_source}


# --- Existing endpoints ---


@app.get("/current.png")
async def current_image():
    """Serve the current pre-processed image. This URL is what TRMNL fetches."""
    if not CURRENT_IMAGE.exists():
        return JSONResponse({"error": "No image available"}, status_code=404)
    return FileResponse(
        CURRENT_IMAGE,
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Length": str(CURRENT_IMAGE.stat().st_size),
        },
    )


@app.get("/health")
async def health():
    """Health check endpoint for monitoring."""
    status = get_status()
    healthy = status["scheduler_running"] and status["current_image_exists"]
    return JSONResponse(
        {
            "status": "healthy" if healthy else "degraded",
            "timestamp": datetime.now().isoformat(),
            **status,
        },
        status_code=200 if healthy else 503,
    )


@app.get("/api/next")
async def next_image():
    """Push the next image based on configured art source."""
    import asyncio
    global _runtime_source
    source = _runtime_source
    if source == "goat-art":
        await asyncio.get_event_loop().run_in_executor(None, run_goat_art_force)
        return {"status": "ok", "source": "goat-art", "message": "New goat art pushed"}
    elif source == "nasa":
        await asyncio.get_event_loop().run_in_executor(None, run_nasa)
        return {"status": "ok", "source": "nasa", "message": "NASA APOD pushed"}
    elif source == "rijksmuseum":
        await asyncio.get_event_loop().run_in_executor(None, run_rijksmuseum)
        return {"status": "ok", "source": "rijksmuseum", "message": "Rijksmuseum painting pushed"}
    else:
        await asyncio.get_event_loop().run_in_executor(None, run_rijksmuseum)
        return {"status": "ok", "source": "rijksmuseum", "message": "Rijksmuseum painting pushed"}


def run_goat_art_force():
    """Force a goat art push (bypasses daily limit)."""
    from app.goat_art import force_push
    from app.scheduler import _run_job
    _run_job("goat-art", force_push, skip_processing=True)


@app.get("/api/push/goat-art")
async def push_goat_art():
    """Manually trigger a goat art push (bypasses daily limit)."""
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, run_goat_art_force)
    return {"status": "ok", "message": "Goat art pushed"}


@app.get("/api/push/rijksmuseum")
async def push_rijksmuseum():
    """Manually trigger a Rijksmuseum image push."""
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, run_rijksmuseum)
    return {"status": "ok", "message": "Rijksmuseum image pushed"}


@app.get("/api/push/nasa")
async def push_nasa():
    """Manually trigger a NASA APOD push."""
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, run_nasa)
    return {"status": "ok", "message": "NASA APOD pushed"}


@app.get("/api/status")
async def status():
    """Get detailed status information."""
    global _runtime_source
    counts = get_counts()
    base_status = get_status()
    base_status["art_source"] = _runtime_source
    base_status["gallery_counts"] = counts
    return base_status


@app.get("/api/build-index")
async def build_index(pages: int = 5):
    """Rebuild/extend the Rijksmuseum landscape index (runs in background thread)."""
    import asyncio
    from app.sources import build_rijksmuseum_index

    loop = asyncio.get_event_loop()
    index = await loop.run_in_executor(None, lambda: build_rijksmuseum_index(max_pages=pages))
    return {"status": "ok", "total_paintings": len(index)}
