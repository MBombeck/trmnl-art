"""WebAuthn passkey endpoints: options shape, challenge store, credential CRUD."""

import re

from webauthn.helpers import bytes_to_base64url

from app.config import PASSKEYS_FILE
from app.util import read_json, write_json_atomic

B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def _seed_passkeys(*labels: str) -> list[dict]:
    creds = [
        {
            "id": bytes_to_base64url(f"cred-{i}".encode()),
            "public_key": bytes_to_base64url(f"pk-{i}".encode()),
            "sign_count": 0,
            "transports": ["internal"],
            "created_at": "2026-08-29T12:00:00",
            "label": label,
        }
        for i, label in enumerate(labels)
    ]
    write_json_atomic(PASSKEYS_FILE, creds)
    return creds


# --- Registration options (must be logged in) ---


def test_register_options_requires_auth(client):
    assert client.post("/api/auth/webauthn/register/options").status_code == 401


def test_register_options_shape(client, auth):
    r = client.post("/api/auth/webauthn/register/options", auth=auth)
    assert r.status_code == 200
    data = r.json()
    assert B64URL.match(data["state"])
    opts = data["options"]
    assert B64URL.match(opts["challenge"])
    assert opts["rp"]["id"] == "bombeck.io"
    assert opts["rp"]["name"] == "TRMNL Admin"
    assert opts["user"]["name"] == "marc"
    assert B64URL.match(opts["user"]["id"])


def test_register_options_excludes_existing_credentials(client, auth):
    creds = _seed_passkeys("Laptop")
    r = client.post("/api/auth/webauthn/register/options", auth=auth)
    excluded = [c["id"] for c in r.json()["options"]["excludeCredentials"]]
    assert creds[0]["id"] in excluded


def test_register_verify_bad_credential_400(client, auth):
    state = client.post("/api/auth/webauthn/register/options", auth=auth).json()["state"]
    r = client.post(
        "/api/auth/webauthn/register/verify",
        auth=auth,
        json={"state": state, "label": "x", "credential": {"id": "garbage"}},
    )
    assert r.status_code == 400


def test_register_verify_unknown_state_400(client, auth):
    r = client.post(
        "/api/auth/webauthn/register/verify",
        auth=auth,
        json={"state": "does-not-exist", "credential": {}},
    )
    assert r.status_code == 400
    assert "Challenge" in r.json()["detail"]


# --- Authentication options (public) ---


def test_login_options_without_passkeys_400(client):
    r = client.post("/api/auth/webauthn/login/options")
    assert r.status_code == 400
    assert "Keine Passkeys" in r.json()["detail"]


def test_login_options_shape(client):
    creds = _seed_passkeys("Laptop", "Handy")
    r = client.post("/api/auth/webauthn/login/options")
    assert r.status_code == 200
    data = r.json()
    assert B64URL.match(data["state"])
    opts = data["options"]
    assert B64URL.match(opts["challenge"])
    assert opts["rpId"] == "bombeck.io"
    allowed = [c["id"] for c in opts["allowCredentials"]]
    assert {c["id"] for c in creds} == set(allowed)


def test_login_verify_unknown_credential_401(client):
    _seed_passkeys("Laptop")
    state = client.post("/api/auth/webauthn/login/options").json()["state"]
    r = client.post(
        "/api/auth/webauthn/login/verify",
        json={"state": state, "credential": {"id": "unknown-id"}},
    )
    assert r.status_code == 401


def test_login_verify_bad_assertion_401(client):
    creds = _seed_passkeys("Laptop")
    state = client.post("/api/auth/webauthn/login/options").json()["state"]
    r = client.post(
        "/api/auth/webauthn/login/verify",
        json={"state": state, "credential": {"id": creds[0]["id"]}},
    )
    assert r.status_code == 401


def test_challenge_is_single_use(client, auth):
    """A state id can only be redeemed once."""
    creds = _seed_passkeys("Laptop")
    state = client.post("/api/auth/webauthn/login/options").json()["state"]
    body = {"state": state, "credential": {"id": creds[0]["id"]}}
    assert client.post("/api/auth/webauthn/login/verify", json=body).status_code == 401
    # Second use: challenge already consumed -> 400
    assert client.post("/api/auth/webauthn/login/verify", json=body).status_code == 400


# --- Credential management ---


def test_credentials_list_requires_auth_and_hides_key(client, auth):
    _seed_passkeys("Laptop", "Handy")
    assert client.get("/api/auth/webauthn/credentials").status_code == 401

    r = client.get("/api/auth/webauthn/credentials", auth=auth)
    assert r.status_code == 200
    creds = r.json()["credentials"]
    assert {c["label"] for c in creds} == {"Laptop", "Handy"}
    assert all("public_key" not in c for c in creds)


def test_credential_delete(client, auth):
    creds = _seed_passkeys("Laptop", "Handy")
    r = client.delete(f"/api/auth/webauthn/credentials/{creds[0]['id']}", auth=auth)
    assert r.status_code == 200
    stored = read_json(PASSKEYS_FILE, [])
    assert [c["label"] for c in stored] == ["Handy"]

    # Unknown id -> 404; unauthenticated -> 401
    assert client.delete("/api/auth/webauthn/credentials/nope", auth=auth).status_code == 404
    assert client.delete(f"/api/auth/webauthn/credentials/{creds[1]['id']}").status_code == 401


def test_dashboard_shows_passkeys(client, auth):
    _seed_passkeys("Mein Laptop")
    r = client.get("/", auth=auth)
    assert r.status_code == 200
    assert "Sicherheit" in r.text
    assert "Mein Laptop" in r.text
    assert "Passkey hinzufügen" in r.text


def test_login_page_shows_passkey_button_only_with_credentials(client):
    r = client.get("/login")
    assert "Mit Passkey anmelden" not in r.text
    _seed_passkeys("Laptop")
    r = client.get("/login")
    assert "Mit Passkey anmelden" in r.text
