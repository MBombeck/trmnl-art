"""Test setup: isolated DATA_DIR + auth env BEFORE any app import."""

import os
import shutil
import tempfile
from pathlib import Path

# Must happen before app.config is imported anywhere.
_TMP = Path(tempfile.mkdtemp(prefix="trmnl-art-test-"))
os.environ["DATA_DIR"] = str(_TMP)
os.environ["ADMIN_USERNAME"] = "marc"
os.environ["ADMIN_PASSWORD"] = "test-pass"
os.environ["TAGESIMPULSE_API_URL"] = ""  # no network in tests
os.environ["GEMINI_API_KEY"] = ""
os.environ["TRMNL_WEBHOOK_UUID"] = ""
os.environ["ART_SOURCE"] = "goat-art"

import pytest  # noqa: E402
from PIL import Image  # noqa: E402


AUTH = ("marc", "test-pass")


@pytest.fixture(autouse=True)
def clean_data_dir():
    """Wipe the shared DATA_DIR between tests and recreate gallery dirs."""
    for child in _TMP.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    from app.gallery import ensure_dirs
    from app.config import PENDING_DIR
    ensure_dirs()
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def client():
    """TestClient WITHOUT lifespan (no scheduler / no initial push)."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture
def auth():
    return AUTH


def make_png(width: int, height: int, color=(120, 60, 40), white_left: int = 0, white_top: int = 0) -> bytes:
    """Helper: solid PNG, optionally with white bars baked in on left/top."""
    import io
    img = Image.new("RGB", (width, height), color)
    if white_left:
        img.paste((255, 255, 255), (0, 0, white_left, height))
    if white_top:
        img.paste((255, 255, 255), (0, 0, width, white_top))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
