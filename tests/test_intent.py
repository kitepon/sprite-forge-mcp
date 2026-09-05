"""原文・参照・有効範囲の保存を、一時台帳だけで確かめる。"""
import asyncio

import pytest

from backend.intent import IntentRequest, Proposal, PREVIEW_TAGS, preview_content
from tests.test_style import make, png


def proposal(ref=None, scope="persistent", feature="outfit", text="separate jacket and skirt"):
    return {"observations": [], "questions": [], "changes": [{
        "feature": feature, "scope": scope, "panel_key": None, "reference": ref,
        "description_en": text, "avoid_en": "", "avoid_ja": "", "reason_ja": "指定された特徴を採用"}]}


async def setup(service, tmp_path):
    picture = tmp_path / "input.png"
    picture.write_bytes(png())
    await service.create_character("probe", "she/her")
    return await service.add_samples("probe", str(picture), "画像についての注文")


def test_original_survives_model_failure(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def fail(job, images):
        assert service.events.load_job(job["job_id"])["original_comment"] == "  4枚目を使いたい\n"
        assert len(images) == 1
        raise RuntimeError("契約枠の上限")

    service.intent_interpreter = fail

    async def scenario():
        await setup(service, tmp_path)
        with pytest.raises(RuntimeError, match="契約枠"):
            await service.interpret_comment(IntentRequest(name="probe", comment="  4枚目を使いたい\n"))
        return await service.list_comment_intents("probe")

    jobs = asyncio.run(scenario())
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["original_comment"] == "  4枚目を使いたい\n"


def test_confirm_preserves_unrelated_conditions_and_separates_this_run(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        return proposal(job["references"][0])

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        job = await service.interpret_comment(IntentRequest(name="probe", comment="衣装は1枚目"))
        assert "intent_conditions" not in await service.character_info("probe")
        rec = await service.character_info("probe")
        rec["intent_conditions"] = {"hair": proposal(feature="hair", text="short hair")["changes"][0]}
        service._save_character(rec)
        edited = job["proposal"]
        edited["changes"][0]["description_en"] = "edited outfit"
        edited["changes"] += proposal(scope="this_run", feature="pose", text="side view")["changes"]
        accepted = await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(edited))
        return accepted, await service.character_info("probe")

    job, rec = asyncio.run(scenario())
    assert rec["intent_conditions"]["outfit"]["description_en"] == "edited outfit"
    assert rec["intent_conditions"]["hair"]["description_en"] == "short hair"
    assert "pose" not in rec["intent_conditions"]
    assert job["effective_conditions"]["pose"]["description_en"] == "side view"


@pytest.mark.parametrize("kind", ["character", "style"])
def test_removed_sample_index_is_not_reused(tmp_path, monkeypatch, kind):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        picture = tmp_path / "input.png"
        picture.write_bytes(png())
        create = service.create_character if kind == "character" else service.create_style
        add = service.add_samples if kind == "character" else service.add_style_samples
        remove = service.remove_sample if kind == "character" else service.remove_style_sample
        await create("probe", "she/her")
        rec = await add("probe", str(picture))
        old = rec["samples"][0]
        await remove("probe", old["index"])
        rec = await add("probe", str(picture))
        return old, rec["samples"][0]

    old, new = asyncio.run(scenario())
    assert new["index"] > old["index"]
    assert new["path"] != old["path"]


@pytest.mark.parametrize("conflict", ["reference", "feature", "recreated", "scope", "duplicate"])
def test_confirm_reports_conflicts_without_changing_conditions(tmp_path, monkeypatch, conflict):
    service, _ = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        return proposal(job["references"][0])

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        job = await service.interpret_comment(IntentRequest(name="probe", comment="衣装は1枚目"))
        proposed = Proposal.model_validate(job["proposal"])
        if conflict == "reference":
            await service.remove_sample("probe", 0)
        elif conflict == "feature":
            rec = await service.character_info("probe")
            rec["intent_conditions"] = {"outfit": proposal(text="different outfit")["changes"][0]}
            service._save_character(rec)
        elif conflict == "recreated":
            await service.create_character("probe", "new character")
        elif conflict == "scope":
            proposed.changes[0].scope = "panel"
            proposed.changes[0].panel_key = "turn_front"
        else:
            proposed.changes.append(proposed.changes[0].model_copy())
        before = await service.character_info("probe")
        with pytest.raises(ValueError):
            await service.confirm_comment_intent(job["job_id"], proposed)
        assert await service.character_info("probe") == before
        assert service.events.load_job(job["job_id"])["status"] == "awaiting_confirmation"

    asyncio.run(scenario())


def test_preview_uses_confirmed_words_and_keeps_interpretation_job(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        result = proposal(job["references"][0])
        result["changes"][0]["avoid_en"] = "hat"
        result["changes"][0]["avoid_ja"] = "帽子"
        return result

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        rec = await service.character_info("probe")
        rec["lora_name"] = "fixture.safetensors"
        service._save_character(rec)
        intent = await service.interpret_comment(IntentRequest(name="probe", stage="preview", comment="帽子を外し、衣装は1枚目"))
        await service.confirm_comment_intent(intent["job_id"], Proposal.model_validate(intent["proposal"]))
        job = await service.preview_character("probe", count=2, intent_job_id=intent["job_id"])
        assert job["job_id"] != intent["job_id"]
        assert service.events.load_job(intent["job_id"])["status"] == "confirmed"
        assert job["intent_job_id"] == intent["job_id"]
        assert job["loras"] == [("fixture.safetensors", 0.8)]
        assert "separate jacket and skirt" in job["prompt"]
        assert "hat" in job["negative"]
        assert comfy.submitted[-1]["20"]["inputs"]["text"] == job["prompt"]
        assert [picture["seed"] for picture in job["pictures"]] == [1, 2]

    asyncio.run(scenario())


def test_saved_order_is_used_by_interpreter(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    seen = []

    async def interpret(job, images):
        seen.extend(ref["sample_index"] for ref in job["references"])
        return proposal(job["references"][0])

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        await service.add_samples("probe", str(tmp_path / "input.png"))
        job = await service.save_comment(IntentRequest(name="probe", comment="1枚目", sample_indices=[1, 0]))
        assert job["status"] == "draft"
        assert not seen
        await service.interpret_saved_comment(job["job_id"])

    asyncio.run(scenario())
    assert seen == [1, 0]


def test_model_output_must_reference_the_input(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        return proposal({**job["references"][0], "sample_index": 999})

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        with pytest.raises(ValueError, match="渡していない"):
            await service.interpret_comment(IntentRequest(name="probe", comment="衣装"))
        assert (await service.list_comment_intents("probe"))[0]["status"] == "failed"

    asyncio.run(scenario())


def test_preview_replaces_only_owned_defaults():
    conditions = {"pose": proposal(feature="pose", text="side view")["changes"][0],
                  "outfit": proposal(text="blue jacket")["changes"][0]}
    prompt = preview_content(PREVIEW_TAGS, conditions)
    assert prompt == "full body, side view, blue jacket"
    assert preview_content("custom pose", {}) == "custom pose"
    with pytest.raises(ValueError, match="同時"):
        preview_content("custom pose", conditions)


def test_preview_interpretation_receives_stage_defaults_without_persisting_them(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        assert job["stage_conditions"]["pose"]["description_en"] == "standing, front view, looking at viewer"
        assert job["stage_conditions"]["composition"]["description_en"] == "full body"
        return proposal(scope="this_run", feature="pose", text="standing, side view")

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        job = await service.interpret_comment(IntentRequest(name="probe", stage="preview", comment="今回は横向き"))
        await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(job["proposal"]))
        rec = await service.character_info("probe")
        assert rec["intent_conditions"] == {}
        assert service.events.load_job(job["job_id"])["stage_conditions"] == job["stage_conditions"]
        other = await service.save_comment(IntentRequest(name="probe", stage="samples", comment="参考画像"))
        assert other["stage_conditions"] == {}
        await service.create_style("paint")
        style = await service.save_comment(IntentRequest(name="paint", kind="style", stage="preview", comment="画風を確認"))
        assert style["stage_conditions"] == {}

    asyncio.run(scenario())


def test_unconnected_style_change_is_not_persisted(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        return proposal(feature="style", text="brush texture")

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        job = await service.interpret_comment(IntentRequest(name="probe", comment="筆のタッチを変えたい"))
        with pytest.raises(ValueError, match="未完了"):
            await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(job["proposal"]))
        assert "intent_conditions" not in await service.character_info("probe")

    asyncio.run(scenario())
