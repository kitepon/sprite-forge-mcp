from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

import pytest

from PIL import Image, ImageDraw

from backend import bible, box
from backend.bible import PANELS, panel_prompt, subject_tag
from backend.events import EventStore
from backend.services import Services
from tests.test_style import approve_sheet, panel_orders


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

    async def queue(self):
        return {"queue_running": [], "queue_pending": []}

    async def free(self):
        return


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
    with pytest.raises(ValueError, match="train_character_lora"):
        run(service.generate_character_bible("Bell"))

    # stage 2: train (only when asked), then preview in seconds
    from tests.test_training_materials import accept_observations
    run(accept_observations(service, "Bell"))
    training = run(service.train_character_lora("Bell", steps=3))
    assert training["status"] == "completed" and (Path(training["dataset"]) / "001.txt").read_text() == "bell, white long coat, hood"
    record = run(service.character_info("Bell"))
    assert record["lora_name"] == training["lora_name"] and record["train_job"] == training["job_id"]
    preview = run(service.preview_character("Bell", "waving", seed=7, count=2))
    assert len(preview["pictures"]) == 2
    assert comfy.submitted[-1]["20"]["inputs"]["text"] == "bell, waving, 1girl, solo, simple background, white background"
    assert comfy.submitted[-1]["4"]["inputs"]["lora_name"] == training["lora_name"] and comfy.submitted[-1]["23"]["inputs"]["seed"] == 8
    comfy.submitted.clear()

    # 第3段階: 設定画を開き、パネルごとに候補から採用する
    job = run(service.generate_character_bible("Bell", seed=1))
    assert job["status"] == "completed" and job["completed_panels"] == 0 and not panel_orders(comfy)
    retry = run(service.retry_panel("Bell", "cos_dress", count=2))
    assert "only one character" in retry["prompt"] and len(retry["candidates"]) == 2
    first = panel_orders(comfy)[0]
    assert first["20"]["inputs"]["text"] == retry["prompt"]
    assert first["21"]["inputs"]["text"] == retry["negative"] and first["22"]["inputs"]["width"] == 832
    assert first["4"]["class_type"] == "LoraLoader" and "8" not in first
    assert first["25"]["inputs"]["filename_prefix"] == "sprite-forge/bible"
    assert "multiple people" in first["21"]["inputs"]["text"]
    adopted = run(service.adopt_panel("Bell", retry["job_id"], retry["candidates"][0]["seed"]))
    assert Path(adopted["adopted"]["path"]).is_file()
    assert Image.open(job["sheet_path"]).width == 2040
    assert "APPROVED REFERENCE SHEET" not in open(job["html_path"], encoding="utf-8").read()
    assert run(service.character_info("Bell"))["bible"]["sheet_path"] == job["sheet_path"]
    redraw = run(service.redraw_panel("Bell", "cos_dress", "ball gown, floor-length dress", seed=9, avoid="frills, boots"))
    assert "ball gown" in redraw["prompt"] and "only one character" in redraw["prompt"]
    assert comfy.submitted[-1]["21"]["inputs"]["text"] == bible.NEGATIVE + ", frills, boots" and redraw["previous"].endswith(".png")
    assert comfy.submitted[-1]["20"]["inputs"]["text"] == redraw["prompt"]
    assert run(service.character_info("Bell"))["panel_overrides"] == {"cos_dress": {"tags": "ball gown, floor-length dress", "avoid": "frills, boots", "seed": 9}}
    picture = run(service.generate_from_bible("Bell", "waving, stage", seed=5))
    assert comfy.submitted[-1]["20"]["inputs"]["text"] == "bell, waving, stage" and picture["lora_name"] == training["lora_name"]
    assert [c["name"] for c in run(service.list_characters())] == ["Bell"]


