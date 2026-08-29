"""Session-cookie login: password login, rate limit, logout, token integrity."""

import base64
import hashlib
import hmac
import json
import time

from app.security import (
    SESSION_COOKIE,
    create_session_token,
    verify_session_token,
    _b64u,
    _session_key,
)


def _login(client, password="test-pass"):
    return client.post("/api/auth/login", json={"password": password})


def test_password_login_sets_cookie_and_grants_access(client):
    r = _login(client)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert SESSION_COOKIE in r.cookies

    # Cookie (persisted by the client) now grants access — no Basic needed
    r = client.get("/api/status")
    assert r.status_code == 200
    r = client.get("/", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_login_page_redirects_when_logged_in(client):
    _login(client)
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_wrong_password_401(client):
    r = _login(client, password="falsch")
    assert r.status_code == 401
    assert SESSION_COOKIE not in r.cookies
    assert "Falsches Passwort" in r.json()["detail"]


def test_rate_limit_after_five_failures(client):
    for _ in range(5):
        assert _login(client, password="falsch").status_code == 401
    r = _login(client, password="falsch")
    assert r.status_code == 429
    assert "Fehlversuche" in r.json()["detail"]
    # Even the correct password is blocked while rate-limited
    assert _login(client).status_code == 429


def test_logout_clears_cookie(client):
    _login(client)
    assert client.get("/api/status").status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert client.get("/api/status").status_code == 401


def test_logout_requires_auth(client):
    assert client.post("/api/auth/logout").status_code == 401


def test_tampered_token_rejected(client):
    token = create_session_token("marc")
    payload, sig = token.rsplit(".", 1)
    forged_payload = _b64u(json.dumps({"u": "eve", "exp": int(time.time()) + 999}).encode())

    assert verify_session_token(token) == "marc"
    assert verify_session_token(f"{forged_payload}.{sig}") is None
    assert verify_session_token(payload) is None  # no signature
    assert verify_session_token("garbage.garbage") is None
    assert verify_session_token("") is None

    client.cookies.set(SESSION_COOKIE, f"{forged_payload}.{sig}")
    assert client.get("/api/status").status_code == 401


def test_expired_token_rejected():
    payload = _b64u(json.dumps({"u": "marc", "exp": int(time.time()) - 10}).encode())
    sig = _b64u(hmac.new(_session_key(), payload.encode(), hashlib.sha256).digest())
    assert verify_session_token(f"{payload}.{sig}") is None


def test_session_key_changes_with_password(monkeypatch):
    """Rotating ADMIN_PASSWORD invalidates existing sessions (derived key)."""
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    token = create_session_token("marc")
    assert verify_session_token(token) == "marc"
    monkeypatch.setenv("ADMIN_PASSWORD", "rotated")
    assert verify_session_token(token) is None


def test_session_secret_env_used(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "super-secret")
    token = create_session_token("marc")
    assert verify_session_token(token) == "marc"
    monkeypatch.setenv("SESSION_SECRET", "other-secret")
    assert verify_session_token(token) is None


def test_secure_flag_behind_https_proxy(client):
    r = client.post(
        "/api/auth/login",
        json={"password": "test-pass"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert r.status_code == 200
    assert "secure" in r.headers["set-cookie"].lower()

    # Plain http (tests): no Secure flag, so the cookie works locally
    client.cookies.clear()
    r = _login(client)
    assert "secure" not in r.headers["set-cookie"].lower()
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "samesite=lax" in r.headers["set-cookie"].lower()


def test_expired_session_fetch_has_no_basic_challenge(client):
    """Stale cookie + API fetch → 401 WITHOUT WWW-Authenticate (no popup)."""
    client.cookies.set(SESSION_COOKIE, "stale.token")
    r = client.get("/api/status")
    assert r.status_code == 401
    assert "WWW-Authenticate" not in r.headers
