"""一枚シートは廃止。設定画はパネルごとに候補を出して採用する。"""
from __future__ import annotations

import asyncio
from pathlib import Path

from backend.services import Services
from tests.test_style import make, png, panel_orders


def test_replace_opens_a_new_empty_bible(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("probe", "she/her", lora_name="fixture.safetensors"))
    first = run(service.generate_character_bible("probe"))
    retry = run(service.retry_panel("probe", "turn_front", count=1))
    run(service.adopt_panel("probe", retry["job_id"], retry["candidates"][0]["seed"]))
    assert (Path(first["panels_dir"]) / "turn_front.png").is_file()
    second = run(service.generate_character_bible("probe", replace=True))
    assert second["job_id"] != first["job_id"]
    assert second["completed_panels"] == 0
    assert not (Path(second["panels_dir"]) / "turn_front.png").is_file()
    assert (Path(first["panels_dir"]) / "turn_front.png").is_file()
    panels = run(service.list_bible_panels("probe", generated=True))
    assert panels[0]["key"] == "turn_front" and panels[0]["adopted"] is False


def test_bible_opens_without_a_one_sheet(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    asyncio.run(service.create_character("probe", "she/her", lora_name="fixture.safetensors"))
    job = asyncio.run(service.generate_character_bible("probe"))
    assert job["kind"] == "character_bible" and job["status"] == "completed"
    assert job["completed_panels"] == 0 and job["panels"] == []
    assert comfy.submitted == []
    assert Path(job["sheet_path"]).is_file()


def test_generate_without_lora_does_not_train(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    asyncio.run(service.create_character("probe", "she/her"))
    try:
        asyncio.run(service.generate_character_bible("probe"))
    except ValueError as error:
        assert "train_character_lora" in str(error)
    else:
        raise AssertionError("設定画は学習を始めない")
    assert comfy.submitted == []


def test_panel_candidates_are_adopted_and_can_be_retried(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("probe", "she/her", lora_name="fixture.safetensors"))
    opened = run(service.generate_character_bible("probe"))
    retry = run(service.retry_panel("probe", "turn_front", count=2))
    assert retry["kind"] == "panel_retry" and len(retry["candidates"]) == 2
    assert len(panel_orders(comfy)) == 2
    assert "only one character" in retry["prompt"]
    assert "8" not in panel_orders(comfy)[0] and panel_orders(comfy)[0]["23"]["inputs"]["denoise"] == 1.0
    chosen = retry["candidates"][0]
    adopted = run(service.adopt_panel("probe", retry["job_id"], chosen["seed"]))
    path = Path(adopted["adopted"]["path"])
    assert path.is_file() and path.name == "turn_front.png"
    record = run(service.character_info("probe"))
    assert record["bible"]["job_id"] == opened["job_id"]
    again = run(service.retry_panel("probe", "turn_front", count=2))
    assert len(again["candidates"]) == 2
    swapped = run(service.adopt_panel("probe", again["job_id"], again["candidates"][1]["seed"]))
    assert Path(swapped["adopted"]["previous"]).is_file()


def test_grow_lora_from_adopted_panels(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("probe", "she/her", lora_name="fixture.safetensors"))
    sample = tmp_path / "sample.png"
    sample.write_bytes(png("#ff8844"))
    run(service.add_samples("probe", str(sample), "white coat"))
    from tests.test_training_materials import accept_observations
    run(accept_observations(service, "probe"))
    retry = run(service.retry_panel("probe", "turn_front", count=1))
    run(service.adopt_panel("probe", retry["job_id"], retry["candidates"][0]["seed"]))
    trained = run(service.grow_lora_from_panels("probe", steps=3))
    assert trained["kind"] == "lora_train" and trained["status"] == "completed"
    record = run(service.character_info("probe"))
    assert record["training_additions"]
    assert record["training_additions"][0]["source_image_id"] == "panel:turn_front"


def test_ui_drops_one_sheet_and_picks_ten_per_panel():
    root = Path(__file__).resolve().parents[1] / "web"
    flows = (root / "flows.js").read_text()
    main = (root / "main.js").read_text()
    preview = (root / "preview.js").read_text()
    api = (root / "api.js").read_text()
    assert "['キャラクター', '参考画像', '学習', 'プレビュー', '設定画']" in flows
    assert "['キャラクター', '画風', 'プレビュー', '設定画']" in flows
    assert "一枚シート" not in flows
    assert "このパネルを10枚出す" in flows
    assert "設定画を全部作り直す" in flows
    assert "採用したパネルでLoRAを更新する" in flows
    assert "pending_sheet" not in main
    assert "この学習結果を使って設定画へ" in preview
    assert "/sheet/approve" not in api
    app = (root.parent / "backend" / "app.py").read_text()
    jobs = (root / "jobs.js").read_text()
    assert "generate_character_sheet" not in app
    assert "grow_lora_from_panels" in app
    assert "panel_retry: 'パネルの候補'" in jobs
