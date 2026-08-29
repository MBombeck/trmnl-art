"""TRMNL Art Display — FastAPI application.

Serves pre-processed, e-ink optimized images to the TRMNL display.
Public (unauthenticated): GET /current.png, GET /health, the login page
(/login) and the auth endpoints under /api/auth/*. Everything else
(admin UI, gallery, generator, mutating APIs) requires a session cookie
(login page: password or WebAuthn passkey) or HTTP Basic auth as
curl/scripting fallback (ADMIN_USERNAME/ADMIN_PASSWORD, fail-closed).

NOTE: /tagesimpulse/* is served by a separate container via Traefik
PathPrefix — this app must never register routes under that prefix.
"""

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app import generator, state
from app.auth import list_credentials, router as auth_router
from app.config import (
    CURRENT_IMAGE,
    DATA_DIR,
    GOAT_GALLERY_DIR,
    INDEX_FILE,
    PENDING_DIR,
    TAGESIMPULSE_API_URL,
)
from app.gallery import (
    SOURCES,
    delete_image,
    ensure_dirs,
    get_counts,
    get_image_path,
    get_migration_summary,
    list_images,
    run_startup_migration,
)
from app.scheduler import get_status, run_goat_art, run_nasa, run_rijksmuseum, start_scheduler
from app.security import require_admin
from app.templates import render_dashboard, render_gallery
from app.util import write_bytes_atomic

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
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
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

    # Gallery migration: content-hash dedupe + size/border repair (idempotent)
    try:
        summary = run_startup_migration()
        if summary["duplicates_removed"] or summary["repaired"]:
            log.info(
                f"Migration: {summary['duplicates_removed']} duplicates removed, "
                f"{summary['repaired']} images repaired"
            )
    except Exception as e:
        log.error(f"Gallery migration failed: {e}")

    active_source = state.get_active_source()

    # Build Rijksmuseum index if source needs it and it doesn't exist
    if active_source in ("rijksmuseum", "mixed") and not INDEX_FILE.exists():
        from app.sources import build_rijksmuseum_index
        log.info("No Rijksmuseum index found, building initial index (5 pages)...")
        build_rijksmuseum_index(max_pages=5)

    # If no current image exists, push one immediately
    if not CURRENT_IMAGE.exists():
        log.info("No current image, running initial job...")
        if active_source == "goat-art":
            run_goat_art()
        elif active_source == "nasa":
            run_nasa()
        elif active_source == "rijksmuseum":
            run_rijksmuseum()
        elif active_source == "random":
            random.choice([run_goat_art, run_rijksmuseum, run_nasa])()
        else:
            hour = datetime.now().hour
            if 5 <= hour < 12:
                run_rijksmuseum()
            else:
                run_nasa()

    start_scheduler()
    log.info(f"TRMNL Art Display started (source: {active_source})")
    yield
    log.info("TRMNL Art Display shutting down")


app = FastAPI(
    title="TRMNL Art Display",
    description="Serves e-ink optimized art to TRMNL display",
    version="4.0.0",
    lifespan=lifespan,
)

# All admin/UI/API routes require auth: session cookie (browser login) or
# HTTP Basic (curl fallback), fail-closed without ADMIN_PASSWORD. Only
# /current.png, /health, /login and /api/auth/* stay public.
admin = APIRouter(dependencies=[Depends(require_admin)])


def _fetch_tagesimpulse() -> dict | None:
    """Fetch today's Tagesimpuls from the sibling container (graceful)."""
    if not TAGESIMPULSE_API_URL:
        return None
    try:
        r = requests.get(TAGESIMPULSE_API_URL, timeout=5)
        if r.status_code == 200:
            return r.json()
        log.warning(f"Tagesimpulse API returned {r.status_code}")
    except Exception as e:
        log.warning(f"Tagesimpulse API not reachable: {e}")
    return None


def _current_since() -> str | None:
    """When the current display image was last changed (file mtime)."""
    if not CURRENT_IMAGE.exists():
        return None
    return datetime.fromtimestamp(CURRENT_IMAGE.stat().st_mtime).strftime("%d.%m.%Y %H:%M")


