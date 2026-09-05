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
                           base_interpretation=None, stage="sheet", panel="", comment="参照の姿を今後も使う")
    asyncio.run(main(args))
    job = json.loads((args.cache / "interpretation.json").read_text())
    assert job["record_description"] == description and job["status"] == "awaiting_confirmation"


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
