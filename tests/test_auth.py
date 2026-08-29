"""Auth tests: session/Basic on protected routes, login redirect for browsers,
device endpoints stay public."""

PROTECTED_GETS = [
    "/",
    "/gallery",
    "/api/status",
    "/api/galleries",
    "/api/source",
    "/api/pending",
]

HTML_ACCEPT = {"Accept": "text/html,application/xhtml+xml"}


def test_protected_routes_require_auth(client):
    """API clients (no text/html Accept) get 401 JSON with Basic challenge."""
    for path in PROTECTED_GETS:
        r = client.get(path)
        assert r.status_code == 401, path
        assert "WWW-Authenticate" in r.headers, path


def test_browser_html_routes_redirect_to_login(client):
    """Browsers (Accept: text/html) are redirected to /login instead of 401."""
    r = client.get("/", headers=HTML_ACCEPT, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login?next=%2F"

    r = client.get("/gallery", headers=HTML_ACCEPT, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/login?next=%2Fgallery")


def test_login_page_is_public(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "TRMNL Admin" in r.text
    assert "Anmelden" in r.text


def test_mutating_routes_require_auth(client):
    assert client.post("/api/generate", json={}).status_code == 401
    assert client.post("/api/source", json={"source": "nasa"}).status_code == 401
    assert client.delete("/api/galleries/goat-art/x.png").status_code == 401
    assert client.get("/api/next").status_code == 401
    assert client.get("/api/push/goat-art").status_code == 401


def test_wrong_credentials_rejected(client):
    r = client.get("/api/status", auth=("marc", "wrong"))
    assert r.status_code == 401


def test_public_endpoints_no_auth(client):
    # /health: 200 healthy or 503 degraded — but never 401
    r = client.get("/health")
    assert r.status_code in (200, 503)
    # /current.png: 404 (no image yet) or 200 — never 401
    r = client.get("/current.png")
    assert r.status_code in (200, 404)


def test_correct_credentials_accepted(client, auth):
    """HTTP Basic keeps working on API endpoints (curl/scripting fallback)."""
    r = client.get("/api/status", auth=auth)
    assert r.status_code == 200
    assert "art_source" in r.json()

    r = client.get("/", auth=auth)
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_fail_closed_without_password(client, auth, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    r = client.get("/api/status", auth=auth)
    assert r.status_code == 503
    assert "ADMIN_PASSWORD" in r.json()["detail"]


def test_dashboard_escapes_titles(client, auth):
    """XSS: malicious gallery titles must be escaped in the HTML."""
    from tests.conftest import make_png
    from app.gallery import save_image
    evil = '<script>alert(1)</script>'
    save_image("goat-art", "evil.png", make_png(800, 480), evil)

    r = client.get("/gallery", auth=auth)
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text
