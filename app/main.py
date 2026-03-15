"""TRMNL Art Display — FastAPI application.

Serves pre-processed, e-ink optimized images to TRMNL display.
Schedules daily art from Rijksmuseum (morning) and NASA APOD (noon).
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.config import CURRENT_IMAGE, DATA_DIR, INDEX_FILE, NASA_CRON_HOUR, RIJKSMUSEUM_CRON_HOUR
from app.scheduler import get_status, job_status, run_nasa, run_rijksmuseum, start_scheduler
from app.sources import build_rijksmuseum_index

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

    # Copy seed data on first run (from Docker image to persistent volume)
    seed_dir = Path("/app/data-seed")
    if seed_dir.exists() and not INDEX_FILE.exists():
        import shutil
        for f in seed_dir.iterdir():
            dest = DATA_DIR / f.name
            if not dest.exists():
                shutil.copy2(f, dest)
                log.info(f"Seeded {f.name}")

    # Build index on first run if it doesn't exist
    if not INDEX_FILE.exists():
        log.info("No Rijksmuseum index found, building initial index (5 pages)...")
        build_rijksmuseum_index(max_pages=5)

    # If no current image exists, push one immediately
    if not CURRENT_IMAGE.exists():
        log.info("No current image, running initial job...")
        hour = datetime.now().hour
        if 5 <= hour < 12:
            run_rijksmuseum()
        else:
            run_nasa()

    start_scheduler()
    log.info("TRMNL Art Display started")
    yield
    log.info("TRMNL Art Display shutting down")


app = FastAPI(
    title="TRMNL Art Display",
    description="Serves e-ink optimized art to TRMNL display",
    version="1.0.0",
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
    """Cycle to the next image. Switches source based on current one:
    - If last was NASA -> push Rijksmuseum
    - If last was Rijksmuseum -> push NASA
    - Default: use time of day
    """
    nasa_status = job_status["nasa"]
    rijks_status = job_status["rijksmuseum"]

    # Determine which source to use (opposite of last successful push)
    nasa_last = nasa_status.get("last_success") or ""
    rijks_last = rijks_status.get("last_success") or ""

    if nasa_last > rijks_last:
        run_rijksmuseum()
        return {"status": "ok", "source": "rijksmuseum", "message": "Switched to Rijksmuseum painting"}
    elif rijks_last > nasa_last:
        run_nasa()
        return {"status": "ok", "source": "nasa", "message": "Switched to NASA APOD"}
    else:
        hour = datetime.now().hour
        if RIJKSMUSEUM_CRON_HOUR <= hour < NASA_CRON_HOUR:
            run_rijksmuseum()
            return {"status": "ok", "source": "rijksmuseum", "message": "Rijksmuseum painting pushed"}
        else:
            run_nasa()
            return {"status": "ok", "source": "nasa", "message": "NASA APOD pushed"}


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
    return get_status()


@app.get("/api/build-index")
async def build_index(pages: int = 5):
    """Rebuild/extend the Rijksmuseum landscape index."""
    index = build_rijksmuseum_index(max_pages=pages)
    return {"status": "ok", "total_paintings": len(index)}
