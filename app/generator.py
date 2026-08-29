"""On-demand image generator ("Bilder generieren").

Generates images via Imagen 4 Ultra, post-processes them (border trim +
cover-fit 800x480) and parks them as pending items in data/pending/ until
they are accepted into the goat gallery (optionally pushed) or discarded.
"""

import base64
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

import requests

from app import config
from app.config import CURRENT_IMAGE, PENDING_DIR
from app.gallery import save_image
from app.processing import (
    encode_png,
    open_rgb,
    prepare_asset_image,
    render_display,
)
from app.trmnl import push_to_trmnl
from app.util import read_json, sha256_hex, slugify, write_bytes_atomic, write_json_atomic

log = logging.getLogger("trmnl-art.generator")

# Modell konfigurierbar: imagen-4.0-generate-001 (Standard, ~halber Preis) reicht
# für 800×480-E-Ink; Ultra nur für maximale Detailtreue nötig.
IMAGEN_MODEL = os.environ.get("IMAGEN_MODEL", "imagen-4.0-generate-001")
IMAGEN_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{IMAGEN_MODEL}:predict"
)

DEFAULT_SUBJECT = "a cheerful goat"

# Strong anti-border instruction — Imagen sometimes bakes white bars into the frame.
ANTI_BORDER = (
    " Full-bleed composition filling the entire 16:9 frame edge to edge, no borders, "
    "no frames, no white margins, no letterboxing, subject fully inside the frame, "
    "nothing cropped at the edges. No watermark, no text, no signature."
)

STYLE_PRESETS: dict[str, dict[str, str]] = {
    "pop-art": {
        "label": "Pop-Art (Benday Dots)",
        "template": (
            "A bold Roy-Lichtenstein-style pop-art artwork of {subject}. Benday dots "
            "halftone shading, flat saturated primary colors, crisp black comic outlines, "
            "cheerful and energetic mood, vintage comic print texture."
        ),
    },
    "keith-haring": {
        "label": "Keith Haring",
        "template": (
            "A Keith Haring style artwork of {subject}. Thick black outlines, radiant "
            "energy lines, dancing simplified figures, playful flat primary colors on a "
            "white or single-color background, joyful street-art energy, friendly and "
            "cheerful mood."
        ),
    },
    "warhol": {
        "label": "Warhol Silkscreen (2x2)",
        "template": (
            "An Andy Warhol silkscreen pop-art grid: 2x2 panels of the same motif — "
            "{subject} — each panel in a different vivid color pair (pink/blue, "
            "yellow/red, green/orange, purple/lime). The FULL subject is visible in "
            "every panel: entire head and body completely inside each panel with a "
            "generous margin inside the panels, nothing cut off. Slight silkscreen "
            "misregistration, cheerful bold impact."
        ),
    },
    "lichtenstein-romance": {
        "label": "Lichtenstein Romance-Comic",
        "template": (
            "A romantic 1960s comic panel in Roy Lichtenstein's style showing {subject}. "
            "Benday dots, bold black outlines, flat dramatic colors, melodramatic "
            "lighting, no speech bubbles and no text, warm cheerful tone."
        ),
    },
}


