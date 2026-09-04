from __future__ import annotations

import asyncio

from backend import box
from backend.events import EventStore
from backend.services import Services


class _Client:
    async def post(self, url, json):
        assert url.endswith("/free")


class _Comfy:
    client = _Client()
    base_url = "http://fox:8188"


def test_training_copies_panels_streams_progress_and_persists_job(tmp_path, monkeypatch):
    panels = tmp_path / "generated" / "bible_ember_panels"
    panels.mkdir(parents=True)
    (panels / "front.png").write_bytes(b"png")

    async def copied(local, remote, **kwargs):
        assert local == panels
        assert remote == r"C:\sf"
        return 0, ""

    async def copied_file(local, remote, **kwargs):
        assert local.name.endswith("dataset.toml")
        assert 'image_dir = "C:/sf/bible_ember_panels"' in local.read_text(encoding="utf-8")
        return 0, ""

    async def lines(*args, **kwargs):
        yield "step 1/3\n"
        yield "step 3/3\n"

    monkeypatch.setattr(box, "copy_tree_to_box", copied)
    monkeypatch.setattr(box, "copy_to_box", copied_file)
    monkeypatch.setattr(box, "stream_training", lines)
    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    result = asyncio.run(Services(comfy=_Comfy(), events=events, generated_root=tmp_path / "generated").train_character_lora("ember", steps=3))

    assert result["status"] == "completed"
    assert result["progress"] == {"step": 3, "total": 3}
    assert result["lora_name"].endswith(".safetensors")
    assert [event["kind"] for event in events.read(result["job_id"])] == [
        "tool_called", "queued", "running", "progress", "progress", "completed"
    ]
