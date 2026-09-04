from __future__ import annotations

from backend.services import Services


class _Comfy:
    async def submit(self, workflow, client_id):
        self.workflow, self.client_id = workflow, client_id
        return "prompt-1"

    async def history(self, prompt_id):
        assert prompt_id == "prompt-1"
        return {"status": {"completed": True, "status_str": "success"}}


def test_service_status_transitions_and_emits_events(tmp_path):
    from backend.events import EventStore
    import asyncio

    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    service = Services(comfy=_Comfy(), events=events)
    job = asyncio.run(service.start_base("fire mage", 42))
    status = asyncio.run(service.status(job["job_id"]))

    assert status["status"] == "success"
    assert status["prompt_id"] == "prompt-1"
    assert [event["kind"] for event in events.read(job["job_id"])] == [
        "tool_called", "queued", "submitted", "tool_called", "success"
    ]


def test_service_returns_unknown_for_missing_job(tmp_path):
    from backend.events import EventStore
    import asyncio

    service = Services(comfy=_Comfy(), events=EventStore(tmp_path / "events.ndjson", tmp_path / "jobs"))
    assert asyncio.run(service.status("missing")) == {"job_id": "missing", "status": "unknown"}
