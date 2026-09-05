"""構成案の解釈・訂正・確定境界。外部モデルとGPUは呼ばない。"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

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


def test_layout_cli_has_its_own_strict_schema_and_subscription_command(monkeypatch):
    from backend.intent_cli import run
    proposed = proposal(legacy_layout()[:1])
    def execute(args, *, input, cwd, **kwargs):
        schema = json.loads((cwd / "schema.json").read_text())
        assert "panels" in schema["properties"] and "changes" not in schema["properties"]
        for value in schema["$defs"].values():
            if "properties" in value:
                assert set(value["required"]) == set(value["properties"])
        assert 'forced_login_method="chatgpt"' in args
        assert "汎用キャラクターシート" in input
        (cwd / "result.json").write_text(json.dumps(proposed))
        return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed"}', stderr="")
    monkeypatch.setattr("backend.intent_cli.subprocess.run", execute)
    assert run({"input": {"stage": "layout", "sheet_layout": legacy_layout()}, "images": []})["proposal"] == proposed


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


def test_runner_transfers_working_layout_and_not_a_new_current_record(monkeypatch):
    from backend.intent_runner import interpret
    before = legacy_layout()
    working = deepcopy(before[:1])
    job = dict(original_comment="一枚", record_description="", existing_settings={}, references=[], image_comments=[], base_conditions={}, stage="layout", panel="", sheet_layout=before, working_layout=working)
    class Process:
        returncode = 0
        async def communicate(self, raw):
            assert json.loads(raw)["input"]["sheet_layout"] == working
            return json.dumps({"proposal": proposal(working), "model": "fixture", "elapsed_seconds": 0, "auth": "chatgpt"}).encode(), b""
    async def start(*args, **kwargs):
        return Process()
    monkeypatch.setattr("backend.intent_runner.asyncio.create_subprocess_exec", start)
    assert asyncio.run(interpret(job, []))["panels"][0]["key"] == working[0]["key"]


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
