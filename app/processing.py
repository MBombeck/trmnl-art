"""Image processing pipeline for TRMNL BWRY (4-color) display.

Prepares high-quality full-color PNGs for the TRMNL server, which handles
palette conversion to BWRY (black, white, red, yellow) itself.

Pipeline:
  resize -> autocontrast -> shadow boost -> contrast -> unsharp mask -> saturation boost
"""

import logging
from io import BytesIO

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from app.config import DISPLAY_HEIGHT, DISPLAY_WIDTH

log = logging.getLogger("trmnl-art.processing")

# Max output size in bytes (1 MB)
MAX_OUTPUT_BYTES = 1_000_000


def analyze_brightness(img: Image.Image) -> dict:
    """Analyze image brightness and contrast for processing decisions."""
    gray = img.convert("L")
    stat = ImageStat.Stat(gray)
    hist = gray.histogram()
    total = sum(hist)

    mean = stat.mean[0]
    stddev = stat.stddev[0]
    dark_ratio = sum(hist[:64]) / total
    light_ratio = sum(hist[192:]) / total

    return {
        "mean_brightness": mean,
        "contrast_stddev": stddev,
        "dark_ratio": dark_ratio,
        "light_ratio": light_ratio,
        "is_dark": mean < 70,
        "is_very_dark": mean < 40,
        "is_low_contrast": stddev < 30,
    }


def resize_cover(img: Image.Image, width: int = DISPLAY_WIDTH, height: int = DISPLAY_HEIGHT) -> Image.Image:
    """Resize image to fill target dimensions, center-crop excess (cover mode)."""
    return ImageOps.fit(img, (width, height), method=Image.LANCZOS, centering=(0.5, 0.5))


