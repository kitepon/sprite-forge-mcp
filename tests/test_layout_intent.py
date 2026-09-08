"""構成案の解釈・訂正・確定境界。外部モデルとGPUは呼ばない。"""
import asyncio
from copy import deepcopy
import json

import pytest

from backend.intent import IntentRequest, Proposal
from backend.sheet_layout import LayoutProposal, LayoutUpdate, legacy_layout
from tests.test_style import make


def proposal(layout):
    return {"summary_ja": "構成の確認", "questions": [], "panels": [dict(p, description_ja=p["label"], reference=None) for p in deepcopy(layout)]}


def test_propose_edit_confirm_preserves_original_and_old_layout_until_confirmed(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("生き物", "a slime")
        before = await service.get_sheet_layout("生き物")
        working = deepcopy(before[:2][::-1])
        working[0]["label"] = "移動中"

        async def interpreter(job, images):
            assert job["sheet_layout"] == before
            assert job["working_layout"] == working
            assert images == []
            result = proposal(working)
            result["panels"][0]["label"] = "跳ねる"
            return result
        service.intent_interpreter = interpreter
        job = await service.interpret_comment(IntentRequest(name="生き物", stage="layout", comment="青い体の移動を載せたい", layout_panels=working, layout_expected=before))
        assert await service.get_sheet_layout("生き物") == before
        chosen = LayoutProposal.model_validate(job["proposal"])
        chosen.panels.reverse()
        chosen.panels[0].label = "体の確認"
        accepted = await service.confirm_sheet_layout(job["job_id"], chosen)
        assert accepted["original_comment"] == "青い体の移動を載せたい"
        assert accepted["proposal"]["panels"][0]["label"] == "跳ねる"
        assert accepted["accepted"]["panels"][0]["label"] == "体の確認"
        assert [p["label"] for p in await service.get_sheet_layout("生き物")] == ["体の確認", "跳ねる"]
        assert (await service.character_info("生き物")).get("intent_conditions", {}) == {}
        assert not comfy.submitted
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["questions", "stale", "reference", "wrong_confirmation", "empty"])
def test_rejects_unresolved_or_mismatched_layout(tmp_path, monkeypatch, failure):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("対象", "test")
        before = await service.get_sheet_layout("対象")
        async def interpret(job, images):
            return proposal(before[:2])
        service.intent_interpreter = interpret
        job = await service.interpret_comment(IntentRequest(name="対象", stage="layout", comment="2項目"))
        candidate = deepcopy(job["proposal"])
        if failure == "questions":
            candidate["questions"] = ["どの画像ですか？"]
        elif failure == "reference":
            candidate["panels"][0]["reference"] = {"record_key": "wrong", "sample_index": 10, "path": "unknown.png"}
        elif failure == "empty":
            for part in candidate["panels"][0]["parts"]:
                part["description_en"] = " "
        elif failure == "stale":
            await service.save_sheet_layout("対象", LayoutUpdate.model_validate({"expected": before, "panels": before[:1]}))
        if failure == "wrong_confirmation":
            with pytest.raises(ValueError, match="構成"):
                await service.confirm_comment_intent(job["job_id"], Proposal(observations=[], changes=[], questions=[]))
        else:
            with pytest.raises(ValueError):
                await service.confirm_sheet_layout(job["job_id"], LayoutProposal.model_validate(candidate))
        assert service.events.load_job(job["job_id"])["status"] == "awaiting_confirmation"
        assert await service.get_sheet_layout("対象") == (before[:1] if failure == "stale" else before)
    asyncio.run(scenario())


def test_layout_cli_has_its_own_strict_schema():
    from backend.intent_cli import execute
    from tests.test_intent_cli import SCHEMA_LEAD, FakeComfy
    comfy = FakeComfy()
    layout = legacy_layout()
    result = asyncio.run(execute({"stage": "layout", "sheet_layout": layout}, [], comfy=comfy))
    prompt = comfy.prompts[-1]
    _, schema_blob = prompt.split("\n" + SCHEMA_LEAD + "\n", 1)
    schema = json.loads(schema_blob)
    assert "panels" in schema["properties"] and "changes" not in schema["properties"]
    for value in schema["$defs"].values():
        if "properties" in value:
            assert set(value["required"]) == set(value["properties"])
    assert "汎用キャラクターシート" in prompt
    assert "一枠に実際に描く被写体数・視点・範囲" in prompt
    assert "その数量と構図を維持" in prompt
    assert "表情で変わる内容はexpressionへ分けます" in prompt
    assert "そのpartのavoid_enへ対象を列挙" in prompt
    assert "共通条件に値が存在しない特徴" in prompt
    assert "removed_keys" in schema["properties"]
    assert "注文で変わる差分だけ" in prompt
    # 差分は現在の構成へ合成され、利用側には全項目の案が届く。
    assert [p["key"] for p in result["proposal"]["panels"]] == [p["key"] for p in layout]
    assert result["proposal"]["panels"][0]["label"] == layout[0]["label"] + "（変更）"
    assert result["proposal"]["panels"][1]["label"] == layout[1]["label"]


