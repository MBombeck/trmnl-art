"""Scheduler tests: gallery-origin no-resave + source switch rescheduling."""

from tests.conftest import make_png


def test_run_job_gallery_origin_not_resaved(monkeypatch):
    """A: images served FROM the gallery must not be saved back as duplicates."""
    import app.scheduler as scheduler
    from app.gallery import GALLERY_DIRS

    monkeypatch.setattr(scheduler, "push_to_trmnl", lambda desc: True)
    d = GALLERY_DIRS["goat-art"]
    data = make_png(800, 480)
    (d / "existing.png").write_bytes(data)
    before = len(list(d.glob("*.png")))

    scheduler._run_job("goat-art", lambda: (data, "Existing Goat", "gallery"))

    assert len(list(d.glob("*.png"))) == before  # no new file
    assert scheduler.job_status["goat-art"]["last_error"] is None


def test_run_job_fresh_origin_saved_once(monkeypatch):
    import app.scheduler as scheduler
    from app.gallery import GALLERY_DIRS

    monkeypatch.setattr(scheduler, "push_to_trmnl", lambda desc: True)
    d = GALLERY_DIRS["goat-art"]
    data = make_png(1408, 768)
    before = len(list(d.glob("*.png")))

    scheduler._run_job("goat-art", lambda: (data, "Fresh Goat", "fresh"))

    assert len(list(d.glob("*.png"))) == before + 1
    # Saved asset is normalized to display size
    from io import BytesIO
    from PIL import Image
    new_file = next(f for f in d.glob("*.png") if "fresh_goat" in f.name)
    assert Image.open(BytesIO(new_file.read_bytes())).size == (800, 480)


def test_run_job_two_tuple_treated_as_fresh(monkeypatch):
    import app.scheduler as scheduler
    from app.gallery import GALLERY_DIRS

    monkeypatch.setattr(scheduler, "push_to_trmnl", lambda desc: True)
    d = GALLERY_DIRS["nasa"]
    data = make_png(1200, 900)

    scheduler._run_job("nasa", lambda: (data, "Nebula"))

    assert len(list(d.glob("*.png"))) == 1


def test_source_switch_persists_and_reschedules(client, auth, monkeypatch):
    """E: POST /api/source persists to settings.json and re-registers cron jobs."""
    import app.scheduler as scheduler_mod
    from app import state

    calls = []
    monkeypatch.setattr(scheduler_mod, "reschedule", lambda src: calls.append(src))

    r = client.post("/api/source", json={"source": "nasa"}, auth=auth)
    assert r.status_code == 200
    assert calls == ["nasa"]
    assert state.get_active_source() == "nasa"

    from app.config import SETTINGS_FILE
    import json
    assert json.loads(SETTINGS_FILE.read_text())["art_source"] == "nasa"

    r = client.get("/api/source", auth=auth)
    assert r.json()["source"] == "nasa"


def test_source_switch_rejects_unknown(client, auth):
    r = client.post("/api/source", json={"source": "bogus"}, auth=auth)
    assert r.status_code == 400


def test_reschedule_registers_expected_jobs():
    import app.scheduler as scheduler

    scheduler.reschedule("nasa")
    ids = {j.id for j in scheduler.scheduler.get_jobs()}
    assert ids == {"nasa_daily"}

    scheduler.reschedule("goat-art")
    ids = {j.id for j in scheduler.scheduler.get_jobs()}
    assert ids == {"goat_art_daily"}

    scheduler.reschedule("mixed")
    ids = {j.id for j in scheduler.scheduler.get_jobs()}
    assert ids == {"rijksmuseum_daily", "nasa_daily"}

    scheduler.reschedule("random")
    ids = {j.id for j in scheduler.scheduler.get_jobs()}
    assert ids == {"random_daily"}
