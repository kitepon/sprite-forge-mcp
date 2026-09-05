from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

import pytest

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
                       generated_root=tmp_path / "generated", uploads_root=tmp_path / "uploads",
                       characters_root=tmp_path / "characters")
    service._view = view_image
    return service, comfy


def test_three_stages_each_stop_for_correction(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(png("#ff8844")); b.write_bytes(png("#8844ff"))
    run = asyncio.run

    # stage 1: samples — collect, look (samples.png), correct captions, drop one
    record = run(service.create_character("Bell", "she/her idol", "idol"))
    assert record["trigger"] == "bell" and record["samples"] == [] and record["lora_name"] == ""
    record = run(service.add_samples("Bell", f"{a},{b}", captions="white crop top|long coat"))
    assert [s["caption"] for s in record["samples"]] == ["white crop top", "long coat"] and (tmp_path / "characters" / "Bell" / "samples.png").is_file()
    record = run(service.set_caption("Bell", 1, "white long coat, hood"))
    record = run(service.remove_sample("Bell", 0))
    assert [s["index"] for s in record["samples"]] == [1] and not (tmp_path / "characters" / "Bell" / "samples" / "000.png").exists()
    try:
        run(service.generate_character_bible("Bell"))
    except ValueError as error:
        assert "train_character_lora" in str(error)
    else:
        raise AssertionError("the bible must not train by itself")

    # stage 2: train (only when asked), then preview in seconds
    from tests.test_training_materials import accept_observations
    run(accept_observations(service, "Bell"))
    training = run(service.train_character_lora("Bell", steps=3))
    assert training["status"] == "completed" and (Path(training["dataset"]) / "001.txt").read_text() == "bell, white long coat, hood"
    record = run(service.character_info("Bell"))
    assert record["lora_name"] == training["lora_name"] and record["train_job"] == training["job_id"]
    preview = run(service.preview_character("Bell", "waving", seed=7, count=2))
    assert len(preview["pictures"]) == 2 and comfy.submitted[-1]["20"]["inputs"]["text"] == "bell, 1girl, waving, simple background, white background"
    assert comfy.submitted[-1]["4"]["inputs"]["lora_name"] == training["lora_name"] and comfy.submitted[-1]["23"]["inputs"]["seed"] == 8
    comfy.submitted.clear()

    # stage 3: the sheet, then a redraw by words
    job = run(service.generate_character_bible("Bell", seed=1))
    assert job["status"] == "completed" and len(job["panels"]) == len(PANELS) == 23 and len(comfy.submitted) == 23
    first = comfy.submitted[0]
    assert first["20"]["inputs"]["text"] == "bell, 1girl, full body, standing, front view, looking at viewer, arms at sides, simple background, white background"
    assert first["21"]["inputs"]["text"] == bible.NEGATIVE and first["22"]["inputs"]["width"] == 832
    assert Image.open(job["sheet_path"]).width == 2040 and "TRAINING PICTURES" in open(job["html_path"], encoding="utf-8").read()
    assert run(service.character_info("Bell"))["bible"]["sheet_path"] == job["sheet_path"]
    redraw = run(service.redraw_panel("Bell", "cos_dress", "ball gown, floor-length dress", seed=9, avoid="frills, boots"))
    assert redraw["prompt"] == "bell, 1girl, ball gown, floor-length dress, simple background, white background"
    assert comfy.submitted[-1]["21"]["inputs"]["text"] == bible.NEGATIVE + ", frills, boots" and redraw["previous"].endswith(".png")
    assert run(service.character_info("Bell"))["panel_overrides"] == {"cos_dress": {"tags": "ball gown, floor-length dress", "avoid": "frills, boots", "seed": 9}}
    comfy.submitted.clear()
    run(service.generate_character_bible("Bell", seed=1))  # the correction sticks for the next sheet
    dress = comfy.submitted[[p.key for p in PANELS].index("cos_dress")]
    assert dress["20"]["inputs"]["text"] == redraw["prompt"] and dress["21"]["inputs"]["text"].endswith("frills, boots") and dress["23"]["inputs"]["seed"] == 9
    picture = run(service.generate_from_bible("Bell", "waving, stage", seed=5))
    assert comfy.submitted[-1]["20"]["inputs"]["text"] == "bell, waving, stage" and picture["lora_name"] == training["lora_name"]
    assert [c["name"] for c in run(service.list_characters())] == ["Bell"]


def test_adopting_an_existing_lora_skips_training(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    asyncio.run(service.create_character("Bell", "she/her", lora_name="BellGrok.safetensors", trigger="bell_idol"))
    job = asyncio.run(service.generate_character_bible("Bell"))
    assert job["lora_name"] == "BellGrok.safetensors" and comfy.submitted[0]["20"]["inputs"]["text"].startswith("bell_idol, 1girl, ")


def test_panel_prompts_carry_content_only_and_the_subject_comes_from_the_description():
    assert subject_tag("he/him cloud knight") == "1boy" and subject_tag("a robot") == "1other"
    item = next(p for p in PANELS if p.kind == "item")
    assert panel_prompt(item, "bell", "she/her").startswith("bell, no humans, ")
    for panel in PANELS:
        text = panel_prompt(panel, "bell", "she/her")
        for word in ("cel", "painterly", "glossy", "masterpiece", "best quality", "high detail"):
            assert word not in text
    assert [p["key"] for p in asyncio.run(Services(comfy=ComfyFixture()).list_bible_panels())][:2] == ["turn_front", "turn_34"]


def test_japanese_names_get_an_ascii_key_and_still_work(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    record = asyncio.run(service.create_character("ベル", "she/her", trigger="bell"))
    assert record["name"] == "ベル" and record["key"].startswith("n") and record["key"].isascii() and record["trigger"] == "bell"
    assert asyncio.run(service.character_info("ベル"))["key"] == record["key"]
    assert bible.safe_name("ベル") == bible.safe_name("ベル") != bible.safe_name("ベル2")


@pytest.mark.parametrize("failure", ["panel", "sheet", "html"])
def test_failed_regeneration_preserves_previous_bible_and_history(tmp_path, monkeypatch, failure):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    first = run(service.generate_character_bible("Bell"))
    redraw = run(service.redraw_panel("Bell", "turn_front", "waving"))
    before = run(service.character_info("Bell"))
    paths = [Path(p) for p in first["panels"] + [first["sheet_path"], first["html_path"], redraw["previous"]]]
    contents = {p: p.read_bytes() for p in paths}

    def fail(*args, **kwargs):
        raise RuntimeError("regeneration failed")

    if failure == "panel":
        original = service._run_edit
        calls = 0
        async def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                fail()
            return await original(*args)
        monkeypatch.setattr(service, "_run_edit", fail_second)
    else:
        monkeypatch.setattr(bible, "compose_model_sheet" if failure == "sheet" else "write_html", fail)
    with pytest.raises(RuntimeError, match="regeneration failed"):
        run(service.generate_character_bible("Bell", seed=7))
    assert run(service.character_info("Bell")) == before
    assert all(p.exists() and p.read_bytes() == data for p, data in contents.items())
    failed = next(j for j in service.events.list_jobs() if j["status"] == "failed")
    assert failed["error"] == "regeneration failed"


def test_successful_regeneration_publishes_new_paths_and_redraw_uses_them(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    first = run(service.generate_character_bible("Bell"))
    old_paths = [Path(p) for p in first["panels"] + [first["sheet_path"], first["html_path"]]]
    old_contents = {p: p.read_bytes() for p in old_paths}
    second = run(service.generate_character_bible("Bell", seed=7))
    assert second["panels_dir"] != first["panels_dir"]
    assert second["sheet_path"] != first["sheet_path"]
    assert second["html_path"] != first["html_path"]
    current = run(service.character_info("Bell"))["bible"]
    assert current["job_id"] == second["job_id"]
    fixed = run(service.redraw_panel("Bell", "turn_front", "waving"))
    assert fixed["sheet_path"] == current["sheet_path"]
    assert fixed["html_path"] == current["html_path"]
    assert Path(fixed["path"]).parent == Path(current["panels_dir"])
    assert all(p.read_bytes() == data for p, data in old_contents.items())


def test_redraw_supports_bibles_saved_before_versioned_paths(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    run(service.generate_character_bible("Bell"))
    record = run(service.character_info("Bell"))
    info = record["bible"]
    legacy_panels = tmp_path / "characters" / "Bell" / "bible" / "panels"
    Path(info["panels_dir"]).rename(legacy_panels)
    info["panels_dir"] = str(legacy_panels)
    for field, extension in (("sheet_path", "png"), ("html_path", "html")):
        destination = tmp_path / "generated" / f"bible_Bell.{extension}"
        Path(info[field]).rename(destination)
        info[field] = str(destination)
    service._save_character(record)
    fixed = run(service.redraw_panel("Bell", "turn_front", "waving"))
    assert fixed["sheet_path"] == info["sheet_path"]
    assert fixed["html_path"] == info["html_path"]
    assert Path(fixed["path"]).parent == legacy_panels
