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


def test_generate_falls_through_to_openrouter_after_quota(client, auth, monkeypatch):
    import app.generator as generator
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(generator, "OPENAI_API_KEY", "")
    monkeypatch.setattr(generator, "OPENROUTER_API_KEY", "fake-or-key")

    def raise_quota(prompt):
        raise generator.GeneratorError("Gemini-Guthaben aufgebraucht", status_code=429)

    called = []
    monkeypatch.setattr(generator, "_call_imagen", raise_quota)
    monkeypatch.setattr(generator, "_call_openrouter", lambda p: called.append(p) or make_png(1408, 768))

    r = client.post("/api/generate", json={"style_preset": "pop-art"}, auth=auth)
    assert r.status_code == 200, r.text
    assert called, "OpenRouter backend was not used as fallback"
    pending = generator.list_pending()
    assert pending and pending[0]["backend"].startswith("openrouter:")


def test_generate_all_backends_exhausted_lists_every_account(client, auth, monkeypatch):
    import app.generator as generator
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(generator, "OPENAI_API_KEY", "fake-oa")
    monkeypatch.setattr(generator, "OPENROUTER_API_KEY", "fake-or")

    def quota(prompt):
        raise generator.GeneratorError("leer", status_code=429)

    for fn in ("_call_imagen", "_call_openai", "_call_openrouter"):
        monkeypatch.setattr(generator, fn, quota)

    r = client.post("/api/generate", json={}, auth=auth)
    assert r.status_code == 429
    detail = r.json()["detail"]
    for needle in ("ai.studio", "platform.openai.com", "openrouter.ai/settings/credits"):
        assert needle in detail


def test_image_backend_env_moves_openrouter_first(client, auth, monkeypatch):
    import app.generator as generator
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(generator, "OPENROUTER_API_KEY", "fake-or")
    monkeypatch.setattr(generator, "IMAGE_BACKEND", "openrouter")

    order = []
    monkeypatch.setattr(generator, "_call_imagen", lambda p: order.append("imagen") or make_png(1408, 768))
    monkeypatch.setattr(generator, "_call_openrouter", lambda p: order.append("openrouter") or make_png(1408, 768))

    r = client.post("/api/generate", json={"style_preset": "pop-art"}, auth=auth)
    assert r.status_code == 200, r.text
    assert order == ["openrouter"]


def test_non_quota_error_does_not_fall_through(client, auth, monkeypatch):
    import app.generator as generator
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(generator, "OPENROUTER_API_KEY", "fake-or")

    def safety(prompt):
        raise generator.GeneratorError("Sicherheitsfilter", status_code=422)

    monkeypatch.setattr(generator, "_call_imagen", safety)
    monkeypatch.setattr(generator, "_call_openrouter", lambda p: (_ for _ in ()).throw(AssertionError("must not run")))

    r = client.post("/api/generate", json={}, auth=auth)
    assert r.status_code == 422
