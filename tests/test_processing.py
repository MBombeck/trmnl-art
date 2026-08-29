"""Tests for trim_uniform_borders and the asset pipeline."""

from io import BytesIO

from PIL import Image

from tests.conftest import make_png


def _open(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data)).convert("RGB")


def test_trim_white_left_column():
    from app.processing import trim_uniform_borders
    img = _open(make_png(400, 300, white_left=51))
    out = trim_uniform_borders(img)
    assert out.size == (349, 300)


def test_trim_white_top_and_left():
    from app.processing import trim_uniform_borders
    img = _open(make_png(400, 300, white_left=40, white_top=20))
    out = trim_uniform_borders(img)
    assert out.size == (360, 280)


def test_trim_ignores_thin_edges():
    from app.processing import trim_uniform_borders
    img = _open(make_png(400, 300, white_left=5))
    out = trim_uniform_borders(img)
    assert out.size == (400, 300)


def test_trim_ignores_dark_borders():
    from app.processing import trim_uniform_borders
    img = Image.new("RGB", (400, 300), (10, 10, 10))
    out = trim_uniform_borders(img)
    assert out.size == (400, 300)


def test_prepare_asset_fits_oversized_to_display():
    from app.processing import prepare_asset_image
    img = _open(make_png(1408, 768))
    out = prepare_asset_image(img)
    assert out.size == (800, 480)


def test_prepare_asset_passthrough_exact_size():
    from app.processing import prepare_asset_image
    img = _open(make_png(800, 480, white_left=51))
    out = prepare_asset_image(img)
    # Exact display size: passed through untouched (no trim, no fit)
    assert out is img


def test_process_image_full_pipeline_outputs_display_size():
    from app.processing import process_image
    out_bytes, analysis = process_image(make_png(1408, 768, white_left=51))
    out = _open(out_bytes)
    assert out.size == (800, 480)
    assert "mean_brightness" in analysis
