"""通常の学習入口は準備を連続実行し、判断が必要な時だけ止まる。"""
import asyncio

import pytest

from backend.bible import subject_tag
from backend.intent import IntentRequest, Proposal
from tests.test_style import make, png


async def settled_learning(service, job):
    task = service._learning_tasks.get(job["job_id"])
    if task is not None:
        await task
    return service.events.load_job(job["job_id"])


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
                "training_samples": [{"reference": ref, "priority": "normal", "features": [], "reason_ja": "通常の教材として使います"} for ref in job["references"]],
                "questions": ["どの衣装を使いますか？"] if questions else [],
                "changes": [{"feature": "outfit", "scope": "persistent", "panel_key": None, "reference": job["references"][0],
                             "description_en": "red coat", "avoid_en": "", "avoid_ja": "", "reason_ja": "この衣装を採用"}] if wish else []}
    service.intent_interpreter = interpret


@pytest.mark.parametrize("kind", ["character", "style"])
def test_learning_runs_reading_materials_and_training_from_one_action(tmp_path, monkeypatch, kind):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, kind)
        job = await settled_learning(service, await service.start_learning("検証用", kind, steps=3))
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


def test_start_learning_returns_before_reading_finishes(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        started = asyncio.Event()

        async def slow(job, images):
            started.set()
            await asyncio.Event().wait()

        service.intent_interpreter = slow
        job = await service.start_learning("検証用", steps=3)
        assert job["status"] == "running"
        await started.wait()
        assert service.events.load_job(job["job_id"])["status"] == "running"
        assert not job.get("training_job_id")
        service._learning_tasks[job["job_id"]].cancel()
        with pytest.raises(asyncio.CancelledError):
            await service._learning_tasks[job["job_id"]]

    asyncio.run(scenario())


def test_wishes_are_applied_without_another_confirmation(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, wish=True)
        job = await settled_learning(service, await service.start_learning("検証用", steps=3))
        assert service.events.load_job(job["training_job_id"])["status"] == "completed"
        assert job["accepted"]["changes"][0]["reason_ja"] == "この衣装を採用"
        assert job["accepted_observations"][0]["appearance_ja"] == "赤いコートの成人女性"
        assert (await service.character_info("検証用"))["intent_conditions"]["outfit"]["description_en"] == "red coat"
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["question", "comment", "sample"])
def test_unanswered_or_changed_input_does_not_start_training(tmp_path, monkeypatch, change):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, wish=True, questions=True)
        job = await settled_learning(service, await service.start_learning("検証用", steps=3))
        assert job["status"] == "awaiting_confirmation"
        if change != "question":
            job["proposal"]["questions"] = []
        if change == "comment":
            await service.save_comment(IntentRequest(name="検証用", stage="samples", comment="希望を変更"))
        if change == "sample":
            await service.set_caption("検証用", 0, "画像への希望を変更")
        with pytest.raises(ValueError):
            await service.confirm_learning(job["job_id"], Proposal.model_validate(job["proposal"]))
        assert not (await service.character_info("検証用"))["lora_name"]
        assert not any(j["kind"] == "lora_train" for j in service.events.list_jobs())
    asyncio.run(scenario())


def test_answering_a_question_continues_without_another_approval(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, wish=True, questions=True)
        paused = await settled_learning(service, await service.start_learning("検証用", steps=3))
        assert paused["status"] == "awaiting_confirmation"
        assert not any(j["kind"] == "lora_train" for j in service.events.list_jobs())
        interpret = service.intent_interpreter
        async def answered(job, images):
            proposal = await interpret(job, images)
            proposal["questions"] = []
            return proposal
        service.intent_interpreter = answered
        await service.save_comment(IntentRequest(name="検証用", stage="samples", comment="顔立ちを保つ。この画像の衣装を使う"))
        job = await settled_learning(service, await service.start_learning("検証用", steps=3))
        assert service.events.load_job(job["training_job_id"])["status"] == "completed"
    asyncio.run(scenario())


def test_failed_reading_is_visible_and_never_trains(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path)
        async def fail(*_args):
            raise RuntimeError("解析サービスに接続できません")
        service.intent_interpreter = fail
        job = await service.start_learning("検証用", steps=3)
        with pytest.raises(RuntimeError, match="解析サービス"):
            await service._learning_tasks[job["job_id"]]
        latest = service.events.list_jobs()[0]
        assert latest["status"] == "failed" and "learning_steps" in latest
        assert "解析サービス" in latest["error"]
        assert not (await service.character_info("検証用"))["lora_name"]
    asyncio.run(scenario())


