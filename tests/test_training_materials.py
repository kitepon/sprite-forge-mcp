"""学習の説明と注文を分け、確認した教材の写しを実行する。"""
import asyncio
from pathlib import Path

import pytest

from backend.intent import IntentRequest, Proposal
from tests.test_style import make, png


async def accept_observations(service, name, kind="character", captions=None):
    record = await getattr(service, f"{kind}_info")(name)
    job = await service.save_comment(IntentRequest(name=name, kind=kind, stage="training", comment="画像の観察を確認"))
    proposal = {"observations": [{"reference": ref, "appearance_ja": "画像に見える内容",
                                 "caption_en": captions[i] if captions else sample.get("caption") or "a subject"}
                                for i, (ref, sample) in enumerate(zip(job["references"], record["samples"]))],
                "changes": [], "questions": []}
    job.update(status="awaiting_confirmation", proposal=proposal)
    service.events.save_job(job)
    return await service.confirm_training_observations(job["job_id"], Proposal.model_validate(proposal).observations)


@pytest.mark.parametrize("kind", ["character", "style"])
def test_reviewed_observation_is_separate_and_prepared_copy_is_frozen(tmp_path, monkeypatch, kind):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        source = tmp_path / "red.png"
        source.write_bytes(png("red"))
        await getattr(service, f"create_{kind}")("probe", "説明")
        add = service.add_samples if kind == "character" else service.add_style_samples
        await add("probe", str(source), "青い服にしてほしい")
        with pytest.raises(ValueError, match="教材の説明"):
            await service.prepare_training("probe", kind, steps=3)
        accepted = await accept_observations(service, "probe", kind, ["red coat"])
        record = await getattr(service, f"{kind}_info")("probe")
        assert record["samples"][0]["caption"] == "青い服にしてほしい"
        assert record["samples"][0]["training_caption"]["caption_en"] == "red coat"
        prepared = await service.prepare_training("probe", kind, steps=3)
        assert prepared["status"] == "awaiting_confirmation"
        assert prepared["materials"][0]["intent_job_id"] == accepted["job_id"]
        frozen = Path(prepared["materials"][0]["path"])
        actual = frozen.read_bytes()
        await getattr(service, f"remove_{'sample' if kind == 'character' else 'style_sample'}")("probe", 0)
        await add("probe", str(source), "あとから追加した希望")
        train = getattr(service, f"train_{kind}_lora")
        result = await train("probe", prepared_job_id=prepared["job_id"])
        assert result["job_id"] == prepared["job_id"] and result["steps"] == 3
        assert frozen.read_bytes() == actual
        assert frozen.with_suffix(".txt").read_text() == f"{record['trigger']}, red coat"
        assert "青い" not in frozen.with_suffix(".txt").read_text()
        with pytest.raises(ValueError, match="確認待ち"):
            await train("probe", prepared_job_id=prepared["job_id"])
        assert (await getattr(service, f"{kind}_info")("probe"))["samples"][0]["caption"] == "あとから追加した希望"

    asyncio.run(scenario())


