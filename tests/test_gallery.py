"""Tests for hash dedupe (save_image) and the startup migration."""

import os
import time
from io import BytesIO

from PIL import Image

from tests.conftest import make_png


def test_save_image_dedupes_identical_bytes():
    from app.gallery import GALLERY_DIRS, save_image
    data = make_png(800, 480)

    first = save_image("goat-art", "one.png", data, "Bild Eins")
    second = save_image("goat-art", "two.png", data, "Bild Zwei")

    assert first == "one.png"
    assert second == "one.png"  # returns existing filename
    pngs = list(GALLERY_DIRS["goat-art"].glob("*.png"))
    assert len(pngs) == 1
    assert pngs[0].name == "one.png"


def test_save_image_different_content_both_saved():
    from app.gallery import GALLERY_DIRS, save_image
    save_image("goat-art", "a.png", make_png(800, 480, color=(10, 20, 30)), "A")
    save_image("goat-art", "b.png", make_png(800, 480, color=(30, 20, 10)), "B")
    assert len(list(GALLERY_DIRS["goat-art"].glob("*.png"))) == 2


def test_migration_removes_duplicates_keeps_semantic_name():
    from app.gallery import GALLERY_DIRS, run_startup_migration
    d = GALLERY_DIRS["goat-art"]
    data = make_png(800, 480)

    semantic = d / "warhol_goat.png"
    dated = d / "warhol_goat_20250101.png"
    semantic.write_bytes(data)
    dated.write_bytes(data)
    (d / "warhol_goat_20250101.json").write_text("{}")
    # Same mtime => "close" => semantic name preferred
    now = time.time()
    os.utime(semantic, (now, now))
    os.utime(dated, (now, now))

    summary = run_startup_migration()

    assert summary["duplicates_removed"] == 1
    assert semantic.exists()
    assert not dated.exists()
    assert not (d / "warhol_goat_20250101.json").exists()


def test_migration_repairs_oversized_and_bordered_images():
    from app.config import MIGRATION_LOG_FILE
    from app.gallery import GALLERY_DIRS, run_startup_migration
    d = GALLERY_DIRS["goat-art"]

    (d / "big.png").write_bytes(make_png(1408, 768))
    (d / "bordered.png").write_bytes(make_png(800, 480, white_left=60))
    (d / "ok.png").write_bytes(make_png(800, 480))

    summary = run_startup_migration()

    assert summary["repaired"] == 2
    for name in ("big.png", "bordered.png", "ok.png"):
        img = Image.open(BytesIO((d / name).read_bytes()))
        assert img.size == (800, 480), name
    # White bar must be gone after repair
    bordered = Image.open(BytesIO((d / "bordered.png").read_bytes())).convert("RGB")
    assert bordered.getpixel((5, 240)) != (255, 255, 255)
    assert MIGRATION_LOG_FILE.exists()


def test_migration_is_idempotent():
    from app.gallery import GALLERY_DIRS, run_startup_migration
    d = GALLERY_DIRS["goat-art"]
    (d / "big.png").write_bytes(make_png(1408, 768))

    first = run_startup_migration()
    second = run_startup_migration()

    assert first["repaired"] == 1
    assert second["repaired"] == 0
    assert second["duplicates_removed"] == 0
