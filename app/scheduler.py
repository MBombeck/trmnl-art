"""Job scheduler with self-healing retry logic.

The active source lives in data/settings.json (see app.state); switching it
via the API re-registers the cron jobs at runtime (reschedule()).
"""

import logging
import random
import re
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import (
    CURRENT_IMAGE,
    DATA_DIR,
    GOAT_ART_CRON_HOUR,
    GOAT_ART_CRON_MINUTE,
    MAX_RETRIES,
    NASA_CRON_HOUR,
    NASA_CRON_MINUTE,
    RETRY_DELAY_MINUTES,
    RIJKSMUSEUM_CRON_HOUR,
    RIJKSMUSEUM_CRON_MINUTE,
    TIMEZONE,
)
from app.gallery import save_image
from app.processing import encode_png, open_rgb, prepare_asset_image, render_display
from app.sources import fetch_nasa_image, fetch_rijksmuseum_image
from app.state import get_active_source
from app.trmnl import push_to_trmnl
from app.util import write_bytes_atomic

log = logging.getLogger("trmnl-art.scheduler")

# Job state tracking
job_status = {
    "rijksmuseum": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
    "nasa": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
    "goat-art": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
}

_JOB_IDS = ("goat_art_daily", "rijksmuseum_daily", "nasa_daily", "random_daily")


def _make_gallery_filename(description: str) -> str:
    """Convert description to a safe, unique filename."""
    name = re.sub(r'[^\w\s-]', '', description.lower())
    name = re.sub(r'[\s-]+', '_', name).strip('_')
    if not name:
        name = "image"
    date_suffix = datetime.now().strftime('%Y%m%d')
    return f"{name}_{date_suffix}.png"


def _run_job(source: str, fetch_fn):
    """Generic job runner with error handling and retry tracking.

    fetch_fn returns (img_bytes, description) for freshly fetched/generated
    images or (img_bytes, description, origin) where origin is "gallery" for
    images that were read from the gallery (those are NOT re-saved — this was
    the duplicate-per-push bug).
    """
    status = job_status[source]
    status["last_run"] = datetime.now().isoformat()

    try:
        result = fetch_fn()
        if not result:
            raise RuntimeError(f"No image from {source}")

        if len(result) == 3:
            img_data, description, origin = result
        else:
            img_data, description = result
            origin = "fresh"

        # Full pipeline: sanity decode -> trim borders + cover-fit 800x480
        # (skipped when already exact) -> e-ink grading for the display.
        img = prepare_asset_image(open_rgb(img_data))
        display_bytes = render_display(img)

        # Save as current image (atomic)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(CURRENT_IMAGE, display_bytes)

        # Persist fresh images to the source gallery (gallery-origin images
        # already live there — re-saving them created duplicates).
        if origin != "gallery":
            try:
                gallery_fn = _make_gallery_filename(description)
                save_image(source, gallery_fn, encode_png(img), description)
            except Exception as e:
                log.warning(f"Failed to save to gallery: {e}")

        # Push to TRMNL
        if not push_to_trmnl(description):
            raise RuntimeError("TRMNL push failed")

        status["last_success"] = datetime.now().isoformat()
        status["last_error"] = None
        status["retries"] = 0
        log.info(f"Job {source} completed: {description}")

    except Exception as e:
        status["last_error"] = str(e)
        status["retries"] += 1
        log.error(f"Job {source} failed (attempt {status['retries']}): {e}")

        # Self-healing: schedule retry if under max retries
        if status["retries"] <= MAX_RETRIES:
            log.info(f"Scheduling retry {status['retries']}/{MAX_RETRIES} in {RETRY_DELAY_MINUTES}min")
            import threading
            def delayed_retry():
                time.sleep(RETRY_DELAY_MINUTES * 60)
                _run_job(source, fetch_fn)
            t = threading.Thread(target=delayed_retry, daemon=True)
            t.start()
        else:
            log.error(f"Job {source} exhausted retries ({MAX_RETRIES})")


def run_goat_art():
    """Scheduled job: fetch and push goat art image."""
    from app.goat_art import fetch_goat_art
    _run_job("goat-art", fetch_goat_art)


def run_rijksmuseum():
    """Scheduled job: fetch and push Rijksmuseum painting."""
    _run_job("rijksmuseum", fetch_rijksmuseum_image)