def test_prepared_training_cannot_target_recreated_record(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        source = tmp_path / "red.png"; source.write_bytes(png())
        await service.create_character("probe", "she/her")
        await service.add_samples("probe", str(source))
        await accept_observations(service, "probe")
        prepared = await service.prepare_training("probe", steps=3)
        await service.create_character("probe", "new")
        with pytest.raises(ValueError, match="対象"):
            await service.train_character_lora("probe", prepared_job_id=prepared["job_id"])

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["missing", "duplicate", "blank", "conflict"])
def test_observation_confirmation_does_not_partially_save(tmp_path, monkeypatch, failure):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        source = tmp_path / "red.png"; source.write_bytes(png())
        await service.create_character("probe", "she/her")
        await service.add_samples("probe", f"{source},{source}", "赤を青に|背景を変えて")
        job = await service.save_comment(IntentRequest(name="probe", stage="training", comment="希望"))
        proposal = {"observations": [{"reference": ref, "appearance_ja": "赤い服", "caption_en": "red coat"} for ref in job["references"]], "changes": [], "questions": ["どの背景？"]}
        job.update(status="awaiting_confirmation", proposal=proposal)
        service.events.save_job(job)
        items = Proposal.model_validate(proposal).observations
        if failure == "missing": items.pop()
        if failure == "duplicate": items[1] = items[0]
        if failure == "blank": items[1].caption_en = " "
        if failure == "conflict": await accept_observations(service, "probe", captions=["new one", "new two"])
        before = await service.character_info("probe")
        with pytest.raises(ValueError):
            await service.confirm_training_observations(job["job_id"], items)
        assert await service.character_info("probe") == before
        assert not service.events.load_job(job["job_id"]).get("accepted_observations")

    asyncio.run(scenario())


@pytest.mark.parametrize("first", ["wish", "observation"])
def test_observations_and_wishes_are_independent(tmp_path, monkeypatch, first):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        source = tmp_path / "red.png"; source.write_bytes(png())
        await service.create_character("probe", "she/her")
        await service.add_samples("probe", str(source), "青くして")
        job = await service.save_comment(IntentRequest(name="probe", stage="training", comment="今後は青い服"))
        from tests.test_intent import proposal
        proposed = proposal(job["references"][0], text="blue coat")
        proposed["observations"] = [{"reference": job["references"][0], "appearance_ja": "赤い服", "caption_en": "red coat"}]
        job.update(status="awaiting_confirmation", proposal=proposed)
        service.events.save_job(job)
        parsed = Proposal.model_validate(proposed)
        if first == "wish":
            await service.confirm_comment_intent(job["job_id"], parsed)
            await service.confirm_training_observations(job["job_id"], parsed.observations)
        else:
            await service.confirm_training_observations(job["job_id"], parsed.observations)
            assert "intent_conditions" not in await service.character_info("probe")
            assert service.events.load_job(job["job_id"])["status"] == "awaiting_confirmation"
            await service.confirm_comment_intent(job["job_id"], parsed)
        first_materials = await service.prepare_training("probe", steps=3)
        second_materials = await service.prepare_training("probe", steps=4)
        assert first_materials["dataset"] != second_materials["dataset"]
        assert Path(first_materials["materials"][0]["path"]).exists()
        assert first_materials["materials"][0]["caption"] == "probe, red coat"
        assert (await service.character_info("probe"))["intent_conditions"]["outfit"]["description_en"] == "blue coat"

    asyncio.run(scenario())


def test_preparation_and_observation_rest_routes_share_service(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app

    service, _ = make(tmp_path, monkeypatch)
    for key in ("characters_root", "styles_root", "generated_root", "events"):
        monkeypatch.setattr(app.services, key, getattr(service, key))
    source = tmp_path / "red.png"; source.write_bytes(png())
    asyncio.run(service.create_character("probe", "she/her"))
    asyncio.run(service.add_samples("probe", str(source), "青くして"))
    job = asyncio.run(service.save_comment(IntentRequest(name="probe", stage="training", comment="観察")))
    observations = [{"reference": job["references"][0], "appearance_ja": "赤い服", "caption_en": "red coat"}]
    job.update(status="awaiting_confirmation", proposal={"observations": observations, "changes": [], "questions": []})
    service.events.save_job(job)
    with TestClient(app.app) as client:
        response = client.post(f"/api/intents/{job['job_id']}/observations", json=observations)
        assert response.status_code == 200 and response.json()["accepted_observations"] == observations
        prepared = client.post("/api/training/prepare", params={"name": "probe", "kind": "character", "steps": 3})
        assert prepared.status_code == 200
        assert prepared.json()["status"] == "awaiting_confirmation"
        assert Path(prepared.json()["materials"][0]["path"]).exists()
