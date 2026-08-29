"""Admin auth: HMAC session cookies (browser login) + HTTP Basic (API fallback).

Public (no auth): GET /current.png, GET /health, the login page and the
auth endpoints under /api/auth/*. Everything else requires either
- a valid session cookie ``trmnl_session`` (set via /login), or
- valid HTTP Basic credentials (curl/scripting fallback).

Unauthenticated *browser* requests (Accept: text/html) are redirected to
/login?next=<path> instead of getting the ugly Basic-Auth popup; API
clients still get a 401 JSON. If ADMIN_PASSWORD is not configured the
protected routes fail closed with 503 and a German hint.

Session tokens are hand-rolled and stateless:
    base64url(JSON payload) + "." + base64url(HMAC-SHA256 signature)
with payload {"u": username, "exp": unix_ts}. The signing key is
SESSION_SECRET (env) or, as fallback, sha256("trmnl-session:" + ADMIN_PASSWORD)
— so rotating the admin password invalidates all sessions.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import ADMIN_USERNAME_DEFAULT

_basic = HTTPBasic(auto_error=False)

SESSION_COOKIE = "trmnl_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days

# --- Login rate limiting (in-memory, per IP) ---
RATE_LIMIT_WINDOW = 60.0  # seconds
RATE_LIMIT_MAX_FAILS = 5
_login_failures: dict[str, list[float]] = {}


def admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", "")


def admin_username() -> str:
    return os.environ.get("ADMIN_USERNAME", ADMIN_USERNAME_DEFAULT)


def _not_configured() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Admin-Zugang nicht konfiguriert: Bitte die Umgebungsvariable "
            "ADMIN_PASSWORD setzen (optional ADMIN_USERNAME, Standard 'marc') "
            "und den Dienst neu starten."
        ),
    )


# --- Session tokens ---


def _session_key() -> bytes:
    """HMAC key: SESSION_SECRET env or derived from ADMIN_PASSWORD."""
    secret = os.environ.get("SESSION_SECRET", "")
    if secret:
        return hashlib.sha256(secret.encode("utf-8")).digest()
    return hashlib.sha256(("trmnl-session:" + admin_password()).encode("utf-8")).digest()


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_session_token(username: str) -> str:
    """Signed, stateless session token: b64url(payload).b64url(hmac)."""
    payload = _b64u(
        json.dumps({"u": username, "exp": int(time.time()) + SESSION_MAX_AGE}).encode("utf-8")
    )
    sig = _b64u(hmac.new(_session_key(), payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_session_token(token: str | None) -> str | None:
    """Return the username for a valid, unexpired token — else None."""
    if not token or "." not in token or not admin_password():
        return None
    payload, sig = token.rsplit(".", 1)
    expected = _b64u(hmac.new(_session_key(), payload.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig.encode("ascii"), expected.encode("ascii")):
        return None
    try:
        data = json.loads(_b64u_decode(payload))
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("u"), str):
        return None
    if not isinstance(data.get("exp"), int) or data["exp"] < time.time():
        return None
    return data["u"]


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def set_session_cookie(response: Response, request: Request, username: str) -> None:
    """Attach a fresh 30-day session cookie (Secure only over https)."""
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(username),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# --- Rate limiting for password login ---


def check_login_rate_limit(ip: str) -> None:
    """Raise 429 (German) when an IP produced 5 failed logins within a minute."""
    now = time.time()
    fails = [t for t in _login_failures.get(ip, []) if now - t < RATE_LIMIT_WINDOW]
    _login_failures[ip] = fails
    if len(fails) >= RATE_LIMIT_MAX_FAILS:
        raise HTTPException(
            status_code=429,
            detail="Zu viele Fehlversuche. Bitte eine Minute warten und erneut versuchen.",
        )


def record_login_failure(ip: str) -> None:
    _login_failures.setdefault(ip, []).append(time.time())


def reset_login_rate_limit() -> None:
    """Test helper: forget all recorded failures."""
    _login_failures.clear()


# --- FastAPI dependency ---


def require_admin(
    request: Request, credentials: HTTPBasicCredentials | None = Depends(_basic)
) -> str:
    """Accept a valid session cookie OR valid HTTP Basic credentials.

    On failure: browsers (Accept: text/html) are redirected to /login,
    API clients get 401 JSON (with a Basic challenge for curl — unless a
    stale session cookie is present, to avoid browser popups).
    """
    password = admin_password()
    username = admin_username()

    if not password:
        # Fail closed: never expose the admin surface without a password.
        raise _not_configured()

    # (a) Session cookie (browser login / passkey)
    cookie_token = request.cookies.get(SESSION_COOKIE)
    session_user = verify_session_token(cookie_token)
    if session_user is not None:
        return session_user

    # (b) HTTP Basic (curl/scripting fallback)
    if credentials is not None and (
        secrets.compare_digest(credentials.username.encode("utf-8"), username.encode("utf-8"))
        & secrets.compare_digest(credentials.password.encode("utf-8"), password.encode("utf-8"))
    ):
        return username

    # Failure: browsers to the login page, APIs get 401 JSON.
    if "text/html" in request.headers.get("accept", ""):
        next_path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        raise HTTPException(
            status_code=302,
            detail="Anmeldung erforderlich",
            headers={"Location": f"/login?next={quote(next_path, safe='')}"},
        )
    headers = {}
    if not cookie_token:
        # Basic challenge only for cookie-less clients (curl); a browser
        # fetch with an expired session must not trigger the auth popup.
        headers["WWW-Authenticate"] = 'Basic realm="TRMNL Art Admin"'
    raise HTTPException(status_code=401, detail="Anmeldung erforderlich", headers=headers)
