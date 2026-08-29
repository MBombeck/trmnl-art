"""Runtime settings persisted in data/settings.json (atomic writes).

Single source of truth for the active art source: the env var ART_SOURCE only
provides the initial default; dashboard/API switches persist here and the
scheduler reads from here.
"""

import logging

from app.config import ART_SOURCE, SETTINGS_FILE
from app.util import read_json, write_json_atomic

log = logging.getLogger("trmnl-art.state")

VALID_SOURCES = ("goat-art", "rijksmuseum", "nasa", "mixed", "random")


def get_active_source() -> str:
    """Active art source: settings.json wins, env ART_SOURCE is the fallback."""
    settings = read_json(SETTINGS_FILE, {}) or {}
    source = settings.get("art_source")
    if source in VALID_SOURCES:
        return source
    return ART_SOURCE if ART_SOURCE in VALID_SOURCES else "goat-art"


def set_active_source(source: str) -> None:
    """Persist the active art source (atomic)."""
    if source not in VALID_SOURCES:
        raise ValueError(f"Unknown source: {source}")
    settings = read_json(SETTINGS_FILE, {}) or {}
    settings["art_source"] = source
    write_json_atomic(SETTINGS_FILE, settings)
    log.info(f"Active source persisted: {source}")
