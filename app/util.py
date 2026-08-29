"""Shared helpers: atomic file writes, hashing, slugs."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write bytes to path atomically (tmp file + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, obj) -> None:
    """Serialize obj as pretty JSON and write atomically."""
    write_bytes_atomic(Path(path), json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8"))


def read_json(path: Path, default=None):
    """Read a JSON file, returning default on any error."""
    path = Path(path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(text: str, max_len: int = 60) -> str:
    """Filesystem-safe slug: lowercase, word chars + underscores."""
    name = re.sub(r"[^\w\s-]", "", (text or "").lower())
    name = re.sub(r"[\s-]+", "_", name).strip("_")
    return name[:max_len].strip("_") or "bild"
