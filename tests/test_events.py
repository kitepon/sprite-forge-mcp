from __future__ import annotations

from backend.events import EventStore, SCHEMA_VERSION
from backend.services import Services


def test_events_are_per_job_sequenced_and_persisted(tmp_path):
    store = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")

    first = store.append("job-a", "queued", {"seed": 7})
    second = store.append("job-b", "queued", {})
    third = store.append("job-a", "submitted", {"prompt_id": "prompt-1"})

    assert (first["seq"], second["seq"], third["seq"]) == (1, 1, 2)
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["event_id"] != third["event_id"]
    assert list(store.read("job-a")) == [first, third]
    assert list(store.read("job-b")) == [second]

    job = {"job_id": "job-a", "status": "submitted"}
    path = store.save_job(job)
    assert path.name == "job-a.json"
    assert store.load_job("job-a") == job
    assert job["created_at"] == job["updated_at"]
    created_at = job["created_at"]
    store.save_job(job)
    assert job["created_at"] == created_at and job["updated_at"] >= created_at
    assert store.load_job("missing") is None
    assert store.list_jobs() == [job]


def test_events_skip_malformed_ndjson_records(tmp_path):
    path = tmp_path / "events.ndjson"
    path.write_text('{"job_id":"ok","seq":1}\nnot json\n', encoding="utf-8")

    assert list(EventStore(path, tmp_path / "jobs").read()) == [{"job_id": "ok", "seq": 1}]


def test_events_resume_after_event_id(tmp_path):
    store = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    first = store.append("job-a", "tool_called", {"tool": "generate_sprite"})
    second = store.append("job-a", "completed", {"count": 1})

    assert list(store.read_since(first["event_id"])) == [second]
    assert list(store.read_since("unknown")) == [first, second]


def test_sprite_call_records_invocation_and_completion(tmp_path):
    from io import BytesIO
    from PIL import Image
    import asyncio

    class Comfy:
        async def submit(self, workflow, client_id):
            return "source" if workflow.get("3", {}).get("class_type") != "RMBG" else "matte"

        async def upload(self, content, name):
            return name

    image = Image.new("RGBA", (2, 2), (20, 40, 60, 0))
    encoded = BytesIO(); image.save(encoded, format="PNG")
    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    service = Services(comfy=Comfy(), events=events, generated_root=tmp_path / "generated")

    async def history(_prompt_id):
        return {"outputs": {"1": {"images": [{"filename": "artifact.png"}]}}}

    async def view(_image):
        return encoded.getvalue()

    service._history_until_done = history
    service._view = view
    job = asyncio.run(service.generate_sprite("azure mage", count=1, seed=7))

    assert [event["kind"] for event in events.read(job["job_id"])] == ["tool_called", "completed"]
    assert (tmp_path / "generated" / f"{job['job_id']}-0.png").is_file()


def test_sse_replays_events_after_since_id(tmp_path, monkeypatch):
    import asyncio
    from backend import app

    store = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    first = store.append("job-a", "tool_called", {"tool": "generate_sprite"})
    second = store.append("job-a", "completed", {"count": 1})
    monkeypatch.setattr(app.services, "events", store)

    async def first_chunk():
        stream = app._event_stream(first["event_id"])
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    chunk = asyncio.run(first_chunk())
    assert f"id: {second['event_id']}" in chunk
    assert 'event: completed' in chunk
