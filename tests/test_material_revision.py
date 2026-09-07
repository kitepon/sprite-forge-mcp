"""NG指摘から元教材を見直す。特定の部位へ分岐しない。"""
import asyncio
import base64
import json
import uuid
from pathlib import Path

import pytest

from backend.intent import Proposal
from backend.intent_cli import run
from backend.material_revision import revision_packet, validate_revision
from backend.preview_reviews import PreviewReview
from tests.test_style import make, png

import importlib.util

_PROBE = Path(__file__).resolve().parents[1] / "evidence/ng-remake-20260907/probe_remake.py"
_spec = importlib.util.spec_from_file_location("probe_remake", _PROBE)
probe_remake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe_remake)


def test_duplicate_ng_comments_attach_one_image():
    pictures = [
        {"id": "a", "path": "a.png", "review": {"rating": "ng", "comment": "同じ"}},
        {"id": "b", "path": "b.png", "review": {"rating": "ng", "comment": "同じ"}},
        {"id": "c", "path": "c.png", "review": {"rating": "ng", "comment": "別"}},
        {"id": "d", "path": "d.png", "review": {"rating": ""}},
    ]
    from backend.material_revision import ng_pictures, representative_ng, revision_packet
    assert [item["id"] for item in ng_pictures(pictures)] == ["a", "b", "c"]
    assert [item["id"] for item in representative_ng(pictures)] == ["a", "c"]
    packet = revision_packet(
        {"key": "k", "char_desc": "", "lora_name": "", "samples": [{"index": 0, "path": "s.png", "caption": ""}]},
        pictures)
    assert [item["attachment_index"] for item in packet["ng_reviews"]] == [1, None, 2]


def test_owner_reviews_exclude_research_comments():
    compiled = {"cases": [
        {"id": "owner-01", "origin": "本人のNG", "number": 1, "comment": "共通の否定理由"},
        {"id": "research-collar", "origin": "研究用の指摘・本人の採否ではない", "number": 17,
         "comment": "襟についている毛皮がNG。髪型は変えないで。"},
        {"id": "owner-17", "origin": "本人のNG", "number": 17, "comment": "この画像だけの否定理由"},
    ], "results": [
        {"id": "owner-01", "meaning": {"observed_ng_ja": "短いボブ", "erase_concept_en": "bob",
                                       "evidence_ja": "対応", "preserve_ja": [], "question_ja": None}},
        {"id": "research-collar", "meaning": {"observed_ng_ja": "毛皮", "erase_concept_en": "fur",
                                              "evidence_ja": "対応", "preserve_ja": ["髪型"], "question_ja": None}},
        {"id": "owner-17", "meaning": {"observed_ng_ja": "長い髪", "erase_concept_en": "long hair",
                                       "evidence_ja": "対応", "preserve_ja": [], "question_ja": None}},
    ]}
    selected = probe_remake.owner_reviews(compiled)
    assert [item["number"] for item in selected] == [1, 17]
    assert selected[1]["comment"] == "この画像だけの否定理由"
    assert selected[0]["meaning"]["fix"] == ["短いボブ"]
    assert all("毛皮" not in json.dumps(item, ensure_ascii=False) for item in selected)



def proposal_for(packet, *, priority="normal", feature="outfit", question=False):
    refs = list(packet["references"])
    return {
        "observations": [{"reference": ref, "appearance_ja": "元画像に見える内容", "caption_en": "visible subject"}
                         for ref in refs],
        "training_samples": [{"reference": ref, "priority": "reference" if i == 0 else priority,
                              "features": [] if i == 0 else [feature],
                              "reason_ja": "元のポーズ参考を残し、NGの対になる状態を他の教材で学ぶ"}
                             for i, ref in enumerate(refs)],
        "changes": [{"feature": feature, "scope": "persistent", "panel_key": None, "reference": refs[-1],
                     "description_en": "desired visible state", "avoid_en": "rejected state",
                     "avoid_ja": "否定された状態", "reason_ja": "NG原文に対応", "style_name": None,
                     "style_deferred": False}],
        "questions": ["1枚目を教材に含めますか？"] if question else [],
    }


def interpret_for(feature="outfit", question=False):
    async def interpret(job, images):
        if job.get("stage") == "preview_review" or "review_input" in job:
            return {"fix": ["否定された状態"], "preserve": ["指摘されていない特徴"], "questions": []}
        assert job["stage"] == "material_revision"
        assert [item["rating"] for item in job["revision_input"]["ng_reviews"]] == ["ng"]
        assert len(images) == 3
        return proposal_for(job["revision_input"], feature=feature, question=question)
    return interpret


