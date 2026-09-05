"""Styles: pictures whose look becomes a style LoRA; stacked on a character or used alone."""
from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from backend import box
from backend.events import EventStore
from backend.services import Services


def png(color: str = "#44aaff") -> bytes:
    image = Image.new("RGBA", (24, 32), color)
    output = BytesIO(); image.save(output, "PNG")
    return output.getvalue()


class ComfyFixture:
    def __init__(self):
        self.submitted: list[dict] = []
        self.base_url = "http://fox:8188"
        class _Client:
            async def post(self, url, json): assert url.endswith("/free")
        self.client = _Client()
        self.drop_after: int | None = None

    async def upload(self, content, name):
        return name

    async def submit(self, workflow, client_id):
        self.submitted.append(workflow)
        return f"prompt-{len(self.submitted)}"

    async def history(self, prompt_id):
        if self.drop_after is not None:
            return {}
        return {"status": {"completed": True, "status_str": "success"},
                "outputs": {"25": {"images": [{"filename": f"{prompt_id}.png"}]}}}

    async def queue(self):
        return {"queue_running": [], "queue_pending": []}


def make(tmp_path, monkeypatch):
    async def copied(local, remote, **kwargs): return 0, ""
    async def lines(*args, **kwargs):
        yield "steps: 100%|##########| 3/3 [00:03<00:00,  1.24it/s]"
    monkeypatch.setattr(box, "copy_tree_to_box", copied)
    monkeypatch.setattr(box, "copy_to_box", copied)
    monkeypatch.setattr(box, "stream_training", lines)
    comfy = ComfyFixture()
    service = Services(comfy=comfy, events=EventStore(tmp_path / "events.ndjson", tmp_path / "jobs"),
                       generated_root=tmp_path / "generated", uploads_root=tmp_path / "uploads",
                       characters_root=tmp_path / "characters", styles_root=tmp_path / "styles")
    async def view(_image): return png()
    service._view = view
    return service, comfy


