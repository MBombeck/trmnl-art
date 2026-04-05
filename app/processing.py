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

    Args:
        img_data: Raw image bytes (JPEG, PNG, etc.)
        use_2bit: Legacy parameter, ignored. Full-color output always.

    Returns:
        Tuple of (processed image bytes, analysis dict)
    """
    img = Image.open(BytesIO(img_data)).convert("RGB")
    analysis = analyze_brightness(img)

    # Resize to display dimensions
    img = resize_cover(img)

    # Grade for display (full-color)
    result = grade_for_display(img)

    # Save as optimized PNG
    buf = BytesIO()
    result.save(buf, format="PNG", optimize=True)
    out_bytes = buf.getvalue()

    # If PNG exceeds 1 MB, fall back to high-quality JPEG
    if len(out_bytes) > MAX_OUTPUT_BYTES:
        log.info(f"PNG too large ({len(out_bytes)/1024:.0f} KB), converting to JPEG q=90")
        buf = BytesIO()
        result.save(buf, format="JPEG", quality=90, optimize=True)
        out_bytes = buf.getvalue()

    log.info(
        f"Processed image: {result.size}, "
        f"full-color, "
        f"{len(out_bytes)/1024:.0f} KB, "
        f"brightness={analysis['mean_brightness']:.0f}"
    )

    return out_bytes, analysis