class GeneratorError(Exception):
    """User-facing generation error (German message) with an HTTP status."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def preset_options() -> list[dict[str, str]]:
    """Style presets for the UI dropdown."""
    return [{"key": key, "label": val["label"]} for key, val in STYLE_PRESETS.items()]


def _build_prompt(style_preset: str | None, subject: str | None, custom_prompt: str | None) -> tuple[str, str]:
    """Return (prompt, title) from the request parameters."""
    custom_prompt = (custom_prompt or "").strip()
    subject = (subject or "").strip() or DEFAULT_SUBJECT

    if custom_prompt:
        return custom_prompt + ANTI_BORDER, custom_prompt[:80]

    if style_preset and style_preset not in STYLE_PRESETS:
        raise GeneratorError(f"Unbekanntes Stil-Preset: {style_preset}", status_code=400)
    key = style_preset or "pop-art"
    preset = STYLE_PRESETS[key]
    prompt = preset["template"].format(subject=subject) + ANTI_BORDER
    title = f"{subject} — {preset['label']}"
    return prompt, title


def _call_imagen(prompt: str) -> bytes:
    """Call Imagen 4 Ultra; returns raw image bytes or raises GeneratorError."""
    try:
        r = requests.post(
            f"{IMAGEN_API_URL}?key={config.GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {"sampleCount": 1, "aspectRatio": "16:9"},
            },
            timeout=120,
        )
    except requests.Timeout:
        raise GeneratorError(
            "Zeitüberschreitung bei der Bildgenerierung (120s). Bitte erneut versuchen.",
            status_code=504,
        )
    except requests.RequestException as e:
        raise GeneratorError(f"Imagen-API nicht erreichbar: {e}", status_code=502)

    if r.status_code == 429:
        # Echte Ursache durchreichen: Quota (später erneut) vs. leere Prepaid-Credits (aufladen)
        api_message = ""
        try:
            api_message = r.json().get("error", {}).get("message", "")
        except Exception:
            pass
        if "prepayment" in api_message.lower() or "credits" in api_message.lower():
            raise GeneratorError(
                "Gemini-Guthaben aufgebraucht — bitte unter https://ai.studio/projects "
                "Credits aufladen (Projekt → Billing).",
                status_code=429,
            )
        raise GeneratorError(
            "Imagen-Kontingent erschöpft (429). Bitte später erneut versuchen.",
            status_code=429,
        )
    if r.status_code != 200:
        log.error(f"Imagen API error ({r.status_code}): {r.text[:300]}")
        raise GeneratorError(
            f"Imagen-API-Fehler ({r.status_code}). Details im Server-Log.",
            status_code=502,
        )

    data = r.json()
    predictions = data.get("predictions", [])
    if not predictions or not predictions[0].get("bytesBase64Encoded"):
        reason = ""
        if predictions and predictions[0].get("raiFilteredReason"):
            reason = f" ({predictions[0]['raiFilteredReason']})"
        raise GeneratorError(
            "Imagen hat kein Bild geliefert — vermutlich Sicherheitsfilter"
            f"{reason}. Bitte den Prompt anpassen.",
            status_code=422,
        )

    return base64.b64decode(predictions[0]["bytesBase64Encoded"])


def create_pending(
    style_preset: str | None,
    subject: str | None,
    custom_prompt: str | None,
) -> dict:
    """Generate an image and store it as a pending item. Returns its meta."""
    if not config.GEMINI_API_KEY:
        raise GeneratorError(
            "Generator nicht konfiguriert: Umgebungsvariable GEMINI_API_KEY fehlt.",
            status_code=503,
        )

    prompt, title = _build_prompt(style_preset, subject, custom_prompt)
    raw = _call_imagen(prompt)

    # Post-process: sanity decode -> trim white bars -> cover-fit 800x480
    img = prepare_asset_image(open_rgb(raw))
    asset_bytes = encode_png(img)
    preview_bytes = render_display(img)  # e-ink graded preview

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    item_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    write_bytes_atomic(PENDING_DIR / f"{item_id}.png", asset_bytes)
    write_bytes_atomic(PENDING_DIR / f"{item_id}_preview.png", preview_bytes)

    meta = {
        "id": item_id,
        "prompt": prompt,
        "style": style_preset or ("custom" if (custom_prompt or "").strip() else "pop-art"),
        "subject": (subject or "").strip() or DEFAULT_SUBJECT,
        "title": title,
        "created_at": datetime.now().isoformat(),
    }
    write_json_atomic(PENDING_DIR / f"{item_id}.json", meta)
    log.info(f"Pending item created: {item_id} ({title})")
    return {**meta, "preview_url": f"/api/pending/{item_id}.png"}


def list_pending() -> list[dict]:
    """List pending items, newest first."""
    if not PENDING_DIR.exists():
        return []
    items = []
    for meta_path in sorted(PENDING_DIR.glob("*.json"), reverse=True):
        meta = read_json(meta_path, None)
        if not meta or not (PENDING_DIR / f"{meta.get('id', '')}.png").exists():
            continue
        items.append({**meta, "preview_url": f"/api/pending/{meta['id']}.png"})
    return items


def _pending_paths(item_id: str) -> tuple[Path, Path, Path] | None:
    """Resolve (asset, preview, meta) paths for an id, guarding traversal."""
    if not item_id or any(c in item_id for c in "/\\.") or not (PENDING_DIR / f"{item_id}.png").exists():
        return None
    return (
        PENDING_DIR / f"{item_id}.png",
        PENDING_DIR / f"{item_id}_preview.png",
        PENDING_DIR / f"{item_id}.json",
    )


def get_preview_path(item_id: str) -> Path | None:
    """Path to the graded preview PNG (falls back to the asset)."""
    paths = _pending_paths(item_id)
    if not paths:
        return None
    asset, preview, _ = paths
    return preview if preview.exists() else asset


def discard_pending(item_id: str) -> bool:
    """Delete a pending item and its files."""
    paths = _pending_paths(item_id)
    if not paths:
        return False
    for p in paths:
        if p.exists():
            p.unlink()
    log.info(f"Pending item discarded: {item_id}")
    return True


def accept_pending(item_id: str, push: bool = False) -> dict:
    """Move a pending item into the goat gallery (hash-dedupe aware).

    Optionally grades + pushes it to the TRMNL display immediately.
    """
    paths = _pending_paths(item_id)
    if not paths:
        raise GeneratorError("Unbekannte Pending-ID.", status_code=404)
    asset_path, preview_path, meta_path = paths
    meta = read_json(meta_path, {}) or {}
    title = meta.get("title") or "Generiertes Bild"

    # Semantic filename from subject/style
    style = slugify(meta.get("style") or "custom", max_len=24)
    subject = slugify(meta.get("subject") or meta.get("prompt") or "bild", max_len=40)
    base = f"gen_{style}_{subject}"
    gallery_dir = config.GOAT_GALLERY_DIR
    filename = f"{base}.png"
    n = 2
    asset_bytes = asset_path.read_bytes()
    while (gallery_dir / filename).exists() and sha256_hex((gallery_dir / filename).read_bytes()) != sha256_hex(asset_bytes):
        filename = f"{base}_{n}.png"
        n += 1

    saved = save_image("goat-art", filename, asset_bytes, title)

    pushed = False
    if push:
        display_bytes = render_display(open_rgb(asset_bytes))
        write_bytes_atomic(CURRENT_IMAGE, display_bytes)
        pushed = push_to_trmnl(title)

    # Clean up pending files
    for p in (asset_path, preview_path, meta_path):
        if p.exists():
            p.unlink()

    log.info(f"Pending item accepted: {item_id} -> {saved or filename} (pushed={pushed})")
    return {"filename": saved or filename, "title": title, "pushed": pushed}
