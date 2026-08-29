"""HTTP Basic auth for admin UI and mutating/leaky endpoints.

Public (no auth): GET /current.png, GET /health — everything else requires
credentials. If ADMIN_PASSWORD is not configured the protected routes fail
closed with 503 and a German hint.
"""

import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import ADMIN_USERNAME_DEFAULT

_basic = HTTPBasic(auto_error=False)


def require_admin(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> str:
    """FastAPI dependency: validate HTTP Basic credentials against env vars."""
    password = os.environ.get("ADMIN_PASSWORD", "")
    username = os.environ.get("ADMIN_USERNAME", ADMIN_USERNAME_DEFAULT)

    if not password:
        # Fail closed: never expose the admin surface without a password.
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin-Zugang nicht konfiguriert: Bitte die Umgebungsvariable "
                "ADMIN_PASSWORD setzen (optional ADMIN_USERNAME, Standard 'marc') "
                "und den Dienst neu starten."
            ),
        )

    ok = credentials is not None and (
        secrets.compare_digest(credentials.username.encode("utf-8"), username.encode("utf-8"))
        & secrets.compare_digest(credentials.password.encode("utf-8"), password.encode("utf-8"))
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Anmeldung erforderlich",
            headers={"WWW-Authenticate": 'Basic realm="TRMNL Art Admin"'},
        )
    return username
