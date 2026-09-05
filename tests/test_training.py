from __future__ import annotations

import asyncio
from pathlib import Path

from backend import box
from backend.events import EventStore
from backend.services import Services
from tests.test_training_materials import accept_observations


class _Client:
    async def post(self, url, json):
        assert url.endswith("/free")


class _Comfy:
    client = _Client()
    base_url = "http://fox:8188"


def test_training_copies_samples_streams_progress_and_persists_job(tmp_path, monkeypatch):
    async def copied(local, remote, **kwargs):
        assert local.name.startswith("dataset_ember_") and remote == r"C:\sf"
        return 0, ""

    async def copied_file(local, remote, **kwargs):
        text = local.read_text(encoding="utf-8")
        assert 'image_dir = "C:/sf/dataset_ember_' in text and "num_repeats = 200" in text
        return 0, ""

    async def lines(*args, **kwargs):
        yield "steps:  33%|###       | 1/3 [00:01<00:02,  1.24it/s, avr_loss=0.2]"
        yield "some other trainer chatter"
        yield "steps: 100%|##########| 3/3 [00:03<00:00,  1.24it/s, avr_loss=0.1]"

    monkeypatch.setattr(box, "copy_tree_to_box", copied)
    monkeypatch.setattr(box, "copy_to_box", copied_file)
    monkeypatch.setattr(box, "stream_training", lines)
    events = EventStore(tmp_path / "events.ndjson", tmp_path / "jobs")
    service = Services(comfy=_Comfy(), events=events, generated_root=tmp_path / "generated", characters_root=tmp_path / "characters")
    picture = tmp_path / "p.png"
    from PIL import Image; Image.new("RGB", (8, 8), "red").save(picture)
    asyncio.run(service.create_character("ember", "they/them"))
    asyncio.run(service.add_samples("ember", str(picture), "red coat"))
    asyncio.run(accept_observations(service, "ember"))
    result = asyncio.run(service.train_character_lora("ember", steps=3))

    assert result["status"] == "completed"
    assert result["progress"] == {"step": 3, "total": 3}
    assert result["lora_name"].endswith(".safetensors")
    assert (Path(result["dataset"]) / "000.txt").read_text(encoding="utf-8") == "ember, red coat"
    assert (tmp_path / "generated" / f"{result['job_id']}-train.log").read_text(encoding="utf-8").count("\n") == 3
    assert [e["payload"] for e in events.read(result["job_id"]) if e["kind"] == "progress"] == [{"step": 1, "total": 3}, {"step": 3, "total": 3}]