def trim_uniform_borders(
    img: Image.Image,
    threshold: int = 245,
    tolerance: float = 12.0,
    min_border: int = 8,
) -> Image.Image:
    """Crop near-uniform white/near-white bars from the image edges.

    A row/column counts as border when its mean luminance is >= threshold and
    its standard deviation is <= tolerance (near-uniform). Only runs of at
    least min_border pixels are cropped (Imagen sometimes bakes in white bars).
    """
    gray = np.asarray(img.convert("L"), dtype=np.float64)
    h, w = gray.shape

    def is_border(line: np.ndarray) -> bool:
        return bool(line.mean() >= threshold and line.std() <= tolerance)

    top = 0
    while top < h and is_border(gray[top]):
        top += 1
    bottom = 0
    while bottom < h - top and is_border(gray[h - 1 - bottom]):
        bottom += 1
    left = 0
    while left < w and is_border(gray[:, left]):
        left += 1
    right = 0
    while right < w - left and is_border(gray[:, w - 1 - right]):
        right += 1

    # Only crop substantial bars; thin white edges are usually image content.
    top = top if top >= min_border else 0
    bottom = bottom if bottom >= min_border else 0
    left = left if left >= min_border else 0
    right = right if right >= min_border else 0

    if not any((top, bottom, left, right)):
        return img

    new_w = w - left - right
    new_h = h - top - bottom
    # Sanity guard: never crop the image away almost entirely.
    if new_w < max(50, w // 4) or new_h < max(50, h // 4):
        log.warning(
            f"trim_uniform_borders: crop too aggressive ({new_w}x{new_h} from {w}x{h}), skipping"
        )
        return img

    log.info(f"Trimmed uniform borders: L{left} R{right} T{top} B{bottom} -> {new_w}x{new_h}")
    return img.crop((left, top, w - right, h - bottom))


def open_rgb(img_data: bytes) -> Image.Image:
    """Decode raw image bytes into an RGB image (sanity check included)."""
    return Image.open(BytesIO(img_data)).convert("RGB")


def prepare_asset_image(img: Image.Image) -> Image.Image:
    """Normalize an image to the display size 800x480.

    Images that are already exactly 800x480 are passed through untouched
    (they are considered finished assets); everything else gets uniform
    borders trimmed and is then cover-fitted (aspect-preserving) to 800x480.
    """
    if img.size == (DISPLAY_WIDTH, DISPLAY_HEIGHT):
        return img
    img = trim_uniform_borders(img)
    return resize_cover(img)


def encode_png(img: Image.Image) -> bytes:
    """Encode an image as optimized PNG bytes."""
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_display(img: Image.Image) -> bytes:
    """Grade an 800x480 asset for the e-ink display and encode it.

    Falls back to high-quality JPEG when the PNG exceeds 1 MB.
    """
    result = grade_for_display(img)
    out_bytes = encode_png(result)
    if len(out_bytes) > MAX_OUTPUT_BYTES:
        log.info(f"PNG too large ({len(out_bytes)/1024:.0f} KB), converting to JPEG q=90")
        buf = BytesIO()
        result.save(buf, format="JPEG", quality=90, optimize=True)
        out_bytes = buf.getvalue()
    return out_bytes


def boost_shadows(img: Image.Image, pivot: int = 180, shadow_gamma: float = 0.65) -> Image.Image:
    """Lift shadows while preserving highlights (operates on RGB)."""
    arr = np.array(img, dtype=np.float64)
    mask = arr < pivot
    arr[mask] = ((arr[mask] / pivot) ** shadow_gamma) * pivot
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_gamma(img: Image.Image, gamma: float) -> Image.Image:
    """Apply gamma correction. gamma < 1.0 brightens, > 1.0 darkens."""
    arr = np.array(img, dtype=np.float64) / 255.0
    arr = np.power(arr, gamma)
    return Image.fromarray((arr * 255).astype(np.uint8))


def grade_for_display(img: Image.Image) -> Image.Image:
    """Full-color grading pipeline optimized for BWRY display.

    Pipeline:
    1. Dark image compensation (gamma)
    2. Autocontrast (clip 0.05% tails)
    3. Shadow boost (pivot=180, gamma=0.65)
    4. Contrast +15%
    5. Unsharp mask (preserve detail)
    6. Color saturation +20% (makes reds and yellows pop on BWRY)
    """
    analysis = analyze_brightness(img)

    # For very dark images, apply aggressive gamma first
    if analysis["is_very_dark"]:
        log.info(f"Very dark image (mean={analysis['mean_brightness']:.0f}), applying gamma=0.45")
        img = apply_gamma(img, 0.45)
    elif analysis["is_dark"]:
        log.info(f"Dark image (mean={analysis['mean_brightness']:.0f}), applying gamma=0.6")
        img = apply_gamma(img, 0.6)

    # Step 1: autocontrast
    img = ImageOps.autocontrast(img, cutoff=0.05)

    # Step 2: shadow boost
    img = boost_shadows(img, pivot=180, shadow_gamma=0.65)

    # Step 3: contrast +15%
    img = ImageEnhance.Contrast(img).enhance(1.15)

    # Step 4: sharpen to preserve detail
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=100, threshold=2))

    # Step 5: boost color saturation +20% (reds/yellows pop on BWRY)
    img = ImageEnhance.Color(img).enhance(1.20)

    return img


def process_image(img_data: bytes, use_2bit: bool = True) -> tuple[bytes, dict]:
    """Full pipeline: raw image bytes -> display-optimized PNG bytes.

    trim uniform borders -> cover-fit 800x480 (skipped when already exact)
    -> e-ink grading -> PNG (JPEG fallback > 1 MB).

    Args:
        img_data: Raw image bytes (JPEG, PNG, etc.)
        use_2bit: Legacy parameter, ignored. Full-color output always.

    Returns:
        Tuple of (processed image bytes, analysis dict)
    """
    img = open_rgb(img_data)
    analysis = analyze_brightness(img)

    img = prepare_asset_image(img)
    out_bytes = render_display(img)

    log.info(
        f"Processed image: {img.size}, "
        f"full-color, "
        f"{len(out_bytes)/1024:.0f} KB, "
        f"brightness={analysis['mean_brightness']:.0f}"
    )

    return out_bytes, analysis
