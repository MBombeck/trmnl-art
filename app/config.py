import os
from pathlib import Path

# TRMNL
TRMNL_WEBHOOK_UUID = os.environ.get("TRMNL_WEBHOOK_UUID", "")
TRMNL_WEBHOOK_URL = f"https://trmnl.com/api/custom_plugins/{TRMNL_WEBHOOK_UUID}" if TRMNL_WEBHOOK_UUID else ""

# NASA
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

# Display
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
MIN_LANDSCAPE_RATIO = 1.2

# Schedules (cron-style)
RIJKSMUSEUM_CRON_HOUR = int(os.environ.get("RIJKSMUSEUM_HOUR", "5"))
NASA_CRON_HOUR = int(os.environ.get("NASA_HOUR", "12"))
TIMEZONE = os.environ.get("TZ", "Europe/Berlin")

# Data persistence
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
INDEX_FILE = DATA_DIR / "rijksmuseum-index.json"
HISTORY_FILE = DATA_DIR / "history.json"
CURRENT_IMAGE = DATA_DIR / "current.png"
LOG_FILE = DATA_DIR / "trmnl-art.log"

# App
APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
PORT = int(os.environ.get("PORT", "8000"))

# Self-healing
MAX_RETRIES = 3
RETRY_DELAY_MINUTES = 5