# --- Dashboard (unified admin UI) ---


@admin.get("/", response_class=HTMLResponse)
def dashboard():
    """Unified dashboard — current image, controls, Tagesimpulse, generator."""
    status = get_status()
    counts = get_counts()
    return render_dashboard(
        status,
        counts,
        tagesimpulse=_fetch_tagesimpulse(),
        pending=generator.list_pending(),
        presets=generator.preset_options(),
        current_since=_current_since(),
        migration=get_migration_summary(),
        passkeys=list_credentials(),
    )


# --- Gallery UI ---


@admin.get("/gallery", response_class=HTMLResponse)
async def gallery(source: str = "all"):
    """Gallery — browse all images with source filter."""
    if source != "all" and source not in SOURCES:
        source = "all"
    images = list_images(source if source != "all" else None)
    counts = get_counts()
    return render_gallery(images, counts, source, migration=get_migration_summary())


# --- Gallery API ---


@admin.get("/api/galleries")
async def api_galleries():
    """List all gallery images grouped by source."""
    images = list_images()
    counts = get_counts()
    return {"images": images, "counts": counts}


@admin.get("/api/galleries/{source}")
async def api_gallery_source(source: str):
    """List images for a single source."""
    if source not in SOURCES:
        return JSONResponse({"error": f"Unknown source: {source}"}, status_code=404)
    images = list_images(source)
    return {"source": source, "count": len(images), "images": images}


@admin.get("/api/galleries/{source}/{filename}")
async def api_gallery_image(source: str, filename: str):
    """Serve a single gallery image."""
    path = get_image_path(source, filename)
    if not path:
        return JSONResponse({"error": "Image not found"}, status_code=404)
    return FileResponse(path, media_type="image/png")


@admin.delete("/api/galleries/{source}/{filename}")
async def api_gallery_delete(source: str, filename: str):
    """Delete a single gallery image."""
    if delete_image(source, filename):
        return {"status": "ok", "message": f"Deleted {filename} from {source}"}
    return JSONResponse({"error": "Image not found"}, status_code=404)


@admin.post("/api/galleries/{source}/{filename}/push")
async def api_gallery_push(source: str, filename: str):
    """Push a gallery image directly to TRMNL display."""
    from app.gallery import _load_meta
    from app.processing import open_rgb, prepare_asset_image, render_display
    from app.trmnl import push_to_trmnl
    path = get_image_path(source, filename)
    if not path:
        return JSONResponse({"error": "Image not found"}, status_code=404)
    # Sanity decode + grade for the display, then push (atomic write)
    img = prepare_asset_image(open_rgb(path.read_bytes()))
    write_bytes_atomic(CURRENT_IMAGE, render_display(img))
    meta = _load_meta(path)
    title = meta.get("title", path.stem.replace("_", " ").title())
    push_to_trmnl(title)
    return {"status": "ok", "message": f"Pushed to TRMNL: {title}"}


# --- Source switching (persisted + rescheduled) ---


@admin.get("/api/source")
async def api_get_source():
    """Get current art source."""
    return {"source": state.get_active_source()}


@admin.post("/api/source")
async def api_set_source(request: Request):
    """Switch art source at runtime: persist + re-register cron jobs."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    new_source = body.get("source", "")
    if new_source not in state.VALID_SOURCES:
        return JSONResponse({"error": f"Unknown source: {new_source}"}, status_code=400)
    state.set_active_source(new_source)
    from app.scheduler import reschedule
    reschedule(new_source)
    log.info(f"Art source switched to: {new_source}")
    return {"status": "ok", "source": new_source}


# --- Generator ("Bilder generieren") ---


@admin.post("/api/generate")
async def api_generate(request: Request):
    """Generate an image via Imagen 4 Ultra into the pending queue."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        item = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generator.create_pending(
                body.get("style_preset"),
                body.get("subject"),
                body.get("custom_prompt"),
            ),
        )
    except generator.GeneratorError as e:
        return JSONResponse({"detail": str(e)}, status_code=e.status_code)
    return {"id": item["id"], "preview_url": item["preview_url"], "title": item["title"]}


