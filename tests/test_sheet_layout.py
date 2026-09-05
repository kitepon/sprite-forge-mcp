"""構成の保存・生成時の写し・旧パネル修正の対応を検証する。"""
import asyncio
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from PIL import Image

from backend.intent import IntentRequest, Proposal
from backend.sheet_layout import LayoutUpdate, legacy_layout, panel_from
from backend.panel_intent import resolve_panel
from tests.test_sheet_panel_intent import change
from tests.test_style import make


def update(before, panels):
    return LayoutUpdate.model_validate({"expected": before, "panels": panels})


def test_saves_custom_order_labels_and_preserves_only_unchanged_content(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("custom", "he/him", lora_name="fixture.safetensors")
        before = await service.get_sheet_layout("custom")
        record = await service.character_info("custom")
        record["panel_overrides"] = {"cos_armor": {"tags": "heavy armor"}, "turn_front": {"tags": "sitting"}}
        service._save_character(record)
        chosen = deepcopy([before[16], before[0]])
        chosen[0]["label"] = "水着"
        chosen[0]["parts"][-1]["description_en"] = "a blue swimsuit"
        chosen[1]["label"] = "正面"
        assert await service.save_sheet_layout("custom", update(before, chosen)) == chosen
        after = await service.character_info("custom")
        assert after["panel_overrides"] == {"turn_front": {"tags": "sitting"}}
        assert await service.get_sheet_layout("custom") == chosen
        history = next(j for j in service.events.list_jobs() if j["kind"] == "sheet_layout")
        assert history["panel_overrides_before"]["cos_armor"]["tags"] == "heavy armor"
        with pytest.raises(ValueError, match="更新"):
            await service.save_sheet_layout("custom", update(before, chosen))
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["duplicate", "path", "empty", "role"])
def test_rejects_invalid_external_layout(mutation):
    panels = legacy_layout()[:2]
    if mutation == "duplicate":
        panels[1]["key"] = panels[0]["key"]
    elif mutation == "path":
        panels[0]["key"] = "../other"
    elif mutation == "empty":
        panels = []
    else:
        panels[0]["role_features"].append("outfit")
    with pytest.raises((ValidationError, ValueError)):
        update(legacy_layout(), panels)


