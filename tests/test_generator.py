"""Generator flow tests — Imagen call is monkeypatched, no network."""

from io import BytesIO

from PIL import Image

from tests.conftest import make_png


def test_generate_without_api_key_returns_german_error(client, auth):
    r = client.post("/api/generate", json={"style_preset": "pop-art"}, auth=auth)
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.json()["detail"]


def test_generate_flow_accept_and_gallery(client, auth, monkeypatch):
    import app.generator as generator
    from app import config
    from app.gallery import GALLERY_DIRS

    # Fake Imagen: 16:9 output with a baked-in white bar
    fake_raw = make_png(1408, 768, white_left=51)
    prompts = []

    def fake_imagen(prompt):
        prompts.append(prompt)
        return fake_raw

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(generator, "_call_imagen", fake_imagen)

    # 1. Generate
    r = client.post(
        "/api/generate",
        json={"style_preset": "warhol", "subject": "a cheerful goat"},
        auth=auth,
    )
    assert r.status_code == 200
    item_id = r.json()["id"]
    assert r.json()["preview_url"] == f"/api/pending/{item_id}.png"
    # Prompt contains preset + subject + anti-border instructions
    assert "a cheerful goat" in prompts[0]
    assert "edge to edge" in prompts[0]

    # 2. Listed as pending
    r = client.get("/api/pending", auth=auth)
    assert any(i["id"] == item_id for i in r.json()["items"])

    # 3. Preview served, display-sized, white bar trimmed
    r = client.get(f"/api/pending/{item_id}.png", auth=auth)
    assert r.status_code == 200
    img = Image.open(BytesIO(r.content))
    assert img.size == (800, 480)

    # 4. Accept without push -> lands in goat gallery with semantic name
    monkeypatch.setattr(generator, "push_to_trmnl", lambda title: True)
    r = client.post(f"/api/pending/{item_id}/accept", json={"push": False}, auth=auth)
    assert r.status_code == 200
    filename = r.json()["filename"]
    assert filename.startswith("gen_warhol_")
    assert (GALLERY_DIRS["goat-art"] / filename).exists()

    # 5. Pending item cleaned up
    r = client.get("/api/pending", auth=auth)
    assert all(i["id"] != item_id for i in r.json()["items"])


def test_generate_accept_with_push_sets_current(client, auth, monkeypatch):
    import app.generator as generator
    from app import config
    from app.config import CURRENT_IMAGE

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(generator, "_call_imagen", lambda p: make_png(1408, 768))
    pushed = []
    monkeypatch.setattr(generator, "push_to_trmnl", lambda title: pushed.append(title) or True)

    r = client.post("/api/generate", json={"subject": "eine Ziege"}, auth=auth)
    item_id = r.json()["id"]
    r = client.post(f"/api/pending/{item_id}/accept", json={"push": True}, auth=auth)
    assert r.status_code == 200
    assert r.json()["pushed"] is True
    assert pushed
    assert CURRENT_IMAGE.exists()
    assert Image.open(BytesIO(CURRENT_IMAGE.read_bytes())).size == (800, 480)


def test_generate_quota_error_german(client, auth, monkeypatch):
    import app.generator as generator
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")

    def raise_quota(prompt):
        raise generator.GeneratorError(
            "Imagen-Kontingent erschöpft (429). Bitte später erneut versuchen.",
            status_code=429,
        )

    monkeypatch.setattr(generator, "_call_imagen", raise_quota)
    r = client.post("/api/generate", json={}, auth=auth)
    assert r.status_code == 429
    assert "Kontingent" in r.json()["detail"]


def test_discard_pending(client, auth, monkeypatch):
    import app.generator as generator
    from app import config
    from app.config import PENDING_DIR

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(generator, "_call_imagen", lambda p: make_png(1408, 768))

    item_id = client.post("/api/generate", json={}, auth=auth).json()["id"]
    assert (PENDING_DIR / f"{item_id}.png").exists()

    r = client.delete(f"/api/pending/{item_id}", auth=auth)
    assert r.status_code == 200
    assert not (PENDING_DIR / f"{item_id}.png").exists()
    assert not (PENDING_DIR / f"{item_id}.json").exists()


def test_unknown_style_preset_rejected(client, auth, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    r = client.post("/api/generate", json={"style_preset": "nope"}, auth=auth)
    assert r.status_code == 400