def test_adopting_an_existing_lora_skips_training(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    asyncio.run(service.create_character("Bell", "she/her", lora_name="BellGrok.safetensors", trigger="bell_idol"))
    job = asyncio.run(service.generate_character_bible("Bell"))
    retry = asyncio.run(service.retry_panel("Bell", "turn_front", count=1))
    assert job["status"] == "completed"
    assert retry["prompt"].startswith("bell_idol, 1girl, ")
    assert panel_orders(comfy)[0]["20"]["inputs"]["text"] == retry["prompt"]


def test_panel_prompts_carry_content_only_and_the_subject_comes_from_the_description():
    assert subject_tag("he/him cloud knight") == "1boy" and subject_tag("a robot") == "1other"
    item = next(p for p in PANELS if p.kind == "item")
    assert panel_prompt(item, "bell", "she/her").startswith("bell, no humans, ")
    for panel in PANELS:
        text = panel_prompt(panel, "bell", "she/her")
        for word in ("cel", "painterly", "glossy", "masterpiece", "best quality", "high detail"):
            assert word not in text
    assert [p["key"] for p in asyncio.run(Services(comfy=ComfyFixture()).list_bible_panels())][:2] == ["turn_front", "turn_34"]
    assert bible.reference_key(next(p for p in PANELS if p.key == "turn_front")) == "front"
    assert bible.reference_key(next(p for p in PANELS if p.key == "turn_side")) == "side"
    assert bible.reference_key(next(p for p in PANELS if p.key == "turn_back")) == "back"
    assert bible.reference_key(next(p for p in PANELS if p.kind == "face")) == "head"
    by_key = {p.key: p for p in PANELS}
    assert bible.draw_mode(by_key["ex_smile"]) == "img2img" and bible.draw_mode(by_key["turn_front"]) == "img2img"
    assert bible.draw_mode(by_key["cos_casual"]) == "pose" and bible.draw_mode(by_key["body_front"]) == "pose"
    assert bible.draw_mode(by_key["act_run"]) == "txt2img" and bible.draw_mode(by_key["chibi_big"]) == "txt2img"
    assert bible.draw_mode(by_key["item_head"]) == "txt2img"
    swim = bible.Panel("cos_swim", "ALTERNATE COSTUMES", "SWIM", "full",
                      (("composition", "full body"), ("pose", "standing, front view"),
                       ("outfit", "bikini swimsuit, two-piece swimwear")))
    assert bible.draw_mode(swim) == "pose" and bible.reference_key(swim) == "front"


def test_sheet_keeps_left_full_body_even_when_a_side_view_is_taller():
    def mask_bytes(box, size=(120, 80)):
        image = Image.new("L", size, 0)
        ImageDraw.Draw(image).rectangle(box, fill=255)
        output = BytesIO()
        image.save(output, "PNG")
        return output.getvalue()

    face = mask_bytes((8, 4, 28, 22))
    front = mask_bytes((4, 22, 38, 72))
    side = mask_bytes((70, 8, 88, 76))
    masks = bible.figure_masks([face, side, front])
    assert len(masks) == 2
    assert masks[0].getbbox()[0] < masks[1].getbbox()[0]
    views = bible.pose_views([Image.new("RGB", (10, 20), c) for c in ("#f00", "#0f0", "#00f", "#ff0")])
    assert views["front"].getpixel((0, 0)) == (255, 0, 0)
    assert views["side"].getpixel((0, 0)) == (0, 255, 0)
    assert views["three_quarter"].getpixel((0, 0)) == (0, 0, 255)
    assert views["back"].getpixel((0, 0)) == (255, 255, 0)


def test_retry_panel_uses_anima_txt2img_with_lora(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    run(service.generate_character_bible("Bell"))
    retry = run(service.retry_panel("Bell", "ex_smile", count=1))
    graph = panel_orders(comfy)[0]
    assert retry["prompt"].startswith("bell, 1girl, portrait")
    assert graph["20"]["inputs"]["text"] == retry["prompt"]
    assert graph["23"]["inputs"]["denoise"] == 1.0 and "8" not in graph
    second = run(service.generate_character_bible("Bell", seed=2))
    assert second["job_id"] == run(service.character_info("Bell"))["bible"]["job_id"]


def test_japanese_names_get_an_ascii_key_and_still_work(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    record = asyncio.run(service.create_character("ベル", "she/her", trigger="bell"))
    assert record["name"] == "ベル" and record["key"].startswith("n") and record["key"].isascii() and record["trigger"] == "bell"
    assert asyncio.run(service.character_info("ベル"))["key"] == record["key"]
    assert bible.safe_name("ベル") == bible.safe_name("ベル") != bible.safe_name("ベル2")


def test_failed_panel_retry_preserves_previous_bible(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    first = run(service.generate_character_bible("Bell"))
    retry = run(service.retry_panel("Bell", "turn_front", count=1))
    run(service.adopt_panel("Bell", retry["job_id"], retry["candidates"][0]["seed"]))
    before = run(service.character_info("Bell"))
    sheet = Path(before["bible"]["sheet_path"]).read_bytes()

    async def fail(*args, **kwargs):
        raise RuntimeError("retry failed")
    monkeypatch.setattr(service, "_run_edit", fail)
    with pytest.raises(RuntimeError, match="retry failed"):
        run(service.retry_panel("Bell", "turn_front", count=1))
    assert run(service.character_info("Bell")) == before
    assert Path(before["bible"]["sheet_path"]).read_bytes() == sheet
    failed = next(j for j in service.events.list_jobs() if j["status"] == "failed")
    assert failed["error"] == "retry failed"


def test_opening_bible_again_keeps_the_same_ledger(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    first = run(service.generate_character_bible("Bell"))
    retry = run(service.retry_panel("Bell", "turn_front", count=1))
    run(service.adopt_panel("Bell", retry["job_id"], retry["candidates"][0]["seed"]))
    second = run(service.generate_character_bible("Bell", seed=7))
    assert second["job_id"] == first["job_id"]
    current = run(service.character_info("Bell"))["bible"]
    assert current["job_id"] == first["job_id"]
    fixed = run(service.redraw_panel("Bell", "turn_front", "waving"))
    assert Path(fixed["path"]).parent == Path(current["panels_dir"])


def test_retry_panel_offers_candidates_and_adopting_one_replaces_only_that_panel(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    colors = iter(["#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff"])
    async def distinct(_image): return png(next(colors))
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    approve_sheet(service, "Bell")
    run(service.generate_character_bible("Bell", seed=1))
    before = run(service.character_info("Bell"))
    panel_path = Path(before["bible"]["panels_dir"]) / "turn_front.png"
    assert not panel_path.exists()
    sheet_before = Path(before["bible"]["sheet_path"]).read_bytes()
    service._view = distinct; comfy.submitted.clear()

    retry = run(service.retry_panel("Bell", "turn_front", count=4))
    assert retry["status"] == "completed" and retry["kind"] == "panel_retry" and len(panel_orders(comfy)) == 4
    seeds = [c["seed"] for c in retry["candidates"]]
    assert len(set(seeds)) == 4 and retry["current_seed"] not in seeds
    assert [w["23"]["inputs"]["seed"] for w in panel_orders(comfy)] == seeds
    assert all(w["20"]["inputs"]["text"] == retry["prompt"] for w in panel_orders(comfy))
    assert retry["prompt"].startswith("bell, 1girl, full body, standing, front view")
    assert "only one character" in retry["prompt"]
    candidate_bytes = [Path(c["path"]).read_bytes() for c in retry["candidates"]]
    assert len({b for b in candidate_bytes}) == 4 and all(Path(c["path"]).parent.name == "candidates" for c in retry["candidates"])
    assert not panel_path.exists() and run(service.character_info("Bell")) == before

    adopted = run(service.adopt_panel("Bell", retry["job_id"], seeds[1]))
    assert adopted["adopted"]["seed"] == seeds[1] and panel_path.read_bytes() == candidate_bytes[1]
    history = Path(before["bible"]["panels_dir"]) / "history"
    assert not adopted["adopted"]["previous"]
    after = run(service.character_info("Bell"))
    assert after["bible"]["panel_overrides"]["turn_front"] == {"seed": seeds[1]} and after["panel_overrides"]["turn_front"] == {"seed": seeds[1]}
    assert Path(after["bible"]["sheet_path"]).read_bytes() != sheet_before and after["bible"]["job_id"] == before["bible"]["job_id"]

    run(service.adopt_panel("Bell", retry["job_id"], seeds[2]))
    assert panel_path.read_bytes() == candidate_bytes[2]
    assert (history / f"turn_front-{retry['job_id'][:8]}-{seeds[2]}.png").read_bytes() == candidate_bytes[1]
    with pytest.raises(ValueError):
        run(service.adopt_panel("Bell", retry["job_id"], 12345))

    service._view = view_image; comfy.submitted.clear()
    again = run(service.retry_panel("Bell", "turn_front", count=1))
    assert again["current_seed"] == seeds[2]


def test_redraw_supports_bibles_saved_before_versioned_paths(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("Bell", "she/her", lora_name="bell.safetensors"))
    approve_sheet(service, "Bell")
    run(service.generate_character_bible("Bell"))
    first = run(service.retry_panel("Bell", "turn_front", count=1))
    run(service.adopt_panel("Bell", first["job_id"], first["candidates"][0]["seed"]))
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
