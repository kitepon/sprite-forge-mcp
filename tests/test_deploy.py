from fastapi.testclient import TestClient

from backend.app import app
from backend.events import EventStore


def test_deployed_app_serves_webui_and_job_history(tmp_path, monkeypatch):
    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    job = {"job_id": "job-1", "kind": "sprite", "status": "completed"}
    events.save_job(job)
    monkeypatch.setattr("backend.app.services.events", events)
    with TestClient(app) as client:
        page = client.get("/")
        history = client.get("/api/jobs")

    assert page.status_code == 200
    assert "Sprite Forge" in page.text
    assert history.json() == [job]
