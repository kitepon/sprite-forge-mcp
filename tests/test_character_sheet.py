"""一枚シートの生成・合否と、設定画の起点優先を確認する。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend import bible
from backend.services import Services
from tests.test_style import make, png


def assert_reference_sheet(job, graph, seed):
    assert job["kind"] == "character_sheet" and job["status"] == "completed"
    assert job["seed"] == seed and job["prompt"] == graph["20"]["inputs"]["text"]
    assert job["negative"] == graph["21"]["inputs"]["text"]
    assert bible.QUALITY_NEGATIVE in job["negative"]
    assert graph["22"]["inputs"]["width"] == 1536 and graph["22"]["inputs"]["height"] == 1024
    assert "the world's most attractive character design sheet" in job["prompt"]
    assert "strict accurate human anatomy" in job["prompt"]
    assert "white background" in job["prompt"]
    assert "full body, standing, front view, looking at viewer" not in job["prompt"]
    assert bible.SINGLE_VIEW_NEGATIVE not in job["negative"]


def test_bible_does_not_start_without_an_approved_sheet(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    asyncio.run(service.create_character("probe", "she/her", lora_name="fixture.safetensors"))
    with pytest.raises(ValueError, match="approve_character_sheet"):
        asyncio.run(service.generate_character_bible("probe"))
    assert comfy.submitted == []


def test_generate_without_lora_does_not_train(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    asyncio.run(service.create_character("probe", "she/her"))
    try:
        asyncio.run(service.generate_character_sheet("probe"))
    except ValueError as error:
        assert "train_character_lora" in str(error)
    else:
        raise AssertionError("一枚シートは学習を始めない")
    assert comfy.submitted == []


def test_generate_approve_and_regenerate_update_ledger(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("probe", "she/her", lora_name="fixture.safetensors"))
    job = run(service.generate_character_sheet("probe", seed=11))
    record = run(service.character_info("probe"))
    graph = comfy.submitted[-1]
    assert_reference_sheet(job, graph, 11)
    assert Path(job["path"]).is_file()
    assert record["pending_sheet"] == job["path"]
    assert record["pending_sheet_job_id"] == job["job_id"]
    assert "approved_sheet" not in record
    assert graph["23"]["inputs"]["seed"] == 11
    assert graph["4"]["inputs"]["lora_name"] == "fixture.safetensors"

    approved = service.approve_character_sheet("probe", job["job_id"])
    dest = Path(approved["approved_sheet"])
    assert dest.name == "approved_sheet.png" and dest.is_file()
    assert dest.read_bytes() == Path(job["path"]).read_bytes()
    assert approved["approved_sheet_job_id"] == job["job_id"]

    try:
        service.approve_character_sheet("probe", "missing")
    except ValueError as error:
        assert "一枚シート" in str(error)
    else:
        raise AssertionError("別ジョブは合格にできない")

    redraw = run(service.regenerate_character_sheet("probe", seed=0))
    fresh = run(service.character_info("probe"))
    redraw_graph = comfy.submitted[-1]
    assert_reference_sheet(redraw, redraw_graph, redraw["seed"])
    assert redraw["job_id"] != job["job_id"]
    assert redraw["seed"] > 0
    assert redraw["prompt"] == job["prompt"]
    assert redraw["negative"] == job["negative"]
    assert fresh["pending_sheet"] == redraw["path"]
    assert fresh["pending_sheet_job_id"] == redraw["job_id"]
    assert fresh["approved_sheet"] == approved["approved_sheet"]


def test_approved_sheet_is_bible_source(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    run = asyncio.run
    run(service.create_character("probe", "she/her", lora_name="fixture.safetensors"))
    sample = tmp_path / "sample.png"
    sample.write_bytes(png("#ff8844"))
    run(service.add_samples("probe", str(sample), "white coat"))
    sheet = run(service.generate_character_sheet("probe", seed=3))
    approved = service.approve_character_sheet("probe", sheet["job_id"])
    bible = run(service.generate_character_bible("probe", seed=3))
    record = run(service.character_info("probe"))
    assert bible["source"] == approved["approved_sheet"]
    assert record["bible"]["source"] == approved["approved_sheet"]
    assert Path(record["bible"]["source"]).read_bytes() == Path(sheet["path"]).read_bytes()


def test_ui_keeps_sheet_judgment_before_bible():
    root = Path(__file__).resolve().parents[1] / "web"
    flows = (root / "flows.js").read_text()
    main = (root / "main.js").read_text()
    preview = (root / "preview.js").read_text()
    api = (root / "api.js").read_text()
    assert "['キャラクター', '参考画像', '学習', 'プレビュー', '一枚シート', '設定画']" in flows
    assert "['キャラクター', '画風', 'プレビュー', '一枚シート', '設定画']" in flows
    assert "合格した一枚を、設定画の起点にしてください。" in flows
    assert "世界一魅力的なキャラクターシートを、人体の構造を厳密に守って白地に描きます" in flows
    assert "API.regenerateSheet(name, 0, style)" in flows
    assert "if (job) API.character(name).then(record => refresh(record, job))" in flows
    assert "pending_sheet ? 4" in main
    assert "この学習結果を使って一枚シートへ" in preview
    assert "/sheet/approve" in api
    app = (root.parent / "backend" / "app.py").read_text()
    jobs = (root / "jobs.js").read_text()
    assert '("/api/characters/{name}/sheet", ["POST"], services.generate_character_sheet)' in app
    assert '("generate_character_sheet", services.generate_character_sheet)' in app
    assert "character_sheet: '一枚シート'" in jobs