def test_generates_custom_panels_with_stable_seeds_and_old_sheet_keeps_its_layout(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("custom", "a quadrupedal dragon", lora_name="fixture.safetensors")
        before = await service.get_sheet_layout("custom")
        chosen = deepcopy([before[2], before[0]])
        for p, label in zip(chosen, ["SIDE", "FRONT"]):
            p["label"], p["section"] = label, "CREATURE"
            p["parts"] = [{"feature": "subject", "description_en": "a quadrupedal dragon", "avoid_en": "human"},
                           {"feature": "pose", "description_en": label.lower() + " view", "avoid_en": ""}]
            p["role_features"] = ["subject", "pose"]
        await service.save_sheet_layout("custom", update(before, chosen))
        first = await service.generate_character_bible("custom", seed=10)
        assert first["total_panels"] == len(comfy.submitted) == 2
        assert [r["seed"] for r in first["panel_requests"]] == [12, 10]
        assert all("human" in r["negative"] for r in first["panel_requests"])
        original_html = Path(first["html_path"]).read_text()
        assert "CREATURE" in original_html and "ALTERNATE COSTUMES" not in original_html
        after = deepcopy(chosen[::-1])
        after[1]["label"] = "NEW NAME"
        after[1]["parts"][0]["description_en"] = "a limbless slime"
        await service.save_sheet_layout("custom", update(chosen, after))
        assert Path(first["html_path"]).read_text() == original_html
        await service.redraw_panel("custom", chosen[0]["key"], "a red dragon", input_mode="english")
        record = await service.character_info("custom")
        assert "NEW NAME" not in Path(first["html_path"]).read_text()
        assert record["bible"]["layout"] == chosen
        assert chosen[0]["key"] not in record["panel_overrides"]
        assert record["bible"]["panel_overrides"][chosen[0]["key"]]["tags"] == "a red dragon"
        second = await service.generate_character_bible("custom", seed=10)
        assert [r["seed"] for r in second["panel_requests"]] == [10, 12]
        assert "a limbless slime" in second["panel_requests"][1]["prompt"]
        assert "a red dragon" not in second["panel_requests"][1]["prompt"]
    asyncio.run(scenario())


def test_layout_changes_invalidate_old_sheet_order_before_confirm_or_generate(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("custom", "he/him", lora_name="fixture.safetensors")
        job = await service.save_comment(IntentRequest(name="custom", stage="sheet", comment="衣装を変更"))
        proposal = Proposal(observations=[], questions=[], changes=[])
        job.update(status="awaiting_confirmation", proposal=proposal.model_dump())
        service.events.save_job(job)
        before = await service.get_sheet_layout("custom")
        await service.save_sheet_layout("custom", update(before, before[:2]))
        with pytest.raises(ValueError, match="構成"):
            await service.confirm_comment_intent(job["job_id"], proposal)
        job.update(status="confirmed", accepted=proposal.model_dump(), effective_conditions={}, common_conditions={})
        service.events.save_job(job)
        with pytest.raises(ValueError, match="構成"):
            await service.generate_character_bible("custom", intent_job_id=job["job_id"])
    asyncio.run(scenario())


def test_custom_role_is_not_replaced_by_whole_sheet_temporary_outfit():
    p = deepcopy(legacy_layout()[16])
    p["key"], p["label"] = "custom_outfit", "Swimsuit"
    p["parts"][-1]["description_en"] = "a swimsuit"
    spec = panel_from(p)
    result = resolve_panel(spec, "fixture", "he/him", {}, [change("outfit", "a uniform")], {})
    assert "a swimsuit" in result["prompt"] and "a uniform" not in result["prompt"]
    result = resolve_panel(spec, "fixture", "he/him", {}, [change("outfit", "a raincoat", panel=p["key"])], {})
    assert "a raincoat" in result["prompt"] and "a swimsuit" not in result["prompt"]


def test_more_than_23_panels_are_all_composed(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("custom", "he/him", lora_name="fixture.safetensors")
        before = await service.get_sheet_layout("custom")
        panels = []
        for i in range(29):
            p = deepcopy(before[0])
            p.update(key=f"custom_{i}", section=f"SECTION {i}", label=f"PANEL {i}", seed_offset=i)
            panels.append(p)
        await service.save_sheet_layout("custom", update(before, panels))
        result = await service.generate_character_bible("custom")
        assert result["total_panels"] == result["completed_panels"] == 29
        html = Path(result["html_path"]).read_text()
        assert all(f"PANEL {i}" in html for i in range(29))
        with Image.open(result["sheet_path"]) as image:
            assert image.height > 10000
            assert image.getpixel((0, image.height - 1)) != (0, 0, 0)
    asyncio.run(scenario())


def test_layout_changed_during_generation_is_not_rolled_back(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    original = comfy.submit

    async def scenario():
        await service.create_character("custom", "he/him", lora_name="fixture.safetensors")
        before = await service.get_sheet_layout("custom")
        chosen = before[:2]
        await service.save_sheet_layout("custom", update(before, chosen))
        changed = deepcopy(chosen)
        changed[0]["parts"][1]["description_en"] = "sitting"

        async def submit(graph, client_id):
            if not comfy.submitted:
                await service.save_sheet_layout("custom", update(chosen, changed))
            return await original(graph, client_id)
        comfy.submit = submit
        result = await service.generate_character_bible("custom")
        record = await service.character_info("custom")
        assert record["sheet_layout"] == changed
        assert record["bible"]["layout"] == result["layout"] == chosen
    asyncio.run(scenario())


@pytest.mark.parametrize("face", ["rest", "mcp"])
def test_public_layout_endpoints_share_the_saved_record(tmp_path, monkeypatch, face):
    from backend import app
    from fastapi.testclient import TestClient
    from fastmcp import Client
    service = app.services
    for field, value in {"characters_root": tmp_path / "characters", "generated_root": tmp_path / "generated",
                         "uploads_root": tmp_path / "uploads"}.items():
        monkeypatch.setattr(service, field, value)
    from backend.events import EventStore
    monkeypatch.setattr(service, "events", EventStore(tmp_path / "events.ndjson", tmp_path / "jobs"))

    async def scenario():
        await service.create_character("custom", "he/him")
        before = await service.get_sheet_layout("custom")
        body = {"expected": before, "panels": before[:2]}
        if face == "rest":
            with TestClient(app.app) as client:
                assert client.get("/api/characters/custom/layout").json() == before
                response = client.post("/api/characters/custom/layout", json=body)
                assert response.status_code == 200, response.text
                assert response.json() == before[:2]
        else:
            async with Client(app.mcp) as client:
                result = await client.call_tool("save_sheet_layout", {"name": "custom", "layout": body})
                assert not result.is_error
        assert await service.get_sheet_layout("custom") == before[:2]
        assert len(await service.list_bible_panels("custom")) == 2
    asyncio.run(scenario())


def test_panel_order_is_bound_to_the_actual_sheet_even_with_same_layout(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("custom", "he/him", lora_name="fixture.safetensors")
        before = await service.get_sheet_layout("custom")
        await service.save_sheet_layout("custom", update(before, before[:1]))
        await service.generate_character_bible("custom")
        job = await service.save_comment(IntentRequest(name="custom", stage="panel", panel="turn_front", comment="手を振って"))
        value = Proposal(observations=[], questions=[], changes=[])
        job.update(status="awaiting_confirmation", proposal=value.model_dump())
        service.events.save_job(job)
        await service.generate_character_bible("custom", seed=2)
        with pytest.raises(ValueError, match="設定画"):
            await service.confirm_comment_intent(job["job_id"], value)
    asyncio.run(scenario())


def test_old_sheet_keeps_redraw_metadata_when_a_new_sheet_finishes(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    original = service._run_edit

    async def scenario():
        await service.create_character("custom", "he/him", lora_name="fixture.safetensors")
        before = await service.get_sheet_layout("custom")
        await service.save_sheet_layout("custom", update(before, before[:1]))
        first = await service.generate_character_bible("custom")

        async def run_edit(job_id, graph):
            if service.events.load_job(job_id)["kind"] == "redraw_panel":
                await service.generate_character_bible("custom", seed=2)
            return await original(job_id, graph)
        service._run_edit = run_edit
        result = await service.redraw_panel("custom", "turn_front", tags="waving", input_mode="english")
        assert (await service.character_info("custom"))["bible"]["job_id"] != first["job_id"]
        assert result["source_bible"]["job_id"] == first["job_id"]
        assert result["source_bible"]["panel_overrides"]["turn_front"]["tags"] == "waving"
        assert service.events.load_job(first["job_id"])["panel_overrides"]["turn_front"]["tags"] == "waving"
    asyncio.run(scenario())
