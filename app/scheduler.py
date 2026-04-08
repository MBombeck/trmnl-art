"""Job scheduler with self-healing retry logic."""

import logging
import re
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import (
    ART_SOURCE,
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
from app.processing import process_image
from app.sources import fetch_nasa_image, fetch_rijksmuseum_image
from app.trmnl import push_to_trmnl

log = logging.getLogger("trmnl-art.scheduler")

# Job state tracking
job_status = {
    "rijksmuseum": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
    "nasa": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
    "goat-art": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
}


def _make_gallery_filename(description: str) -> str:
    """Convert description to a safe, unique filename."""
    name = re.sub(r'[^\w\s-]', '', description.lower())
    name = re.sub(r'[\s-]+', '_', name).strip('_')
    if not name:
        name = "image"
    date_suffix = datetime.now().strftime('%Y%m%d')
    return f"{name}_{date_suffix}.png"


def _run_job(source: str, fetch_fn, use_2bit: bool = True, skip_processing: bool = False):
    """Generic job runner with error handling and retry tracking."""
    status = job_status[source]
    status["last_run"] = datetime.now().isoformat()

    try:
        result = fetch_fn()
        if not result:
            raise RuntimeError(f"No image from {source}")

        img_data, description = result

        if skip_processing:
            # Goat art images are already 800x480 PNGs — just save directly
            png_bytes = img_data
        else:
            png_bytes, analysis = process_image(img_data, use_2bit=use_2bit)

        # Save as current image
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CURRENT_IMAGE.write_bytes(png_bytes)

        # Persist to source gallery
        try:
            gallery_fn = _make_gallery_filename(description)
            save_image(source, gallery_fn, png_bytes, description)
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
                _run_job(source, fetch_fn, use_2bit, skip_processing)
            t = threading.Thread(target=delayed_retry, daemon=True)
            t.start()
        else:
            log.error(f"Job {source} exhausted retries ({MAX_RETRIES})")


def run_goat_art():
    """Scheduled job: fetch and push goat art image."""
    from app.goat_art import fetch_goat_art
    _run_job("goat-art", fetch_goat_art, skip_processing=True)


def run_rijksmuseum():
    """Scheduled job: fetch and push Rijksmuseum painting."""
    _run_job("rijksmuseum", fetch_rijksmuseum_image)


def run_nasa():
    """Scheduled job: fetch and push NASA APOD."""
    _run_job("nasa", fetch_nasa_image)


scheduler = BackgroundScheduler(timezone=TIMEZONE)


def start_scheduler():
    """Start the background scheduler based on ART_SOURCE config."""
    if ART_SOURCE == "goat-art":
        scheduler.add_job(
            run_goat_art,
            CronTrigger(hour=GOAT_ART_CRON_HOUR, minute=GOAT_ART_CRON_MINUTE, timezone=TIMEZONE),
            id="goat_art_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(
            f"Scheduler started: Goat Art at {GOAT_ART_CRON_HOUR}:{GOAT_ART_CRON_MINUTE:02d} ({TIMEZONE})"
        )
    elif ART_SOURCE == "mixed":
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
            f"Scheduler started: Rijksmuseum at {RIJKSMUSEUM_CRON_HOUR}:{RIJKSMUSEUM_CRON_MINUTE:02d}, "
            f"NASA at {NASA_CRON_HOUR}:{NASA_CRON_MINUTE:02d} ({TIMEZONE})"
        )
    elif ART_SOURCE == "rijksmuseum":
        scheduler.add_job(
            run_rijksmuseum,
            CronTrigger(hour=RIJKSMUSEUM_CRON_HOUR, minute=RIJKSMUSEUM_CRON_MINUTE, timezone=TIMEZONE),
            id="rijksmuseum_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(f"Scheduler started: Rijksmuseum only at {RIJKSMUSEUM_CRON_HOUR}:{RIJKSMUSEUM_CRON_MINUTE:02d}")
    elif ART_SOURCE == "nasa":
        scheduler.add_job(
            run_nasa,
            CronTrigger(hour=NASA_CRON_HOUR, minute=NASA_CRON_MINUTE, timezone=TIMEZONE),
            id="nasa_daily",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        log.info(f"Scheduler started: NASA only at {NASA_CRON_HOUR}:{NASA_CRON_MINUTE:02d}")

    scheduler.start()


def get_status() -> dict:
    """Get current scheduler and job status."""
    next_runs = {}
    for job in scheduler.get_jobs():
        next_runs[job.id] = str(job.next_run_time) if job.next_run_time else None

    jobs = {}
    for source, status in job_status.items():
        job_id = f"{source.replace('-', '_')}_daily"
        jobs[source] = {**status, "next_run": next_runs.get(job_id)}

    return {
        "scheduler_running": scheduler.running,
        "art_source": ART_SOURCE,
        "jobs": jobs,
        "current_image_exists": CURRENT_IMAGE.exists(),
        "current_image_size_kb": round(CURRENT_IMAGE.stat().st_size / 1024, 1) if CURRENT_IMAGE.exists() else 0,
    }