def test_layout_change_merges_into_current_layout_preserving_untouched_panels():
    from backend.sheet_layout import LayoutChange, LayoutPanel, merge_layout_change
    current = legacy_layout()[:4]
    changed = dict(current[2], label="水着", description_ja="鎧を水着に変更", reference=None, role_features=["outfit"],
                   parts=[{"feature": "outfit", "description_en": "one-piece swimsuit", "avoid_en": "armor"}])
    added = dict(current[0], key="new_item", label="追加の単品", kind="item", seed_offset=99,
                 description_ja="新しい項目", reference=None)
    change = LayoutChange(summary_ja="3番目を水着に変更", questions=[], removed_keys=[current[1]["key"]],
                          panels=[LayoutPanel.model_validate(changed), LayoutPanel.model_validate(added)])
    merged = merge_layout_change(change, current)
    assert [p.key for p in merged.panels] == [current[0]["key"], current[2]["key"], current[3]["key"], "new_item"]
    assert merged.panels[1].label == "水着"
    assert merged.panels[1].parts[0].description_en == "one-piece swimsuit"
    untouched = merged.panels[0]
    assert untouched.model_dump(exclude={"description_ja", "reference"}) == current[0]
    assert untouched.description_ja == current[0]["label"] and untouched.reference is None
    assert merged.summary_ja == "3番目を水着に変更"


def test_layout_stage_prompt_omits_panel_specs_and_training_captions():
    from backend.intent_runner import interpret
    from tests.test_intent_cli import FakeComfy, _payload_from_prompt
    layout = legacy_layout()[:2]
    base = dict(original_comment="変更", record_kind="character", record_description="", existing_settings={},
                references=[], image_comments=[], base_conditions={}, panel="", sheet_layout=layout,
                panel_specs=[{"key": p["key"]} for p in layout], training_captions=[{"caption_en": "x"}])
    comfy = FakeComfy()
    asyncio.run(interpret({**base, "stage": "layout"}, [], comfy=comfy))
    layout_payload = _payload_from_prompt(comfy.prompts[-1])
    assert "panel_specs" not in layout_payload and "training_captions" not in layout_payload
    assert layout_payload["sheet_layout"] == layout
    asyncio.run(interpret({**base, "stage": "sheet"}, [], comfy=comfy))
    sheet_payload = _payload_from_prompt(comfy.prompts[-1])
    assert sheet_payload["panel_specs"] == base["panel_specs"]
    assert sheet_payload["training_captions"] == base["training_captions"]


def test_adopted_features_and_requested_view_count_reach_prompt_without_common_settings():
    from backend.panel_intent import resolve_panel
    from backend.sheet_layout import panel_from
    design = {"key": "comparison", "section": "比較", "label": "同一人物の二方向", "kind": "full",
              "parts": [{"feature": "subject", "description_en": "same adult man", "avoid_en": ""},
                        {"feature": "face", "description_en": "blue eyes", "avoid_en": ""},
                        {"feature": "composition", "description_en": "two full-body views, front and back", "avoid_en": ""}],
              "role_features": ["composition"], "inherited_features": ["face", "background"], "seed_offset": 0}
    result = resolve_panel(panel_from(design), "person", "he/him", {}, [], {})
    assert "blue eyes" in result["prompt"]
    assert "two full-body views, front and back" in result["prompt"]
    item = {**design, "key": "boots", "kind": "item", "role_features": ["subject"],
            "inherited_features": ["background"], "parts": [
                {"feature": "subject", "description_en": "one pair of brown boots", "avoid_en": "humans, legs, feet"}]}
    result = resolve_panel(panel_from(item), "person", "he/him", {}, [], {})
    assert "one pair of brown boots" in result["prompt"]
    assert "humans" not in result["prompt"] and "humans, legs, feet" in result["negative"]


