from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image

from backend import bible, box
from backend.bible import PANELS, panel_prompt, subject_tag
from backend.events import EventStore
from backend.services import Services


def png(color: str = "#44aaff") -> bytes:
    image = Image.new("RGBA", (24, 32), color)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


class ComfyFixture:
    def __init__(self):
        self.submitted: list[dict] = []
        self.base_url = "http://fox:8188"
        class _Client:
            async def post(self, url, json): assert url.endswith("/free")
        self.client = _Client()

    async def upload(self, content, name):
        assert content.startswith(b"\x89PNG")
        return name

    async def submit(self, workflow, client_id):
        self.submitted.append(workflow)
        return f"prompt-{len(self.submitted)}"

    async def history(self, prompt_id):
        return {"status": {"completed": True, "status_str": "success"},
                "outputs": {"25": {"images": [{"filename": f"{prompt_id}.png"}]}}}


async def view_image(_image):
    return png()


def make(tmp_path, monkeypatch):
    async def copied(local, remote, **kwargs): return 0, ""
    async def lines(*args, **kwargs):
        yield "steps: 100%|##########| 3/3 [00:03<00:00,  1.24it/s]"
    monkeypatch.setattr(box, "copy_tree_to_box", copied)
    monkeypatch.setattr(box, "copy_to_box", copied)
    monkeypatch.setattr(box, "stream_training", lines)
    comfy = ComfyFixture()
    service = Services(comfy=comfy, events=EventStore(tmp_path / "events.ndjson", tmp_path / "jobs"),
                       generated_root=tmp_path / "generated", uploads_root=tmp_path / "uploads")
    service._view = view_image
    return service, comfy


def test_bible_trains_a_lora_from_the_pictures_then_draws_every_panel_with_it(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(png("#ff8844")); b.write_bytes(png("#8844ff"))
    stale = tmp_path / "generated" / "bible_Bell_panels" / "old.png"
    stale.parent.mkdir(parents=True); stale.write_bytes(png())

    job = asyncio.run(service.generate_character_bible(f"{a},{b}", "Bell", "she/her idol", "idol", steps=3,
                                                       captions="white crop top|long coat"))

    assert job["status"] == "completed" and job["trigger"] == "bell" and job["lora_name"].startswith("Bell_")
    assert not stale.exists()
    dataset = tmp_path / "generated" / "lora_Bell_dataset"
    assert (dataset / "0.txt").read_text() == "bell, white crop top" and (dataset / "1.txt").read_text() == "bell, long coat"
    assert len(job["panels"]) == len(PANELS) == 23 and len(comfy.submitted) == 23
    first = comfy.submitted[0]
    assert first["4"]["inputs"]["lora_name"] == job["lora_name"] and first["1"]["inputs"]["unet_name"] == "anima-base-v1.0.safetensors"
    assert first["20"]["inputs"]["text"] == "bell, 1girl, full body, standing, front view, looking at viewer, arms at sides, simple background, white background"
    assert first["21"]["inputs"]["text"] == bible.NEGATIVE and first["22"]["inputs"]["width"] == 832
    face = comfy.submitted[6]
    assert face["22"]["inputs"] == {"width": 1024, "height": 1024, "batch_size": 1} and "portrait" in face["20"]["inputs"]["text"]
    assert Image.open(job["sheet_path"]).width == 2040 and "TRAINING PICTURES" in open(job["html_path"], encoding="utf-8").read()
    assert asyncio.run(service.bible_status(job["job_id"]))["status"] == "completed"
    picture = asyncio.run(service.generate_from_bible("Bell", "waving, stage", seed=5))
    assert picture["lora_name"] == job["lora_name"] and comfy.submitted[-1]["20"]["inputs"]["text"] == "bell, waving, stage"


def test_bible_reuses_an_existing_lora_and_skips_training(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    a = tmp_path / "a.png"; a.write_bytes(png())
    job = asyncio.run(service.generate_character_bible(str(a), "Bell", "she/her", lora_name="BellGrok.safetensors", trigger="bell_idol"))
    assert job["lora_name"] == "BellGrok.safetensors" and "train_job" not in job
    assert not (tmp_path / "generated" / "lora_Bell_dataset").exists()
    assert comfy.submitted[0]["20"]["inputs"]["text"].startswith("bell_idol, 1girl, ")


def test_panel_prompts_carry_content_only_and_the_subject_comes_from_the_description():
    assert subject_tag("he/him cloud knight") == "1boy" and subject_tag("a robot") == "1other"
    item = next(p for p in PANELS if p.kind == "item")
    assert panel_prompt(item, "bell", "she/her").startswith("bell, no humans, ")
    for panel in PANELS:
        text = panel_prompt(panel, "bell", "she/her")
        for word in ("cel", "painterly", "glossy", "masterpiece", "best quality", "high detail"):
            assert word not in text


def test_redraw_panel_replaces_one_panel_by_words_keeps_the_old_one_and_rebuilds_the_sheet(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    a = tmp_path / "a.png"; a.write_bytes(png())
    job = asyncio.run(service.generate_character_bible(str(a), "Bell", "she/her", "idol", lora_name="BellGrok.safetensors", trigger="bell_idol"))
    before = (tmp_path / "generated" / "bible_Bell.png").stat().st_mtime_ns
    redraw = asyncio.run(service.redraw_panel("Bell", "cos_dress", "ball gown, floor-length dress, elbow gloves", seed=9))
    assert redraw["status"] == "completed" and redraw["prompt"] == "bell_idol, 1girl, ball gown, floor-length dress, elbow gloves, simple background, white background"
    assert comfy.submitted[-1]["23"]["inputs"]["seed"] == 9 and comfy.submitted[-1]["4"]["inputs"]["lora_name"] == "BellGrok.safetensors"
    assert (tmp_path / "generated" / "bible_Bell_panels" / "cos_dress.png").is_file() and redraw["previous"].endswith(".png")
    assert (tmp_path / "generated" / "bible_Bell.png").stat().st_mtime_ns >= before
    assert [p["key"] for p in asyncio.run(service.list_bible_panels())][:2] == ["turn_front", "turn_34"]
    try:
        asyncio.run(service.redraw_panel("Bell", "nope"))
    except ValueError as error:
        assert "list_bible_panels" in str(error)
    else:
        raise AssertionError("unknown panel must fail")
