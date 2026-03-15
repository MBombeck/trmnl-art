"""E-ink image processing pipeline.

Optimizes photographs for 800x480 e-ink display with proper dithering,
contrast enhancement, and dark image compensation.

Based on TRMNL byos_fastapi PhotographicPlugin grading chain:
  autocontrast -> gamma -> shadow boost -> brightness -> autocontrast
"""

import logging
from io import BytesIO

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from app.config import DISPLAY_HEIGHT, DISPLAY_WIDTH

log = logging.getLogger("trmnl-art.processing")

# E-ink 2-bit grayscale palette (4 shades)
EINK_PALETTE_2BIT = [0x00, 0x55, 0xAA, 0xFF]


def analyze_brightness(img: Image.Image) -> dict:
    """Analyze image brightness and contrast for e-ink viability."""
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
    """Lift shadows while preserving highlights. From TRMNL PhotographicPlugin."""
    arr = np.array(img, dtype=np.float64)
    mask = arr < pivot
    arr[mask] = ((arr[mask] / pivot) ** shadow_gamma) * pivot
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_gamma(img: Image.Image, gamma: float) -> Image.Image:
    """Apply gamma correction. gamma < 1.0 brightens, > 1.0 darkens."""
    arr = np.array(img, dtype=np.float64) / 255.0
    arr = np.power(arr, gamma)
    return Image.fromarray((arr * 255).astype(np.uint8))


def grade_for_eink(img: Image.Image) -> Image.Image:
    """Full TRMNL-style photographic grading pipeline.

    Pipeline (from byos_fastapi PhotographicPlugin):
    1. autocontrast (clip 0.05% tails)
    2. gamma 1.2 (brighten midtones)
    3. shadow boost (pivot=180, gamma=0.65)
    4. brightness +10%
    5. final autocontrast
    """
    gray = img.convert("L")
    analysis = analyze_brightness(img)

    # For very dark images, apply aggressive gamma first
    if analysis["is_very_dark"]:
        log.info(f"Very dark image (mean={analysis['mean_brightness']:.0f}), applying gamma=0.45")
        gray = apply_gamma(gray, 0.45)
    elif analysis["is_dark"]:
        log.info(f"Dark image (mean={analysis['mean_brightness']:.0f}), applying gamma=0.6")
        gray = apply_gamma(gray, 0.6)

    # Step 1: autocontrast
    gray = ImageOps.autocontrast(gray, cutoff=0.05)

    # Step 2: gamma 1.2 (slight brighten)
    gray = apply_gamma(gray, 1 / 1.2)

    # Step 3: shadow boost
    gray = boost_shadows(gray, pivot=180, shadow_gamma=0.65)

    # Step 4: brightness +10%
    gray = ImageEnhance.Brightness(gray).enhance(1.1)

    # Step 5: final autocontrast
    gray = ImageOps.autocontrast(gray, cutoff=0.05)

    # Extra: sharpen to preserve detail before dithering
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.5, percent=100, threshold=2))

    return gray


def dither_floyd_steinberg(gray: Image.Image) -> Image.Image:
    """Apply Floyd-Steinberg dithering to produce 1-bit output."""
    return gray.convert("1")


def quantize_2bit(gray: Image.Image) -> Image.Image:
    """Quantize to 4-level grayscale with Floyd-Steinberg error diffusion.

    Uses manual Floyd-Steinberg since Pillow's quantize() doesn't handle
    small grayscale palettes well (maps most pixels to black).
    """
    levels = np.array(EINK_PALETTE_2BIT, dtype=np.float64)
    arr = np.array(gray, dtype=np.float64)
    h, w = arr.shape

    for y in range(h):
        for x in range(w):
            old_val = arr[y, x]
            # Find nearest palette level
            new_val = float(levels[np.argmin(np.abs(levels - old_val))])
            arr[y, x] = new_val
            err = old_val - new_val

            # Floyd-Steinberg error diffusion
            if x + 1 < w:
                arr[y, x + 1] += err * 7 / 16
            if y + 1 < h:
                if x - 1 >= 0:
                    arr[y + 1, x - 1] += err * 3 / 16
                arr[y + 1, x] += err * 5 / 16
                if x + 1 < w:
                    arr[y + 1, x + 1] += err * 1 / 16

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def process_image(img_data: bytes, use_2bit: bool = True) -> tuple[bytes, dict]:
    """Full pipeline: raw image bytes -> e-ink optimized PNG bytes.

    Args:
        img_data: Raw image bytes (JPEG, PNG, etc.)
        use_2bit: If True, produce 4-level grayscale. If False, 1-bit dithered.

    Returns:
        Tuple of (processed PNG bytes, analysis dict)
    """
    img = Image.open(BytesIO(img_data)).convert("RGB")
    analysis = analyze_brightness(img)

    # Resize to display dimensions
    img = resize_cover(img)

    # Grade for e-ink
    gray = grade_for_eink(img)

    # Dither/quantize
    if use_2bit:
        result = quantize_2bit(gray)
    else:
        result = dither_floyd_steinberg(gray).convert("L")

    # Save as optimized PNG
    buf = BytesIO()
    result.save(buf, format="PNG", optimize=True)
    png_bytes = buf.getvalue()

    log.info(
        f"Processed image: {img.size} -> {result.size}, "
        f"{'2-bit' if use_2bit else '1-bit'}, "
        f"{len(png_bytes)/1024:.0f} KB, "
        f"brightness={analysis['mean_brightness']:.0f}"
    )

    return png_bytes, analysis
