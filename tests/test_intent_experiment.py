"""比較実験の既存応答を、モデルの再実行なしで引き継ぐ。"""
import asyncio
from copy import deepcopy

from scripts.check_intent import apply_retained
from tests.test_intent import proposal, setup
from tests.test_style import make


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
