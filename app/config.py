import os
from pathlib import Path

# TRMNL
TRMNL_WEBHOOK_UUID = os.environ.get("TRMNL_WEBHOOK_UUID", "")
TRMNL_WEBHOOK_URL = f"https://trmnl.com/api/custom_plugins/{TRMNL_WEBHOOK_UUID}" if TRMNL_WEBHOOK_UUID else ""

# Art source: "goat-art", "rijksmuseum", "nasa", or "mixed" (legacy behavior)
ART_SOURCE = os.environ.get("ART_SOURCE", "goat-art")

# Gemini API (for goat-art generation)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# NASA
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

# Display
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
MIN_LANDSCAPE_RATIO = 1.2

# Schedules (cron-style) — single daily push
GOAT_ART_CRON_HOUR = int(os.environ.get("GOAT_ART_HOUR", "6"))
GOAT_ART_CRON_MINUTE = int(os.environ.get("GOAT_ART_MINUTE", "0"))
RIJKSMUSEUM_CRON_HOUR = int(os.environ.get("RIJKSMUSEUM_HOUR", "5"))
RIJKSMUSEUM_CRON_MINUTE = int(os.environ.get("RIJKSMUSEUM_MINUTE", "0"))
NASA_CRON_HOUR = int(os.environ.get("NASA_HOUR", "14"))
NASA_CRON_MINUTE = int(os.environ.get("NASA_MINUTE", "30"))
TIMEZONE = os.environ.get("TZ", "Europe/Berlin")

# Data persistence
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
INDEX_FILE = DATA_DIR / "rijksmuseum-index.json"
HISTORY_FILE = DATA_DIR / "history.json"
CURRENT_IMAGE = DATA_DIR / "current.png"
LOG_FILE = DATA_DIR / "trmnl-art.log"
GOAT_GALLERY_DIR = DATA_DIR / "goat-gallery"
SETTINGS_FILE = DATA_DIR / "settings.json"
HASHES_FILE = DATA_DIR / "gallery-hashes.json"
MIGRATION_LOG_FILE = DATA_DIR / "migration-log.json"
PENDING_DIR = DATA_DIR / "pending"

# Admin auth. Read dynamically in app.security so tests can override at
# runtime — these are only documented defaults.
# Env vars: ADMIN_PASSWORD (required, fail-closed), ADMIN_USERNAME,
# SESSION_SECRET (optional; falls back to a key derived from ADMIN_PASSWORD),
# WEBAUTHN_RP_ID, WEBAUTHN_ORIGINS (comma-separated).
ADMIN_USERNAME_DEFAULT = "marc"
PASSKEYS_FILE = DATA_DIR / "passkeys.json"

# Tagesimpulse (separate container, reached via public Traefik route).
# Empty string disables the dashboard panel (used in tests).
TAGESIMPULSE_API_URL = os.environ.get(
    "TAGESIMPULSE_API_URL", "https://trmnl-art.bombeck.io/tagesimpulse/api/trmnl"
)
TAGESIMPULSE_BROWSER_URL = os.environ.get(
    "TAGESIMPULSE_BROWSER_URL", "https://trmnl-art.bombeck.io/tagesimpulse/"
)

# App
APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
PORT = int(os.environ.get("PORT", "8000"))

# Self-healing
MAX_RETRIES = 3
RETRY_DELAY_MINUTES = 5
