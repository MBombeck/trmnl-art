"""Auth routes: login page, password login, logout, WebAuthn passkeys.

Passkeys (py_webauthn) are bound to WEBAUTHN_RP_ID (default 'bombeck.io',
valid for trmnl.bombeck.io and trmnl-art.bombeck.io). Credentials live in
DATA_DIR/passkeys.json (atomic writes). Registration requires an existing
admin session; passkey login is public (it IS the login). All binary
WebAuthn fields travel base64url-encoded in JSON.
"""

import json
import logging
import os
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from app.config import PASSKEYS_FILE
from app.security import (
    admin_password,
    admin_username,
    check_login_rate_limit,
    clear_session_cookie,
    record_login_failure,
    require_admin,
    set_session_cookie,
    verify_session_token,
    SESSION_COOKIE,
    _not_configured,
)
from app.templates import render_login
from app.util import read_json, write_json_atomic

log = logging.getLogger("trmnl-art.auth")

router = APIRouter()

RP_NAME = "TRMNL Admin"
CHALLENGE_TTL = 300  # seconds

# Short-lived WebAuthn challenges: state_id -> (challenge, kind, expires_at)
_challenges: dict[str, tuple[bytes, str, float]] = {}


def rp_id() -> str:
    return os.environ.get("WEBAUTHN_RP_ID", "bombeck.io")


