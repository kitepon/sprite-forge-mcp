"""通常の学習入口は準備を連続実行し、判断が必要な時だけ止まる。"""
import asyncio

import pytest

from backend.bible import subject_tag
from backend.intent import IntentRequest, Proposal
from tests.test_style import make, png


async def setup(service, tmp_path, kind="character", wish=False, questions=False):
    source = tmp_path / "source.png"
    source.write_bytes(png())
    await getattr(service, f"create_{kind}")("検証用", "成人女性")
    add = service.add_samples if kind == "character" else service.add_style_samples
    await add("検証用", str(source), "この画像の衣装を採用")
    await service.save_comment(IntentRequest(name="検証用", kind=kind, stage="samples", comment="顔立ちを保つ"))
    await service.save_comment(IntentRequest(name="検証用", kind=kind, stage="training", comment="体形も保つ"))
    async def interpret(job, _images):
        assert "顔立ちを保つ" in job["original_comment"]
        assert "体形も保つ" in job["original_comment"]
        assert job["image_comments"] == ["この画像の衣装を採用"]
        return {"observations": [{"reference": ref, "appearance_ja": "赤いコートの成人女性", "caption_en": "adult woman, red coat"} for ref in job["references"]],
                "questions": ["どの衣装を使いますか？"] if questions else [],
                "changes": [{"feature": "outfit", "scope": "persistent", "panel_key": None, "reference": job["references"][0],
                             "description_en": "red coat", "avoid_en": "", "avoid_ja": "", "reason_ja": "この衣装を採用"}] if wish else []}
    service.intent_interpreter = interpret


@pytest.mark.parametrize("kind", ["character", "style"])
def test_learning_runs_reading_materials_and_training_from_one_action(tmp_path, monkeypatch, kind):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, kind)
        job = await service.start_learning("検証用", kind, steps=3)
        trained = service.events.load_job(job["training_job_id"])
        record = await getattr(service, f"{kind}_info")("検証用")
        assert trained["status"] == "completed"
        assert record["train_job"] == trained["job_id"]
        assert trained["materials"][0]["caption"].endswith("adult woman, red coat")
        assert "採用" not in trained["materials"][0]["caption"]
        assert trained["materials"][0]["original_comment"] == "この画像の衣装を採用"
        with pytest.raises(ValueError, match="学習開始前"):
            await service.confirm_learning(job["job_id"], Proposal.model_validate(job["proposal"]))
    asyncio.run(scenario())


def test_wishes_are_reviewed_once_then_training_starts(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, wish=True)
        job = await service.start_learning("検証用", steps=3)
        assert job["status"] == "awaiting_confirmation"
        assert not (await service.character_info("検証用"))["lora_name"]
        job = await service.confirm_learning(job["job_id"], Proposal.model_validate(job["proposal"]))
        assert service.events.load_job(job["training_job_id"])["status"] == "completed"
        assert (await service.character_info("検証用"))["intent_conditions"]["outfit"]["description_en"] == "red coat"
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["question", "comment", "sample"])
def test_unanswered_or_changed_input_does_not_start_training(tmp_path, monkeypatch, change):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, wish=True, questions=change == "question")
        job = await service.start_learning("検証用", steps=3)
        if change == "comment":
            await service.save_comment(IntentRequest(name="検証用", stage="samples", comment="希望を変更"))
        if change == "sample":
            await service.set_caption("検証用", 0, "画像への希望を変更")
        with pytest.raises(ValueError):
            await service.confirm_learning(job["job_id"], Proposal.model_validate(job["proposal"]))
        assert not (await service.character_info("検証用"))["lora_name"]
        assert not any(j["kind"] == "lora_train" for j in service.events.list_jobs())
    asyncio.run(scenario())


def test_failed_reading_is_visible_and_never_trains(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path)
        async def fail(*_args):
            raise RuntimeError("解析サービスに接続できません")
        service.intent_interpreter = fail
        with pytest.raises(RuntimeError, match="解析サービス"):
            await service.start_learning("検証用", steps=3)
        latest = service.events.list_jobs()[0]
        assert latest["status"] == "failed" and "learning_steps" in latest
        assert "解析サービス" in latest["error"]
        assert not (await service.character_info("検証用"))["lora_name"]
    asyncio.run(scenario())


def test_japanese_registration_description_preserves_subject_kind():
    assert subject_tag("銀髪の成人女性。旅人。") == "1girl"
    assert subject_tag("成人男性の旅人") == "1boy"
    assert subject_tag("青いドラゴン") == "1other"
