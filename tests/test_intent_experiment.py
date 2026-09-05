"""比較実験の既存応答を、モデルの再実行なしで引き継ぐ。"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from scripts.check_intent import apply_retained
from tests.test_intent import proposal, setup
from tests.test_style import make


@pytest.mark.parametrize("description", ["he/him", "an orc", "a quadrupedal dragon", "a limbless slime creature"])
def test_probe_passes_the_given_character_description(tmp_path, monkeypatch, description):
    from backend import services
    from scripts.check_intent import main
    from tests.test_style import png

    service, _ = make(tmp_path, monkeypatch)
    monkeypatch.setattr(services, "Services", lambda: service)
    monkeypatch.setenv("SPRITEFORGE_CACHE", "")
    source = tmp_path / "source.png"
    source.write_bytes(png())

    async def interpret(job, images):
        assert job["record_description"] == description
        assert len(images) == 1
        return proposal(job["references"][0])

    service.intent_interpreter = interpret
    args = SimpleNamespace(cache=tmp_path / "probe", reference=[source], description=description,
                           base_interpretation=None, layout_from=None, stage="sheet", panel="", comment="参照の姿を今後も使う")
    asyncio.run(main(args))
    job = json.loads((args.cache / "interpretation.json").read_text())
    assert job["record_description"] == description and job["status"] == "awaiting_confirmation"


@pytest.mark.parametrize("stage", ["sheet", "layout"])
def test_probe_uses_confirmed_layout_without_transferring_old_image_references(tmp_path, monkeypatch, stage):
    from backend import services
    from backend.sheet_layout import legacy_layout
    from scripts.check_intent import main
    from tests.test_layout_intent import proposal as layout_proposal
    from tests.test_style import png

    service, _ = make(tmp_path, monkeypatch)
    monkeypatch.setattr(services, "Services", lambda: service)
    monkeypatch.setenv("SPRITEFORGE_CACHE", "")
    source = tmp_path / "source.png"
    source.write_bytes(png())
    layout = legacy_layout()[:2]
    value = layout_proposal(layout)
    value["panels"][0]["reference"] = {"record_key": "old", "sample_index": 7, "path": "/old.png"}
    retained = tmp_path / "layout.json"
    retained.write_text(json.dumps({"proposal": value}))

    async def interpret(job, images):
        assert job["sheet_layout"] == layout
        assert len(images) == 1 and job["references"][0]["path"] != "/old.png"
        return layout_proposal(layout) if stage == "layout" else proposal(job["references"][0])
    service.intent_interpreter = interpret
    args = SimpleNamespace(cache=tmp_path / "probe", reference=[source], description="a creature", base_interpretation=None,
                           layout_from=retained, stage=stage, panel="", comment="参照の姿")
    asyncio.run(main(args))
    assert json.loads((args.cache / "interpretation.json").read_text())["sheet_layout"] == layout


def test_retained_response_rebinds_only_isolated_references(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    interpreter = service.intent_interpreter
    old_ref = {"record_key": "source", "sample_index": 7, "path": "/source/image.png"}
    native = {"references": [old_ref], "original_comment": "この衣装を今後も",
              "interpreter": {"model": "fixture"}, "proposal": proposal(old_ref)}
    original = deepcopy(native)

    async def scenario():
        rec = await setup(service, tmp_path)
        job = await apply_retained(service, "probe", native)
        return rec, job

    rec, job = asyncio.run(scenario())
    actual = job["effective_conditions"]["outfit"]["reference"]
    assert actual == {"record_key": rec["key"], "sample_index": 0, "path": rec["samples"][0]["path"]}
    assert native == original
    assert service.intent_interpreter is interpreter
    assert job["status"] == "confirmed"


def test_retained_this_run_keeps_common_outfit_for_next_preview(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    ref = {"record_key": "source", "sample_index": 0, "path": "/source/image.png"}
    native = {"references": [ref], "original_comment": "今後もこの衣装",
              "interpreter": {"model": "fixture"}, "proposal": proposal(ref)}

    async def scenario():
        await setup(service, tmp_path)
        await apply_retained(service, "probe", native)
        native["original_comment"] = "今回だけ青いトップス"
        native["proposal"] = proposal(ref, scope="this_run", text="blue top and white skirt")
        current = await apply_retained(service, "probe", native)
        record = service._load_character("probe")
        return current, service._generation_intent(record, "character", "preview")

    current, following = asyncio.run(scenario())
    assert current["effective_conditions"]["outfit"]["description_en"] == "blue top and white skirt"
    assert following["intent_conditions"]["outfit"]["description_en"] == "separate jacket and skirt"


def test_sheet_comparison_prepares_exact_layout_and_confirms_targeted_response(tmp_path, monkeypatch):
    from backend.sheet_layout import legacy_layout
    from scripts.compare_sheet_intent import prepare
    from tests.test_style import png

    service, _ = make(tmp_path, monkeypatch)
    source = tmp_path / "reference.png"
    source.write_bytes(png())
    ref = {"record_key": "old", "sample_index": 4, "path": str(source)}
    value = proposal(ref, scope="this_run", text="blue coat")
    value["changes"][0]["panel_key"] = "turn_side"
    native = {"record_description": "she/her", "references": [ref], "sheet_layout": legacy_layout()[2:3],
              "original_comment": "今回だけ青い上着", "interpreter": {"model": "fixture"}, "proposal": value}
    original = {"name": "probe", "char_desc": "元の説明", "trigger": "person", "lora_name": "person.safetensors"}
    before = deepcopy((original, native))

    async def scenario():
        name = await prepare(service, original, native)
        assert await service.get_sheet_layout(name) == native["sheet_layout"]
        rec = await service.character_info(name)
        assert rec["lora_name"] == original["lora_name"] and rec["trigger"] == "person"
        assert rec["char_desc"] == native["record_description"]
        job = await apply_retained(service, name, native, stage="sheet")
        assert job["stage"] == "sheet" and job["status"] == "confirmed"
        assert job["accepted"]["changes"][0]["panel_key"] == "turn_side"
        assert job["accepted"]["changes"][0]["reference"]["sample_index"] == 0
        assert not (await service.character_info(name))["intent_conditions"]

    asyncio.run(scenario())
    assert (original, native) == before


def test_sheet_comparison_recovers_only_composition_without_rewriting_failed_job(tmp_path, monkeypatch):
    from backend import bible
    from backend.sheet_layout import legacy_layout
    from scripts.compare_sheet_intent import recover_baseline
    layout = legacy_layout()[:1]
    job = {"job_id": "failed", "kind": "character_bible", "status": "failed", "name": "probe",
           "layout": layout, "completed_panels": 1, "panels": [str(tmp_path / "panel.png")]}
    original = deepcopy(job)
    service = SimpleNamespace(events=SimpleNamespace(load_job=lambda _: job),
                              _load_character=lambda _: {"samples_sheet": str(tmp_path / "samples.png")})
    calls = []
    def compose(*args):
        calls.append(args)
        return args[4]
    monkeypatch.setattr(bible, "compose_model_sheet", compose)
    result = recover_baseline(service, "failed", {"sheet_layout": layout}, tmp_path)
    assert len(calls) == 1 and calls[0][2][0][1] == tmp_path / "panel.png"
    assert result["status"] == "failed" and result["comparison_recovery"]["operation"] == "compose_only"
    assert job == original
    job["completed_panels"] = 0
    with pytest.raises(ValueError, match="全画像"):
        recover_baseline(service, "failed", {"sheet_layout": layout}, tmp_path)
    assert len(calls) == 1