async def prepared(service, tmp_path, comment="襟の毛皮がNG。髪型は変えないで"):
    first = tmp_path / "pose.png"
    second = tmp_path / "body.png"
    first.write_bytes(png("red"))
    second.write_bytes(png("blue"))
    await service.create_character("probe", "成人女性", lora_name="person.safetensors")
    await service.add_samples("probe", str(first), "ポーズだけ参照")
    await service.add_samples("probe", str(second), "服装を維持")
    preview = await service.preview_character("probe", count=3)
    await service.save_preview_review("probe", preview["job_id"], preview["pictures"][0]["id"],
                                      PreviewReview(rating="ng", revision=0, comment=comment))
    await service.save_preview_review("probe", preview["job_id"], preview["pictures"][2]["id"],
                                      PreviewReview(rating="ok", revision=0, comment="残してよい"))
    return preview


def test_packet_keeps_unrated_out_and_does_not_reference_generated_images(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    service.intent_interpreter = interpret_for()

    async def scenario():
        preview = await prepared(service, tmp_path)
        job = await service.propose_material_revision("probe", preview["job_id"], str(uuid.uuid4()))
        record = service._load_character("probe")
        packet = revision_packet(record, (await service.preview_reviews("probe", preview["job_id"]))["pictures"])
        assert [item["id"] for item in packet["ng_reviews"]] == [preview["pictures"][0]["id"]]
        assert all(item["path"] != preview["pictures"][0]["path"] for item in packet["references"])
        assert job["status"] == "awaiting_confirmation"
        assert record["lora_name"] == "person.safetensors"
        return job, preview, record

    job, preview, record = asyncio.run(scenario())
    broken = proposal_for(job["packet"])
    broken["training_samples"][0]["reference"] = {
        "record_key": record["key"], "sample_index": 0, "path": preview["pictures"][0]["path"]}
    with pytest.raises(ValueError):
        validate_revision(Proposal.model_validate(broken), job["packet"])


@pytest.mark.parametrize("feature", ["outfit", "composition", "hair"])
def test_same_freeze_path_for_different_rejected_features(tmp_path, monkeypatch, feature):
    service, _ = make(tmp_path, monkeypatch)
    service.intent_interpreter = interpret_for(feature)

    async def scenario():
        preview = await prepared(service, tmp_path)
        request_id = str(uuid.uuid4())
        await service.propose_material_revision("probe", preview["job_id"], request_id)
        trained = await service.remake_lora_from_revision("probe", request_id, steps=3)
        record = service._load_character("probe")
        assert record["lora_name"] == "person.safetensors"
        assert trained["lora_name"] != record["lora_name"]
        dataset = Path(service.events.load_job(trained["training_job_id"])["dataset"])
        assert {path.name for path in dataset.rglob("*.png")} == {"001.png"}
        assert (dataset / "normal" / "001.txt").read_text() == "probe, visible subject"
        assert not (dataset / "reference").exists()
        assert (service.generated_root / f"material-revision-{request_id}" / "report.html").is_file()
        assert record["samples"][0]["caption"] == "ポーズだけ参照"

    asyncio.run(scenario())


def test_questions_do_not_train(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    service.intent_interpreter = interpret_for(question=True)

    async def scenario():
        preview = await prepared(service, tmp_path)
        request_id = str(uuid.uuid4())
        job = await service.propose_material_revision("probe", preview["job_id"], request_id)
        assert job["status"] == "awaiting_answers"
        with pytest.raises(ValueError, match="確認待ち"):
            await service.remake_lora_from_revision("probe", request_id, steps=3)
        assert service._load_character("probe")["lora_name"] == "person.safetensors"

    asyncio.run(scenario())


def test_cli_uses_revision_instructions_without_part_branches():
    from tests.test_intent_cli import FakeComfy
    from backend.intent_cli import prompt_for
    prompt = prompt_for({"input": {"stage": "material_revision", "original_comment": "見直し"}, "images": ["x"]})
    assert "部位ごとの専用手順は作りません" in prompt
    assert "NG画像をreferenceにしたり" in prompt
    run({"input": {"stage": "material_revision", "original_comment": "見直し"},
         "images": [base64.b64encode(b"image-fixture").decode()]},
        FakeComfy(json.dumps({
            "observations": [], "changes": [], "questions": [], "training_samples": []})))