@pytest.mark.parametrize("boundary", ["interpret", "confirm"])
def test_existing_offset_cannot_acquire_another_key(tmp_path, monkeypatch, boundary):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character("対象", "test")
        before = await service.get_sheet_layout("対象")
        record = service._load_character("対象")
        record["panel_overrides"] = {before[0]["key"]: {"pose": {"description_en": "standing"}}}
        service._save_character(record)
        candidate = proposal(before[:1])

        async def interpret(job, images):
            return candidate
        service.intent_interpreter = interpret
        if boundary == "interpret":
            candidate["panels"][0]["key"] = "renamed_front"
            with pytest.raises(ValueError, match="識別子"):
                await service.interpret_comment(IntentRequest(name="対象", stage="layout", comment="名前を変更"))
        else:
            job = await service.interpret_comment(IntentRequest(name="対象", stage="layout", comment="名前を変更"))
            candidate["panels"][0]["key"] = "renamed_front"
            with pytest.raises(ValueError, match="識別子"):
                await service.confirm_sheet_layout(job["job_id"], LayoutProposal.model_validate(candidate))
        assert service._load_character("対象") == record
    asyncio.run(scenario())


def test_runner_transfers_working_layout_and_not_a_new_current_record():
    from backend.intent_runner import interpret
    from tests.test_intent_cli import FakeComfy, _payload_from_prompt
    before = legacy_layout()
    working = deepcopy(before[:1])
    job = dict(original_comment="一枚", record_kind="character", record_description="", existing_settings={},
               references=[], image_comments=[], base_conditions={}, stage="layout", panel="",
               sheet_layout=before, working_layout=working)
    comfy = FakeComfy()
    result = asyncio.run(interpret(job, [], comfy=comfy))
    payload = _payload_from_prompt(comfy.prompts[-1])
    assert payload["sheet_layout"] == working
    assert "working_layout" not in payload
    assert "recorded_layout" not in payload
    assert result["panels"][0]["key"] == working[0]["key"]


def test_old_manual_draft_cannot_be_rebased_silently_and_discard_keeps_history(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await service.create_character("対象", "test")
        before = await service.get_sheet_layout("対象")
        await service.save_sheet_layout("対象", LayoutUpdate.model_validate({"expected": before, "panels": before[:2]}))
        with pytest.raises(ValueError, match="更新"):
            await service.save_comment(IntentRequest(name="対象", stage="layout", comment="古い案", layout_expected=before, layout_panels=before[:1]))
        job = await service.save_comment(IntentRequest(name="対象", stage="layout", comment="保留にする案"))
        discarded = await service.discard_sheet_layout(job["job_id"])
        assert discarded["status"] == "discarded"
        assert discarded["original_comment"] == "保留にする案"
        assert await service.get_sheet_layout("対象") == before[:2]
        with pytest.raises(ValueError):
            await service.interpret_saved_comment(job["job_id"])
    asyncio.run(scenario())


@pytest.mark.parametrize("face", ["rest", "mcp"])
def test_layout_confirmation_public_faces_share_service(tmp_path, monkeypatch, face):
    from backend import app
    from backend.events import EventStore
    from fastapi.testclient import TestClient
    from fastmcp import Client
    service = app.services
    monkeypatch.setattr(service, "characters_root", tmp_path / "characters")
    monkeypatch.setattr(service, "events", EventStore(tmp_path / "events.ndjson", tmp_path / "jobs"))
    async def scenario():
        await service.create_character("public", "test")
        before = await service.get_sheet_layout("public")
        job = await service.save_comment(IntentRequest(name="public", stage="layout", comment="2項目"))
        value = proposal(before[:2]); job.update(status="awaiting_confirmation", proposal=value)
        service.events.save_job(job)
        if face == "rest":
            with TestClient(app.app) as client:
                result = client.post(f'/api/layout/{job["job_id"]}/confirm', json=value)
                assert result.status_code == 200, result.text
        else:
            async with Client(app.mcp) as client:
                result = await client.call_tool("confirm_sheet_layout", {"job_id": job["job_id"], "proposal": value})
                assert not result.is_error
        assert await service.get_sheet_layout("public") == before[:2]
    asyncio.run(scenario())