def allowed_origins() -> list[str]:
    raw = os.environ.get(
        "WEBAUTHN_ORIGINS", "https://trmnl.bombeck.io,https://trmnl-art.bombeck.io"
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


# --- Challenge store (in-memory, 5-min TTL) ---


def _store_challenge(challenge: bytes, kind: str) -> str:
    now = time.time()
    for key in [k for k, (_, _, exp) in _challenges.items() if exp < now]:
        _challenges.pop(key, None)
    state = secrets.token_urlsafe(24)
    _challenges[state] = (challenge, kind, now + CHALLENGE_TTL)
    return state


def _pop_challenge(state: str, kind: str) -> bytes | None:
    entry = _challenges.pop(state or "", None)
    if not entry:
        return None
    challenge, stored_kind, expires_at = entry
    if stored_kind != kind or expires_at < time.time():
        return None
    return challenge


def reset_challenges() -> None:
    """Test helper."""
    _challenges.clear()


# --- Credential storage (DATA_DIR/passkeys.json) ---


def list_credentials() -> list[dict]:
    creds = read_json(PASSKEYS_FILE, [])
    return creds if isinstance(creds, list) else []


def _save_credentials(creds: list[dict]) -> None:
    write_json_atomic(PASSKEYS_FILE, creds)


def _public_credential(cred: dict) -> dict:
    """Credential metadata safe to expose to the frontend."""
    return {
        "id": cred.get("id", ""),
        "label": cred.get("label", "Passkey"),
        "created_at": cred.get("created_at", ""),
        "transports": cred.get("transports", []),
    }


# --- Login page ---


def _safe_next(next_path: str | None) -> str:
    """Only same-site absolute paths — no open redirects."""
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    """Login page (public). Already logged in? Straight to the target."""
    target = _safe_next(next)
    if verify_session_token(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse(target, status_code=302)
    return render_login(next_path=target, has_passkeys=bool(list_credentials()))


# --- Password login / logout ---


@router.post("/api/auth/login")
async def api_login(request: Request):
    """Password login → session cookie. Rate-limited: 5 fails/min per IP."""
    if not admin_password():
        raise _not_configured()
    ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(ip)
    try:
        body = await request.json()
    except Exception:
        body = {}
    given = body.get("password", "")
    if not isinstance(given, str) or not secrets.compare_digest(
        given.encode("utf-8"), admin_password().encode("utf-8")
    ):
        record_login_failure(ip)
        log.warning(f"Failed password login from {ip}")
        raise HTTPException(status_code=401, detail="Falsches Passwort")
    response = JSONResponse({"status": "ok", "user": admin_username()})
    set_session_cookie(response, request, admin_username())
    return response


@router.post("/api/auth/logout")
def api_logout(user: str = Depends(require_admin)):
    """Clear the session cookie."""
    response = JSONResponse({"status": "ok"})
    clear_session_cookie(response)
    return response


# --- WebAuthn: registration (requires an existing admin session) ---


@router.post("/api/auth/webauthn/register/options")
def webauthn_register_options(user: str = Depends(require_admin)):
    """Registration ceremony options (only for logged-in admins)."""
    options = generate_registration_options(
        rp_id=rp_id(),
        rp_name=RP_NAME,
        user_id=admin_username().encode("utf-8"),
        user_name=admin_username(),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"]))
            for c in list_credentials()
            if c.get("id")
        ],
    )
    state = _store_challenge(options.challenge, "register")
    return {"state": state, "options": json.loads(options_to_json(options))}


@router.post("/api/auth/webauthn/register/verify")
async def webauthn_register_verify(request: Request, user: str = Depends(require_admin)):
    """Verify the attestation and persist the new passkey."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    challenge = _pop_challenge(body.get("state", ""), "register")
    if challenge is None:
        raise HTTPException(
            status_code=400, detail="Challenge abgelaufen — bitte erneut versuchen."
        )
    try:
        verified = verify_registration_response(
            credential=body.get("credential") or {},
            expected_challenge=challenge,
            expected_rp_id=rp_id(),
            expected_origin=allowed_origins(),
        )
    except Exception as e:
        log.warning(f"Passkey registration failed: {e}")
        raise HTTPException(status_code=400, detail="Passkey-Registrierung fehlgeschlagen.")

    label = str(body.get("label") or "").strip()[:60] or "Passkey"
    cred = {
        "id": bytes_to_base64url(verified.credential_id),
        "public_key": bytes_to_base64url(verified.credential_public_key),
        "sign_count": verified.sign_count,
        "transports": [str(t) for t in (body.get("transports") or []) if isinstance(t, str)],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
    }
    creds = [c for c in list_credentials() if c.get("id") != cred["id"]]
    creds.append(cred)
    _save_credentials(creds)
    log.info(f"Passkey registered: {label}")
    return {"status": "ok", "credential": _public_credential(cred)}


# --- WebAuthn: authentication (public — this IS the login) ---


@router.post("/api/auth/webauthn/login/options")
def webauthn_login_options():
    """Authentication ceremony options with the registered credentials."""
    if not admin_password():
        raise _not_configured()
    creds = list_credentials()
    if not creds:
        raise HTTPException(status_code=400, detail="Keine Passkeys registriert.")
    options = generate_authentication_options(
        rp_id=rp_id(),
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"]))
            for c in creds
            if c.get("id")
        ],
    )
    state = _store_challenge(options.challenge, "auth")
    return {"state": state, "options": json.loads(options_to_json(options))}


@router.post("/api/auth/webauthn/login/verify")
async def webauthn_login_verify(request: Request):
    """Verify the assertion, bump the sign count, set the session cookie."""
    if not admin_password():
        raise _not_configured()
    try:
        body = await request.json()
    except Exception:
        body = {}
    credential = body.get("credential") or {}
    cred_id = credential.get("id") or credential.get("rawId") or ""
    stored = next((c for c in list_credentials() if c.get("id") == cred_id), None)
    if stored is None:
        raise HTTPException(status_code=401, detail="Unbekannter Passkey.")
    challenge = _pop_challenge(body.get("state", ""), "auth")
    if challenge is None:
        raise HTTPException(
            status_code=400, detail="Challenge abgelaufen — bitte erneut versuchen."
        )
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id(),
            expected_origin=allowed_origins(),
            credential_public_key=base64url_to_bytes(stored["public_key"]),
            credential_current_sign_count=int(stored.get("sign_count", 0)),
        )
    except Exception as e:
        log.warning(f"Passkey login failed: {e}")
        raise HTTPException(status_code=401, detail="Passkey-Anmeldung fehlgeschlagen.")

    creds = list_credentials()
    for c in creds:
        if c.get("id") == cred_id:
            c["sign_count"] = verified.new_sign_count
    _save_credentials(creds)
    response = JSONResponse({"status": "ok", "user": admin_username()})
    set_session_cookie(response, request, admin_username())
    return response


# --- Credential management (dashboard 'Sicherheit' card) ---


@router.get("/api/auth/webauthn/credentials")
def webauthn_list_credentials(user: str = Depends(require_admin)):
    """List registered passkeys (metadata only, no public keys)."""
    return {"credentials": [_public_credential(c) for c in list_credentials()]}


@router.delete("/api/auth/webauthn/credentials/{cred_id}")
def webauthn_delete_credential(cred_id: str, user: str = Depends(require_admin)):
    """Remove a registered passkey."""
    creds = list_credentials()
    remaining = [c for c in creds if c.get("id") != cred_id]
    if len(remaining) == len(creds):
        raise HTTPException(status_code=404, detail="Passkey nicht gefunden.")
    _save_credentials(remaining)
    return {"status": "ok"}
