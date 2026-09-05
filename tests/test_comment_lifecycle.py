"""非同期処理中に保存したコメントを保つ。一時データと疑似GPUだけで再現する。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend import box
from tests.test_style import make, png
from tests.test_training_materials import accept_observations


@pytest.mark.parametrize("kind", ["character", "style"])
def test_caption_saved_during_training_survives_completion(tmp_path, monkeypatch, kind):
    service, _ = make(tmp_path, monkeypatch)
    picture = tmp_path / "reference.png"
    picture.write_bytes(png())
    create = getattr(service, f"create_{kind}")
    add = service.add_samples if kind == "character" else service.add_style_samples
    save = service.set_caption if kind == "character" else service.set_style_caption
    info = getattr(service, f"{kind}_info")
    train = getattr(service, f"train_{kind}_lora")
    during = []

    async def trainer(*args, **kwargs):
        await save("probe", 0, "new observation")
        during.append((await info("probe"))["samples"][0]["caption"])
        yield "steps: 100%|##########| 3/3 [00:03<00:00, 1.24it/s]"

    monkeypatch.setattr(box, "stream_training", trainer)

    async def scenario():
        await create("probe", "she/her")
        await add("probe", str(picture), "old observation")
        await accept_observations(service, "probe", kind)
        job = await train("probe", steps=3)
        return job, await info("probe")

    job, record = asyncio.run(scenario())
    # 学習の完了と、途中の保存が実際に成功したことを先に確認する。
    if job["status"] != "completed" or during != ["new observation"]:
        pytest.fail(f"reproduction setup failed: status={job['status']}, during={during}")
    assert record["samples"][0]["caption"] == "new observation", record["samples"]
    assert record["lora_name"] == job["lora_name"]
    assert record["train_job"] == job["job_id"]
    assert record["steps"] == 3
    assert (Path(job["dataset"]) / "000.txt").read_text() == (
        f"{record['trigger']}, old observation"
    )


def test_caption_saved_during_sheet_generation_survives_completion(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    picture = tmp_path / "reference.png"
    picture.write_bytes(png())
    original_submit = comfy.submit
    during = []

    async def submit(workflow, client_id):
        if not during:
            await service.set_caption("probe", 0, "new observation")
            during.append((await service.character_info("probe"))["samples"][0]["caption"])
        return await original_submit(workflow, client_id)

    comfy.submit = submit

    async def scenario():
        await service.create_character("probe", "she/her", lora_name="fixture.safetensors")
        await service.add_samples("probe", str(picture), "old observation")
        job = await service.generate_character_bible("probe")
        return job, await service.character_info("probe")

    job, record = asyncio.run(scenario())
    if job["status"] != "completed" or during != ["new observation"] or len(comfy.submitted) != 23:
        pytest.fail(f"reproduction setup failed: status={job['status']}, during={during}, panels={len(comfy.submitted)}")
    assert record["samples"][0]["caption"] == "new observation", record["samples"]
    assert record["bible"]["job_id"] == job["job_id"]


@pytest.mark.parametrize("kind", ["character", "style"])
def test_caption_saved_while_resolving_another_sample_survives(tmp_path, monkeypatch, kind):
    service, _ = make(tmp_path, monkeypatch)
    picture = tmp_path / "reference.png"
    picture.write_bytes(png())
    create = getattr(service, f"create_{kind}")
    add = service.add_samples if kind == "character" else service.add_style_samples
    save = service.set_caption if kind == "character" else service.set_style_caption
    info = getattr(service, f"{kind}_info")
    resolve = service._resolve_image

    async def resolve_with_edit(ref):
        await save("probe", 0, "edited during upload")
        return await resolve(ref)

    async def scenario():
        await create("probe", "she/her")
        await add("probe", str(picture), "old observation")
        monkeypatch.setattr(service, "_resolve_image", resolve_with_edit)
        added = await add("probe", str(picture), "second observation")
        return added, await info("probe")

    added, record = asyncio.run(scenario())
    assert [s["caption"] for s in record["samples"]] == ["edited during upload", "second observation"]
    assert added == record


@pytest.mark.parametrize("replace_sheet", [False, True])
def test_redraw_keeps_edits_saved_during_generation(tmp_path, monkeypatch, replace_sheet):
    service, comfy = make(tmp_path, monkeypatch)
    picture = tmp_path / "reference.png"
    picture.write_bytes(png())
    panel_root = tmp_path / "panels"
    panel_root.mkdir()
    (panel_root / "turn_front.png").write_bytes(png())
    initial_bible = {"job_id": "original", "panels_dir": str(panel_root),
                     "sheet_path": str(tmp_path / "sheet.png"), "html_path": str(tmp_path / "sheet.html"),
                     "at": "before redraw"}
    replacement_bible = {"job_id": "newer", "panels_dir": str(tmp_path / "new-panels"),
                         "sheet_path": str(tmp_path / "new-sheet.png"), "html_path": str(tmp_path / "new-sheet.html"),
                         "at": "new sheet time"}
    original_submit = comfy.submit

    async def submit(workflow, client_id):
        await service.set_caption("probe", 0, "edited during redraw")
        latest = await service.character_info("probe")
        latest["panel_overrides"] = {"turn_back": {"tags": "waving", "avoid": "hat", "seed": 9}}
        if replace_sheet:
            latest["bible"] = replacement_bible
        service._save_character(latest)
        return await original_submit(workflow, client_id)

    async def scenario():
        record = await service.create_character("probe", "she/her", lora_name="fixture.safetensors")
        record = await service.add_samples("probe", str(picture), "old observation")
        record["bible"] = initial_bible
        service._save_character(record)
        comfy.submit = submit
        job = await service.redraw_panel("probe", "turn_front", tags="standing", seed=4)
        return job, await service.character_info("probe")

    job, record = asyncio.run(scenario())
    assert job["status"] == "completed"
    assert record["samples"][0]["caption"] == "edited during redraw"
    assert record["panel_overrides"] == {
        "turn_back": {"tags": "waving", "avoid": "hat", "seed": 9},
        "turn_front": {"tags": "standing", "avoid": "", "seed": 4},
    }
    if replace_sheet:
        assert record["bible"] == replacement_bible
    else:
        assert record["bible"]["job_id"] == "original"
        assert record["bible"]["at"] != "before redraw"
