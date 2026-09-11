"""OKにしたプレビューを教材に足し、サンプルと同じLoRA学習で更新する。"""
import asyncio
import uuid

import pytest

from backend.intent import IntentRequest, Proposal
from backend.preview_reviews import PreviewReview
from tests.test_intent import proposal, setup
from tests.test_style import make


async def settled_grow(service, job):
    task = service._grow_tasks.get(job["job_id"])
    if task is not None:
        await task
    return service.events.load_job(job["job_id"])


def test_preview_order_reaches_prompt_and_ok_images_join_training(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        return proposal(job["references"][0], scope="this_run", text="white cropped top, midriff, separate frilly mini skirt")

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        rec = await service.character_info("probe")
        rec["lora_name"] = "fixture.safetensors"
        rec["samples"][0]["training_caption"] = {"caption_en": "a girl in a white outfit", "appearance_ja": "白い服"}
        service._save_character(rec)
        intent = await service.interpret_comment(IntentRequest(
            name="probe", stage="preview", comment="お腹が見えるセパレートで全身"))
        await service.confirm_comment_intent(intent["job_id"], Proposal.model_validate(intent["proposal"]))
        source = await service.preview_character("probe", count=2, intent_job_id=intent["job_id"])
        assert "white cropped top" in source["prompt"]
        assert "midriff" in source["prompt"]
        await service.save_preview_review(
            "probe", source["job_id"], source["pictures"][0]["id"],
            PreviewReview(rating="ok", revision=0, comment=""))
        started = await service.grow_lora_from_preview("probe", source["job_id"], str(uuid.uuid4()), steps=3)
        assert started["status"] == "running"
        job = await settled_grow(service, started)
        assert job["status"] == "completed"
        record = service._load_character("probe")
        assert record["training_additions"]
        assert "white cropped top" in record["training_additions"][0]["caption_en"]
        trained = service.events.load_job(job["training_job_id"])
        assert trained["status"] == "completed"
        assert any(item["path"].endswith("add-000.png") for item in trained["materials"])
        assert any("white cropped top" in item["caption"] for item in trained["materials"])
        preview = service.events.load_job(job["preview_job_id"])
        plain = service.events.load_job(job["plain_preview_job_id"])
        assert preview["kind"] == "preview"
        assert preview["learning_job_id"] == job["job_id"]
        assert preview["preview_role"] == "with_order"
        assert plain["preview_role"] == "without_order"
        assert preview["paired_job_id"] == plain["job_id"]
        assert "white cropped top" in preview["prompt"]
        assert "white cropped top" not in plain["prompt"]
        assert "standing" not in plain["prompt"] and "front view" not in plain["prompt"]
        assert preview["loras"][0][0] == record["lora_name"]
        assert comfy.submitted[-1]["4"]["inputs"]["lora_name"] == record["lora_name"]

    asyncio.run(scenario())


def test_preview_pair_keeps_same_seed_and_splits_order(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        return proposal(job["references"][0], scope="this_run", text="white cropped top, midriff")

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        rec = await service.character_info("probe")
        rec["lora_name"] = "fixture.safetensors"
        rec["samples"][0]["training_caption"] = {"caption_en": "a girl", "appearance_ja": "少女"}
        service._save_character(rec)
        intent = await service.interpret_comment(IntentRequest(
            name="probe", stage="preview", comment="セパレートで"))
        await service.confirm_comment_intent(intent["job_id"], Proposal.model_validate(intent["proposal"]))
        pair = await service.preview_character_pair("probe", seed=4, count=1, intent_job_id=intent["job_id"])
        plain, ordered = pair["without_order"], pair["with_order"]
        assert plain["seed"] == ordered["seed"] == 4
        assert plain["preview_role"] == "without_order"
        assert ordered["preview_role"] == "with_order"
        assert plain["paired_job_id"] == ordered["job_id"]
        assert "white cropped top" not in plain["prompt"]
        assert "standing" not in plain["prompt"] and "front view" not in plain["prompt"]
        assert "white cropped top" in ordered["prompt"]
        assert "standing" not in ordered["prompt"] and "front view" not in ordered["prompt"]

    asyncio.run(scenario())


def test_start_preview_pair_requires_order_and_builds_both_sets(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def interpret(job, images):
        return proposal(job["references"][0], scope="this_run", text="white cropped top, midriff")

    service.intent_interpreter = interpret

    async def scenario():
        await setup(service, tmp_path)
        rec = await service.character_info("probe")
        rec["lora_name"] = "fixture.safetensors"
        rec["samples"][0]["training_caption"] = {"caption_en": "a girl", "appearance_ja": "少女"}
        service._save_character(rec)
        with pytest.raises(ValueError, match="制作への注文"):
            await service.start_preview_pair("probe", count=1)
        intent = await service.interpret_comment(IntentRequest(
            name="probe", stage="preview", comment="セパレートで"))
        await service.confirm_comment_intent(intent["job_id"], Proposal.model_validate(intent["proposal"]))
        started = await service.start_preview_pair(
            "probe", seed=4, count=1, intent_job_id=intent["job_id"])
        assert started["kind"] == "preview_pair"
        assert started["status"] == "running"
        await service._preview_pair_tasks[started["job_id"]]
        job = service.events.load_job(started["job_id"])
        assert job["status"] == "completed"
        plain = service.events.load_job(job["plain_preview_job_id"])
        ordered = service.events.load_job(job["preview_job_id"])
        assert plain["preview_role"] == "without_order"
        assert ordered["preview_role"] == "with_order"
        assert "white cropped top" not in plain["prompt"]
        assert "standing" not in plain["prompt"]
        assert "white cropped top" in ordered["prompt"]
        assert "standing" not in ordered["prompt"]
        assert plain["paired_job_id"] == ordered["job_id"]

    asyncio.run(scenario())


def test_grow_without_ok_is_an_error(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        rec = await service.character_info("probe")
        rec["lora_name"] = "fixture.safetensors"
        rec["samples"][0]["training_caption"] = {"caption_en": "a girl", "appearance_ja": "少女"}
        service._save_character(rec)
        source = await service.preview_character("probe", count=1)
        with pytest.raises(ValueError, match="OKの画像"):
            await service.grow_lora_from_preview("probe", source["job_id"], str(uuid.uuid4()), steps=3)

    asyncio.run(scenario())