def test_japanese_registration_description_preserves_subject_kind():
    assert subject_tag("銀髪の成人女性。旅人。") == "1girl"
    assert subject_tag("成人男性の旅人") == "1boy"
    assert subject_tag("青いドラゴン") == "1other"


@pytest.mark.parametrize("kind", ["character", "style"])
@pytest.mark.parametrize("changed_comment", ["sample", "overall"])
def test_source_style_is_learned_without_selecting_existing_style(tmp_path, monkeypatch, kind, changed_comment):
    from pathlib import Path
    import tomllib
    from backend.training_dataset import dataset_config
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, kind)
        add = service.add_samples if kind == "character" else service.add_style_samples
        for color in ("red", "green"):
            source = tmp_path / f"{color}.png"; source.write_bytes(png(color))
            await add("検証用", str(source), f"{color}の画像")
        async def interpret(job, _images):
            return {"observations": [{"reference": ref, "appearance_ja": "色の画像", "caption_en": "colored image"} for ref in job["references"]],
                    "questions": [], "training_samples": [
                        {"reference": ref, "priority": p, "features": [f], "reason_ja": reason}
                        for ref, p, f, reason in zip(job["references"], ["reference", "normal", "primary"], ["pose", "outfit", "style"], ["構図の参考だけ", "衣装の参考", "この画風を優先"])],
                    "changes": [{"feature": "style", "scope": "persistent", "panel_key": None, "reference": job["references"][2],
                                 "description_en": "", "avoid_en": "", "avoid_ja": "", "reason_ja": "画像3の画風を優先して学習", "style_name": None, "style_deferred": False}]}
        service.intent_interpreter = interpret
        job = await settled_learning(service, await service.start_learning("検証用", kind, steps=3))
        trained = service.events.load_job(job["training_job_id"])
        assert trained["status"] == "completed" and trained["images"] == 2
        assert {m["reference"]["sample_index"] for m in trained["materials"]} == {1, 2}
        assert len(list(Path(trained["dataset"]).rglob("*.png"))) == 2
        assert [m["training_policy"]["priority"] for m in trained["materials"]] == ["normal", "primary"]
        assert all(Path(m["path"]).read_bytes() == Path(m["reference"]["path"]).read_bytes() for m in trained["materials"])
        subsets = tomllib.loads(dataset_config(trained, "C:/sf/test"))["datasets"][0]["subsets"]
        repeats = {s["image_dir"].split("/")[-1]: s["num_repeats"] for s in subsets}
        assert repeats["primary"] == 2 * repeats["normal"]
        assert "reference" not in repeats
        record = await getattr(service, f"{kind}_info")("検証用")
        assert record.get("style", "") == "" and len(record["samples"]) == 3
        assert "style" not in record["intent_conditions"]
        assert record["training_selection"]["samples"][0]["priority"] == "reference"
        assert not job["accepted"]["changes"][0]["style_deferred"]
        if changed_comment == "sample":
            await (service.set_caption if kind == "character" else service.set_style_caption)("検証用", 1, "希望を更新")
        else:
            await service.save_comment(IntentRequest(name="検証用", kind=kind, stage="samples", comment="画像2の画風も使う"))
        with pytest.raises(ValueError, match="採用方針"):
            await service.prepare_training("検証用", kind)
    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["missing", "duplicate", "all_reference", "wrong_reference"])
def test_invalid_selection_never_starts_or_saves_observations(tmp_path, monkeypatch, case):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await setup(service, tmp_path, wish=True, questions=True)
        job = await settled_learning(service, await service.start_learning("検証用", steps=3))
        value = job["proposal"]
        value["questions"] = []
        if case == "missing": value["training_samples"] = None
        if case == "duplicate": value["training_samples"] *= 2
        if case == "all_reference": value["training_samples"][0]["priority"] = "reference"
        if case == "wrong_reference": value["training_samples"][0]["reference"]["path"] = "unknown.png"
        with pytest.raises(ValueError):
            await service.confirm_learning(job["job_id"], Proposal.model_validate(value))
        assert not service.events.load_job(job["job_id"]).get("accepted_observations")
        assert not any(j["kind"] == "lora_train" for j in service.events.list_jobs())
    asyncio.run(scenario())
