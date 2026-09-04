"""Style presets, picture intake, and the two style-driven drawing tools."""
from __future__ import annotations

import asyncio
import base64
from io import BytesIO

from PIL import Image

from backend.events import EventStore
from backend.services import Services


def png(color: str = "#44aaff") -> bytes:
    image = Image.new("RGBA", (24, 32), color)
    output = BytesIO(); image.save(output, "PNG")
    return output.getvalue()


class ComfyFixture:
    def __init__(self):
        self.submitted: list[dict] = []
        self.drop_after: int | None = None
        self.polls = 0

    async def upload(self, content, name):
        return name

    async def submit(self, workflow, client_id):
        self.submitted.append(workflow)
        return f"prompt-{len(self.submitted)}"

    async def history(self, prompt_id):
        self.polls += 1
        if self.drop_after is not None:
            return {}
        return {"status": {"completed": True, "status_str": "success"},
                "outputs": {"25": {"images": [{"filename": f"{prompt_id}.png"}]}}}

    async def queue(self):
        return {"queue_running": [], "queue_pending": []}


def make(tmp_path):
    comfy = ComfyFixture()
    service = Services(comfy=comfy, events=EventStore(tmp_path / "events.ndjson", tmp_path / "jobs"),
                       generated_root=tmp_path / "generated", uploads_root=tmp_path / "uploads",
                       presets_root=tmp_path / "presets")
    async def view(_image): return png()
    service._view = view
    return service, comfy


def test_presets_are_bundles_of_pictures_saved_listed_and_deleted(tmp_path):
    service, _ = make(tmp_path)
    a, b = tmp_path / "a.png", tmp_path / "b.jpg"
    a.write_bytes(png("#ff0000")); Image.new("RGB", (8, 8), "green").save(b, "JPEG")
    preset = asyncio.run(service.save_style_preset("glow", f"{a}, {b}", note="owner's words"))
    assert preset["key"] == "glow" and len(preset["images"]) == 2 and preset["note"] == "owner's words"
    assert all(p.endswith(".png") for p in preset["images"])
    assert [p["name"] for p in asyncio.run(service.list_style_presets())] == ["glow"]
    assert asyncio.run(service.delete_style_preset("glow"))["deleted"]
    assert asyncio.run(service.list_style_presets()) == []


def test_pictures_come_in_as_paths_data_urls_or_uploads(tmp_path):
    service, _ = make(tmp_path)
    data = "data:image/png;base64," + base64.b64encode(png("#123456")).decode()
    stored = asyncio.run(service._resolve_image(data))
    assert stored.parent == tmp_path / "uploads" and Image.open(stored).size == (24, 32)
    uploaded = service.save_upload(png(), "My Picture.jpg")
    assert uploaded.name.startswith("My_Picture-") and uploaded.suffix == ".png"
    assert asyncio.run(service._resolve_image(uploaded.stem)) == uploaded


def test_generate_image_uses_only_style_pictures(tmp_path):
    service, comfy = make(tmp_path)
    s1 = tmp_path / "s1.png"; s1.write_bytes(png())
    asyncio.run(service.save_style_preset("glow", str(s1)))
    s2 = tmp_path / "s2.png"; s2.write_bytes(png("#00ff00"))
    job = asyncio.run(service.generate_image("a fox", width=768, height=512, style_preset="glow", style_refs=str(s2)))
    assert job["status"] == "completed" and job["path"].endswith("-image.png") and job["elapsed_s"] >= 0
    graph = comfy.submitted[0]
    assert graph["20"]["inputs"]["images.image0"] == ["10", 0] and graph["20"]["inputs"]["images.image1"] == ["11", 0]
    assert "images.image2" not in graph["20"]["inputs"]
    assert graph["22"]["inputs"] == {"width": 768, "height": 512, "batch_size": 1}
    assert "Do not copy the subjects" in graph["20"]["inputs"]["prompt"] and "images 1-2" in graph["20"]["inputs"]["prompt"]
    try:
        asyncio.run(service.generate_image("a fox"))
    except ValueError as error:
        assert "style" in str(error)
    else:
        raise AssertionError("generate_image without style pictures must fail")


def test_waiting_follows_the_queue_and_fails_only_when_comfy_drops_the_prompt(tmp_path):
    service, comfy = make(tmp_path)
    comfy.drop_after = 0
    try:
        asyncio.run(service._history_until_done("prompt-x"))
    except RuntimeError as error:
        assert "dropped" in str(error)
    else:
        raise AssertionError("a prompt absent from queue and history must fail")


def test_refine_image_redraws_with_anima_and_lora(tmp_path):
    service, comfy = make(tmp_path)
    draft = tmp_path / "draft.png"; draft.write_bytes(png())
    job = asyncio.run(service.refine_image(str(draft), "bell_idol, front view", "bell.safetensors", denoise=0.5))
    assert job["status"] == "completed" and job["path"].endswith("-refine.png")
    graph = comfy.submitted[0]
    assert graph["1"]["inputs"]["unet_name"] == "anima-base-v1.0.safetensors" and graph["23"]["inputs"]["denoise"] == 0.5
