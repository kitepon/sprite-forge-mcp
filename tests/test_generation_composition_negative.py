"""確定した構図・被写体・背景を3つの生成入口へ届ける。"""
import asyncio
from copy import deepcopy

import pytest

from backend import bible
from backend.intent import IntentRequest, Proposal
from tests.test_drawing_intent import setup
from tests.test_intent import proposal
from tests.test_style import make


@pytest.mark.parametrize("route", ["preview", "character_drawing", "style_drawing"])
@pytest.mark.parametrize("explicit", [False, True])
def test_generation_keeps_defaults_or_uses_confirmed_composition(tmp_path, monkeypatch, route, explicit):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        kind = "style" if route == "style_drawing" else "character"
        stage = "preview" if route == "preview" else "drawing"
        intent_id = ""
        if explicit:
            job = await service.save_comment(IntentRequest(name="probe", kind=kind, stage=stage, comment="二方向を並べて、灰色の背景で。帽子は除く"))
            assert job["stage_conditions"]["composition"]["avoid_en"] == bible.SINGLE_VIEW_NEGATIVE
            if route == "preview":
                assert job["stage_conditions"]["subject"]["description_en"] == "1girl"
                assert job["stage_conditions"]["background"]["description_en"] == bible.COMMON
            value = proposal(scope="this_run", feature="composition", text="two full-body views, front and back")
            for feature, text in [("subject", "two depictions of the same adult"), ("pose", "standing"),
                                  ("background", "gray background"), ("outfit", "a blue coat")]:
                value["changes"] += proposal(scope="this_run", feature=feature, text=text)["changes"]
            value["changes"][0].update(avoid_en="hat", avoid_ja="帽子")
            job.update(status="awaiting_confirmation", proposal=value)
            service.events.save_job(job)
            accepted = await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
            intent_id = accepted["job_id"]
        before = deepcopy(service._intent_record("probe", kind))
        if route == "preview":
            job = await service.preview_character("probe", intent_job_id=intent_id)
        elif route == "character_drawing":
            job = await service.generate_from_bible("probe", "" if explicit else "one adult standing", intent_job_id=intent_id)
        else:
            job = await service.generate_image("" if explicit else "one adult standing", "probe", intent_job_id=intent_id)
        graph = comfy.submitted[-1]
        assert job["prompt"] == graph["20"]["inputs"]["text"]
        assert job["negative"] == graph["21"]["inputs"]["text"]
        assert service._intent_record("probe", kind) == before
        if explicit:
            assert job["negative"] == bible.QUALITY_NEGATIVE + ", hat"
            assert "two full-body views" in job["prompt"] and "a blue coat" in job["prompt"]
            assert "gray background" in job["prompt"] and "white background" not in job["prompt"]
            assert "1girl" not in job["prompt"]
        else:
            assert job["negative"] == bible.NEGATIVE
            assert job["prompt"] == ("probe, 1girl, full body, standing, front view, looking at viewer, simple background, white background"
                                     if route == "preview" else ("probe_style" if kind == "style" else "probe") + ", one adult standing")
        assert graph["4"]["inputs"]["lora_name"] == ("look.safetensors" if kind == "style" else "person.safetensors")

    asyncio.run(scenario())