@admin.get("/api/pending")
async def api_pending_list():
    """List pending generated images."""
    return {"items": generator.list_pending()}


@admin.get("/api/pending/{item_id}.png")
async def api_pending_preview(item_id: str):
    """Serve the e-ink graded preview of a pending item."""
    path = generator.get_preview_path(item_id)
    if not path:
        return JSONResponse({"error": "Pending item not found"}, status_code=404)
    return FileResponse(path, media_type="image/png")


@admin.post("/api/pending/{item_id}/accept")
async def api_pending_accept(item_id: str, request: Request):
    """Accept a pending item into the goat gallery, optionally push it."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    push = bool(body.get("push", False))
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: generator.accept_pending(item_id, push=push)
        )
    except generator.GeneratorError as e:
        return JSONResponse({"detail": str(e)}, status_code=e.status_code)
    return {"status": "ok", **result}


@admin.delete("/api/pending/{item_id}")
async def api_pending_discard(item_id: str):
    """Discard a pending item."""
    if generator.discard_pending(item_id):
        return {"status": "ok"}
    return JSONResponse({"error": "Pending item not found"}, status_code=404)


# --- Public device endpoints (NO auth) ---


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


# --- Push / status APIs (auth required — they mutate or leak info) ---


@admin.get("/api/next")
async def next_image():
    """Push the next image based on the active art source."""
    source = state.get_active_source()
    if source in ("random", "mixed"):
        source = random.choice(["goat-art", "rijksmuseum", "nasa"])
    if source == "goat-art":
        await asyncio.get_event_loop().run_in_executor(None, run_goat_art_force)
        return {"status": "ok", "source": "goat-art", "message": "Neue Ziegen-Kunst gepusht"}
    elif source == "nasa":
        await asyncio.get_event_loop().run_in_executor(None, run_nasa)
        return {"status": "ok", "source": "nasa", "message": "NASA-Weltraumbild gepusht"}
    else:
        await asyncio.get_event_loop().run_in_executor(None, run_rijksmuseum)
        return {"status": "ok", "source": "rijksmuseum", "message": "Rijksmuseum-Gemälde gepusht"}


def run_goat_art_force():
    """Force a goat art push (bypasses daily limit)."""
    from app.goat_art import force_push
    from app.scheduler import _run_job
    _run_job("goat-art", force_push)


@admin.get("/api/push/goat-art")
async def push_goat_art():
    """Manually trigger a goat art push (bypasses daily limit)."""
    await asyncio.get_event_loop().run_in_executor(None, run_goat_art_force)
    return {"status": "ok", "message": "Ziegen-Kunst gepusht"}


@admin.get("/api/push/rijksmuseum")
async def push_rijksmuseum():
    """Manually trigger a Rijksmuseum image push."""
    await asyncio.get_event_loop().run_in_executor(None, run_rijksmuseum)
    return {"status": "ok", "message": "Rijksmuseum-Bild gepusht"}


@admin.get("/api/push/nasa")
async def push_nasa():
    """Manually trigger a NASA push."""
    await asyncio.get_event_loop().run_in_executor(None, run_nasa)
    return {"status": "ok", "message": "NASA-Bild gepusht"}


@admin.get("/api/status")
async def status():
    """Get detailed status information."""
    counts = get_counts()
    base_status = get_status()
    base_status["art_source"] = state.get_active_source()
    base_status["gallery_counts"] = counts
    base_status["pending_count"] = len(generator.list_pending())
    return base_status


@admin.get("/api/build-index")
async def build_index(pages: int = 5):
    """Rebuild/extend the Rijksmuseum landscape index (runs in background thread)."""
    from app.sources import build_rijksmuseum_index

    loop = asyncio.get_event_loop()
    index = await loop.run_in_executor(None, lambda: build_rijksmuseum_index(max_pages=pages))
    return {"status": "ok", "total_paintings": len(index)}


app.include_router(auth_router)
app.include_router(admin)
