"""Contracts used by the visual studio: stable samples and observable progress."""
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app, box
from tests.test_style import make, png


@pytest.mark.parametrize("kind", ["character", "style"])
def test_remove_then_add_keeps_surviving_images_and_captions(tmp_path, monkeypatch, kind):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    if kind == "character":
        run(service.create_character("ベル", "she/her"))
        add, remove, caption, info = service.add_samples, service.remove_sample, service.set_caption, service.character_info
    else:
        run(service.create_style("ベル"))
        add, remove, caption, info = service.add_style_samples, service.remove_style_sample, service.set_style_caption, service.style_info
    images = []
    for index, color in enumerate(["red", "blue", "green", "orange"]):
        image = tmp_path / f"{index}.png"; image.write_bytes(png(color)); images.append(image)
    for index, image in enumerate(images[:3]):
        run(add("ベル", str(image), f"caption {index}"))
    before = run(info("ベル"))
    surviving = {s["index"]: (s["caption"], Path(s["path"]).read_bytes()) for s in before["samples"] if s["index"] != 1}
    run(remove("ベル", 1))
    record = run(add("ベル", str(images[3]), "衣装 | ポーズ"))
    assert [s["index"] for s in record["samples"]] == [0, 2, 3]
    for sample in record["samples"][:2]:
        assert (sample["caption"], Path(sample["path"]).read_bytes()) == surviving[sample["index"]]
    assert record["samples"][-1]["caption"] == "衣装 | ポーズ"
    run(caption("ベル", 2, "saved separately"))
    assert run(info("ベル"))["samples"][1]["caption"] == "saved separately"
    for index in [0, 2, 3]:
        record = run(remove("ベル", index))
    assert record["samples"] == [] and "samples_sheet" not in record


def test_completed_panels_and_previews_are_visible_before_entire_job_finishes(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="fixture.safetensors"))
    original = comfy.submit
    snapshots = []

    async def submit(graph, job_id):
        snapshots.append(service.events.load_job(job_id))
        return await original(graph, job_id)

    comfy.submit = submit
    run(service.preview_character("Bell", count=2))
    assert snapshots[1]["status"] == "running" and len(snapshots[1]["pictures"]) == 1
    assert Path(snapshots[1]["pictures"][0]["path"]).is_file()
    snapshots.clear()
    run(service.generate_character_bible("Bell"))
    assert snapshots[1]["completed_panels"] == 1 and snapshots[1]["total_panels"] == 23
    assert len(snapshots[1]["panels"]) == 1 and Path(snapshots[1]["panels"][0]).is_file()
    assert snapshots[-1]["completed_panels"] == 22


@pytest.mark.parametrize("failure", ["copy", "stream"])
def test_training_failure_is_not_left_running(tmp_path, monkeypatch, failure):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her"))
    source = tmp_path / "source.png"; source.write_bytes(png())
    run(service.add_samples("Bell", str(source)))

    async def copy(*args, **kwargs):
        return 1, "fixture copy failure"

    async def stream(*args, **kwargs):
        yield "steps: 1/3 [00:01<00:02]"
        raise RuntimeError("fixture stream failure")

    monkeypatch.setattr(box, "copy_tree_to_box" if failure == "copy" else "stream_training", copy if failure == "copy" else stream)
    with pytest.raises(RuntimeError, match="fixture"):
        run(service.train_character_lora("Bell", steps=3))
    job = service.events.list_jobs()[0]
    assert job["status"] == "failed" and "fixture" in job["error"]
    assert list(service.events.read(job["job_id"]))[-1]["kind"] == "failed"
    assert not run(service.character_info("Bell"))["lora_name"]


def test_style_sample_http_routes_and_static_cache_policy(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    monkeypatch.setattr(app.services, "styles_root", service.styles_root)
    monkeypatch.setattr(app.services, "events", service.events)
    run = asyncio.run
    run(service.create_style("水彩"))
    source = tmp_path / "source.png"; source.write_bytes(png())
    run(service.add_style_samples("水彩", str(source)))
    with TestClient(app.app) as client:
        result = client.post("/api/styles/水彩/samples/0/caption", params={"caption": "portrait | blue"})
        assert result.status_code == 200 and result.json()["samples"][0]["caption"] == "portrait | blue"
        result = client.delete("/api/styles/水彩/samples/0")
        assert result.status_code == 200 and result.json()["samples"] == []
        assert client.get("/main.js").headers["cache-control"] == "no-store"
