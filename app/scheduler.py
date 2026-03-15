"""Job scheduler with self-healing retry logic."""

import logging
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import (
    CURRENT_IMAGE,
    DATA_DIR,
    MAX_RETRIES,
    NASA_CRON_HOUR,
    RETRY_DELAY_MINUTES,
    RIJKSMUSEUM_CRON_HOUR,
    TIMEZONE,
)
from app.processing import process_image
from app.sources import fetch_nasa_image, fetch_rijksmuseum_image
from app.trmnl import push_to_trmnl

log = logging.getLogger("trmnl-art.scheduler")

# Job state tracking
job_status = {
    "rijksmuseum": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
    "nasa": {"last_run": None, "last_success": None, "last_error": None, "retries": 0},
}


def _run_job(source: str, fetch_fn, use_2bit: bool = True):
    """Generic job runner with error handling and retry tracking."""
    status = job_status[source]
    status["last_run"] = datetime.now().isoformat()

    try:
        result = fetch_fn()
        if not result:
            raise RuntimeError(f"No image from {source}")

        img_data, description = result
        png_bytes, analysis = process_image(img_data, use_2bit=use_2bit)

        # Save as current image
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CURRENT_IMAGE.write_bytes(png_bytes)

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
            scheduler.add_job(
                _run_job,
                "date",
                run_date=datetime.now().replace(second=0) if False else None,
                args=[source, fetch_fn, use_2bit],
                id=f"{source}_retry_{status['retries']}",
                replace_existing=True,
                misfire_grace_time=600,
            )
            # Use interval trigger for delay
            import threading
            def delayed_retry():
                time.sleep(RETRY_DELAY_MINUTES * 60)
                _run_job(source, fetch_fn, use_2bit)
            t = threading.Thread(target=delayed_retry, daemon=True)
            t.start()
        else:
            log.error(f"Job {source} exhausted retries ({MAX_RETRIES})")


def run_rijksmuseum():
    """Scheduled job: fetch and push Rijksmuseum painting."""
    _run_job("rijksmuseum", fetch_rijksmuseum_image)


def run_nasa():
    """Scheduled job: fetch and push NASA APOD."""
    _run_job("nasa", fetch_nasa_image)


scheduler = BackgroundScheduler(timezone=TIMEZONE)


def start_scheduler():
    """Start the background scheduler with cron jobs."""
    scheduler.add_job(
        run_rijksmuseum,
        CronTrigger(hour=RIJKSMUSEUM_CRON_HOUR, minute=0, timezone=TIMEZONE),
        id="rijksmuseum_daily",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        run_nasa,
        CronTrigger(hour=NASA_CRON_HOUR, minute=0, timezone=TIMEZONE),
        id="nasa_daily",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    log.info(
        f"Scheduler started: Rijksmuseum at {RIJKSMUSEUM_CRON_HOUR}:00, "
        f"NASA at {NASA_CRON_HOUR}:00 ({TIMEZONE})"
    )


def get_status() -> dict:
    """Get current scheduler and job status."""
    next_rijks = None
    next_nasa = None
    for job in scheduler.get_jobs():
        if job.id == "rijksmuseum_daily":
            next_rijks = str(job.next_run_time) if job.next_run_time else None
        elif job.id == "nasa_daily":
            next_nasa = str(job.next_run_time) if job.next_run_time else None

    return {
        "scheduler_running": scheduler.running,
        "jobs": {
            "rijksmuseum": {**job_status["rijksmuseum"], "next_run": next_rijks},
            "nasa": {**job_status["nasa"], "next_run": next_nasa},
        },
        "current_image_exists": CURRENT_IMAGE.exists(),
        "current_image_size_kb": round(CURRENT_IMAGE.stat().st_size / 1024, 1) if CURRENT_IMAGE.exists() else 0,
    }
