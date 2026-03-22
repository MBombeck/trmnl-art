"""TRMNL Art Display — FastAPI application.

Serves pre-processed, e-ink optimized images to TRMNL display.
Supports multiple art sources: goat-art (default), rijksmuseum, nasa, or mixed.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.config import ART_SOURCE, CURRENT_IMAGE, DATA_DIR, GOAT_GALLERY_DIR, INDEX_FILE
from app.scheduler import get_status, run_goat_art, run_nasa, run_rijksmuseum, start_scheduler

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("trmnl-art")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GOAT_GALLERY_DIR.mkdir(parents=True, exist_ok=True)

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

        # Copy goat gallery seed images
        goat_seed = seed_dir / "goat-gallery"
        if goat_seed.exists():
            for f in goat_seed.iterdir():
                dest = GOAT_GALLERY_DIR / f.name
                if not dest.exists():
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
    version="2.0.0",
    lifespan=lifespan,
)


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
    if ART_SOURCE == "goat-art":
        from app.goat_art import force_push
        run_goat_art_force()
        return {"status": "ok", "source": "goat-art", "message": "New goat art pushed"}
    elif ART_SOURCE == "nasa":
        run_nasa()
        return {"status": "ok", "source": "nasa", "message": "NASA APOD pushed"}
    elif ART_SOURCE == "rijksmuseum":
        run_rijksmuseum()
        return {"status": "ok", "source": "rijksmuseum", "message": "Rijksmuseum painting pushed"}
    else:
        run_rijksmuseum()
        return {"status": "ok", "source": "rijksmuseum", "message": "Rijksmuseum painting pushed"}


def run_goat_art_force():
    """Force a goat art push (bypasses daily limit)."""
    from app.goat_art import force_push
    from app.scheduler import _run_job
    _run_job("goat-art", force_push, skip_processing=True)


@app.get("/api/push/goat-art")
async def push_goat_art():
    """Manually trigger a goat art push (bypasses daily limit)."""
    run_goat_art_force()
    return {"status": "ok", "message": "Goat art pushed"}


@app.get("/api/push/rijksmuseum")
async def push_rijksmuseum():
    """Manually trigger a Rijksmuseum image push."""
    run_rijksmuseum()
    return {"status": "ok", "message": "Rijksmuseum image pushed"}


@app.get("/api/push/nasa")
async def push_nasa():
    """Manually trigger a NASA APOD push."""
    run_nasa()
    return {"status": "ok", "message": "NASA APOD pushed"}


@app.get("/api/status")
async def status():
    """Get detailed status information."""
    gallery_count = len(list(GOAT_GALLERY_DIR.glob("*.png"))) if GOAT_GALLERY_DIR.exists() else 0
    base_status = get_status()
    base_status["goat_gallery_count"] = gallery_count
    return base_status


@app.get("/api/build-index")
async def build_index(pages: int = 5):
    """Rebuild/extend the Rijksmuseum landscape index."""
    from app.sources import build_rijksmuseum_index
    index = build_rijksmuseum_index(max_pages=pages)
    return {"status": "ok", "total_paintings": len(index)}