def run_nasa():
    """Scheduled job: fetch and push NASA APOD."""
    _run_job("nasa", fetch_nasa_image)


def run_random():
    """Scheduled job for source 'random': pick one source per day."""
    source = random.choice(["goat-art", "rijksmuseum", "nasa"])
    log.info(f"Random source of the day: {source}")
    {"goat-art": run_goat_art, "rijksmuseum": run_rijksmuseum, "nasa": run_nasa}[source]()


scheduler = BackgroundScheduler(timezone=TIMEZONE)


def reschedule(source: str):
    """(Re-)register cron jobs for the given active source."""
    for job_id in _JOB_IDS:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    if source == "goat-art":
        scheduler.add_job(
            run_goat_art,
            CronTrigger(hour=GOAT_ART_CRON_HOUR, minute=GOAT_ART_CRON_MINUTE, timezone=TIMEZONE),
            id="goat_art_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(
            f"Schedule: Goat Art at {GOAT_ART_CRON_HOUR}:{GOAT_ART_CRON_MINUTE:02d} ({TIMEZONE})"
        )
    elif source == "mixed":
        # Legacy behavior: Rijksmuseum morning, NASA afternoon
        scheduler.add_job(
            run_rijksmuseum,
            CronTrigger(hour=RIJKSMUSEUM_CRON_HOUR, minute=RIJKSMUSEUM_CRON_MINUTE, timezone=TIMEZONE),
            id="rijksmuseum_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            run_nasa,
            CronTrigger(hour=NASA_CRON_HOUR, minute=NASA_CRON_MINUTE, timezone=TIMEZONE),
            id="nasa_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(
            f"Schedule: Rijksmuseum at {RIJKSMUSEUM_CRON_HOUR}:{RIJKSMUSEUM_CRON_MINUTE:02d}, "
            f"NASA at {NASA_CRON_HOUR}:{NASA_CRON_MINUTE:02d} ({TIMEZONE})"
        )
    elif source == "rijksmuseum":
        scheduler.add_job(
            run_rijksmuseum,
            CronTrigger(hour=RIJKSMUSEUM_CRON_HOUR, minute=RIJKSMUSEUM_CRON_MINUTE, timezone=TIMEZONE),
            id="rijksmuseum_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(f"Schedule: Rijksmuseum only at {RIJKSMUSEUM_CRON_HOUR}:{RIJKSMUSEUM_CRON_MINUTE:02d}")
    elif source == "nasa":
        scheduler.add_job(
            run_nasa,
            CronTrigger(hour=NASA_CRON_HOUR, minute=NASA_CRON_MINUTE, timezone=TIMEZONE),
            id="nasa_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(f"Schedule: NASA only at {NASA_CRON_HOUR}:{NASA_CRON_MINUTE:02d}")
    elif source == "random":
        scheduler.add_job(
            run_random,
            CronTrigger(hour=GOAT_ART_CRON_HOUR, minute=GOAT_ART_CRON_MINUTE, timezone=TIMEZONE),
            id="random_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(f"Schedule: random source daily at {GOAT_ART_CRON_HOUR}:{GOAT_ART_CRON_MINUTE:02d}")


def start_scheduler():
    """Start the background scheduler based on the persisted active source."""
    source = get_active_source()
    reschedule(source)
    if not scheduler.running:
        scheduler.start()
    log.info(f"Scheduler started (source: {source})")


def get_status() -> dict:
    """Get current scheduler and job status."""
    next_runs = {}
    for job in scheduler.get_jobs():
        # next_run_time is unset on pending jobs (scheduler not started yet)
        nrt = getattr(job, "next_run_time", None)
        next_runs[job.id] = str(nrt) if nrt else None

    jobs = {}
    for source, status in job_status.items():
        job_id = f"{source.replace('-', '_')}_daily"
        jobs[source] = {**status, "next_run": next_runs.get(job_id)}

    return {
        "scheduler_running": scheduler.running,
        "art_source": get_active_source(),
        "jobs": jobs,
        "next_runs": next_runs,
        "current_image_exists": CURRENT_IMAGE.exists(),
        "current_image_size_kb": round(CURRENT_IMAGE.stat().st_size / 1024, 1) if CURRENT_IMAGE.exists() else 0,
    }
