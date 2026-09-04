from __future__ import annotations

from backend.events import EventStore, SCHEMA_VERSION


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

    path = store.save_job({"job_id": "job-a", "status": "submitted"})
    assert path.name == "job-a.json"
    assert store.load_job("job-a") == {"job_id": "job-a", "status": "submitted"}
    assert store.load_job("missing") is None


def test_events_skip_malformed_ndjson_records(tmp_path):
    path = tmp_path / "events.ndjson"
    path.write_text('{"job_id":"ok","seq":1}\nnot json\n', encoding="utf-8")

    assert list(EventStore(path, tmp_path / "jobs").read()) == [{"job_id": "ok", "seq": 1}]