def test_style_is_pictures_then_a_lora_then_a_look_for_new_pictures(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    a = tmp_path / "a.png"; a.write_bytes(png("#ff0000"))
    style = run(service.create_style("glow", note="owner's words"))
    assert style["trigger"] == "glow_style" and style["samples"] == []
    style = run(service.add_style_samples("glow", str(a), "night sky, sparkles"))
    assert (tmp_path / "styles" / "glow" / "samples.png").is_file()
    try:
        run(service.generate_image("a fox", "glow"))
    except ValueError as error:
        assert "train_style_lora" in str(error)
    else:
        raise AssertionError("a style without a LoRA cannot draw")
    from tests.test_training_materials import accept_observations
    run(accept_observations(service, "glow", "style"))
    training = run(service.train_style_lora("glow", steps=3))
    assert (Path(training["dataset"]) / "000.txt").read_text() == "glow_style, night sky, sparkles"
    assert run(service.style_info("glow"))["lora_name"] == training["lora_name"]
    job = run(service.generate_image("a fox on a snowy street", "glow", width=768, height=512, seed=4))
    graph = comfy.submitted[-1]
    assert job["prompt"] == "glow_style, a fox on a snowy street" and graph["20"]["inputs"]["text"] == job["prompt"]
    assert graph["4"]["inputs"]["lora_name"] == training["lora_name"] and graph["22"]["inputs"]["width"] == 768
    assert [s["name"] for s in run(service.list_styles())] == ["glow"]
    assert run(service.delete_style("glow"))["deleted"] and run(service.list_styles()) == []


def test_character_in_a_style_stacks_both_loras(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    a = tmp_path / "a.png"; a.write_bytes(png())
    run(service.create_style("glow")); run(service.add_style_samples("glow", str(a)))
    from tests.test_training_materials import accept_observations
    run(accept_observations(service, "glow", "style")); run(service.train_style_lora("glow", steps=3))
    run(service.create_character("Bell", "she/her", lora_name="BellGrok.safetensors", trigger="bell_idol"))
    preview = run(service.preview_character("Bell", "waving", seed=1, style="glow"))
    graph = comfy.submitted[-1]
    assert graph["4"]["inputs"]["lora_name"] == "BellGrok.safetensors" and graph["40"]["inputs"]["lora_name"].startswith("glow_")
    assert graph["40"]["inputs"]["model"] == ["4", 0] and graph["23"]["inputs"]["model"] == ["40", 0] and graph["20"]["inputs"]["clip"] == ["40", 1]
    assert preview["prompt"].startswith("bell_idol, glow_style, 1girl, waving")
    record = run(service.set_character_style("Bell", "glow", 0.6))
    assert record["style"] == "glow" and record["style_strength"] == 0.6
    job = run(service.generate_character_bible("Bell"))
    assert job["style"] == "glow" and comfy.submitted[-1]["40"]["inputs"]["strength_model"] == 0.6
    assert comfy.submitted[-1]["20"]["inputs"]["text"].startswith("bell_idol, glow_style, ")
    picture = run(service.generate_from_bible("Bell", "on stage"))
    assert comfy.submitted[-1]["20"]["inputs"]["text"] == "bell_idol, glow_style, on stage"
    run(service.set_character_style("Bell", ""))
    run(service.preview_character("Bell", "waving"))
    assert "40" not in comfy.submitted[-1]


def test_pictures_come_in_as_paths_data_urls_or_uploads(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    data = "data:image/png;base64," + base64.b64encode(png("#123456")).decode()
    stored = asyncio.run(service._resolve_image(data))
    assert stored.parent == tmp_path / "uploads" and Image.open(stored).size == (24, 32)
    uploaded = service.save_upload(png(), "My Picture.jpg")
    assert uploaded.name.startswith("My_Picture-") and uploaded.suffix == ".png"
    assert asyncio.run(service._resolve_image(uploaded.stem)) == uploaded


def test_waiting_follows_the_queue_and_fails_only_when_comfy_drops_the_prompt(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    comfy.drop_after = 0
    try:
        asyncio.run(service._history_until_done("prompt-x"))
    except RuntimeError as error:
        assert "dropped" in str(error)
    else:
        raise AssertionError("a prompt absent from queue and history must fail")


def test_refine_image_redraws_with_anima_and_lora(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    draft = tmp_path / "draft.png"; draft.write_bytes(png())
    job = asyncio.run(service.refine_image(str(draft), "bell_idol, front view", "bell.safetensors", denoise=0.5))
    assert job["status"] == "completed" and job["path"].endswith("-refine.png")
    graph = comfy.submitted[0]
    assert graph["1"]["inputs"]["unet_name"] == "anima-base-v1.0.safetensors" and graph["23"]["inputs"]["denoise"] == 0.5


@pytest.mark.parametrize("kind", ["from_bible", "preview", "image", "refine", "redraw_panel", "sprite"])
@pytest.mark.parametrize("stage", ["submit", "wait", "download", "save"])
def test_generation_failures_are_recorded_and_reraised(tmp_path, monkeypatch, kind, stage):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    style = run(service.create_style("glow"))
    style["lora_name"] = "glow.safetensors"
    service._save_style(style)
    draft = tmp_path / "draft.png"
    draft.write_bytes(png())
    if kind == "redraw_panel":
        run(service.generate_character_bible("Bell"))

    def fail(*args, **kwargs):
        raise RuntimeError(f"{stage} failed")
    async def async_fail(*args, **kwargs):
        fail()
    if stage == "submit":
        monkeypatch.setattr(comfy, "submit", async_fail)
    elif stage == "wait":
        monkeypatch.setattr(comfy, "history", async_fail)
    elif stage == "download":
        monkeypatch.setattr(service, "_view", async_fail)
    elif kind == "redraw_panel":
        monkeypatch.setattr("backend.bible.crop_nonwhite", fail)
    else:
        monkeypatch.setattr(service, "_write_generated", fail)
    calls = {
        "from_bible": lambda: service.generate_from_bible("Bell", "waving"),
        "preview": lambda: service.preview_character("Bell", "waving"),
        "image": lambda: service.generate_image("a fox", "glow"),
        "refine": lambda: service.refine_image(str(draft), "waving", "bell.safetensors"),
        "redraw_panel": lambda: service.redraw_panel("Bell", "turn_front", "waving"),
        "sprite": lambda: service.generate_sprite("a fox", count=1),
    }
    with pytest.raises(RuntimeError, match=f"{stage} failed"):
        run(calls[kind]())
    job = next(j for j in service.events.list_jobs() if j["kind"] == kind)
    assert job["status"] == "failed"
    assert job["error"] == f"{stage} failed"
    failures = [e for e in service.events.read(job["job_id"]) if e["kind"] == "failed"]
    assert len(failures) == 1 and failures[0]["payload"]["error"] == job["error"]
