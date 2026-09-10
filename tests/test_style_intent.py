"""画風の注文は文章でなく既存LoRAの選択として扱う。"""
import asyncio

import pytest

from backend.intent import IntentRequest, Proposal
from tests.test_drawing_intent import setup
from tests.test_intent import proposal
from tests.test_style import approve_sheet, make, panel_orders


async def pending(service, *, stage="preview", scope="this_run", style_name="probe", deferred=False):
    job = await service.save_comment(IntentRequest(name="probe", stage=stage, comment="画風を選んで、衣装は青いコート"))
    value = proposal(scope=scope, feature="style", text="requested brush texture")
    value["changes"][0].update(style_name=style_name, style_deferred=deferred)
    value["changes"] += proposal(scope="this_run", text="blue coat")["changes"]
    job.update(status="awaiting_confirmation", proposal=value)
    service.events.save_job(job)
    return job, value


@pytest.mark.parametrize("scope", ["persistent", "this_run"])
@pytest.mark.parametrize("stage", ["preview", "drawing", "sheet"])
def test_style_selection_reaches_generation_without_content_words(tmp_path, monkeypatch, scope, stage):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        job, value = await pending(service, stage=stage, scope=scope)
        assert [s["name"] for s in job["available_styles"]] == ["probe"]
        accepted = await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        record = service._load_character("probe")
        assert record.get("style", "") == ("probe" if scope == "persistent" else "")
        assert "style" not in record["intent_conditions"]
        assert "style" not in accepted["effective_conditions"]
        call = {"preview": service.preview_character, "drawing": service.generate_from_bible,
                "sheet": service.generate_character_bible}[stage]
        if stage == "sheet":
            approve_sheet(service, "probe")
        generated = await call("probe", **({"prompt": ""} if stage == "drawing" else {}), intent_job_id=job["job_id"])
        if stage == "sheet":
            panels = panel_orders(comfy)
            assert len(panels) == generated["total_panels"]
            assert generated["loras"] == [("person.safetensors", 0.8), ("look.safetensors", 0.7)]
            assert all(graph["4"]["inputs"]["lora_name"] == "person.safetensors" for graph in panels)
            assert all(graph["40"]["inputs"]["lora_name"] == "look.safetensors" for graph in panels)
            assert all("requested brush texture" not in graph["20"]["inputs"]["text"] for graph in panels)
            assert all("probe_style" not in graph["20"]["inputs"]["text"] for graph in panels)
            assert [graph["20"]["inputs"]["text"] for graph in panels] == [
                request["prompt"] for request in generated["panel_requests"]
            ]
        else:
            assert generated["loras"] == [("person.safetensors", 0.8), ("look.safetensors", 0.7)]
            for graph in comfy.submitted:
                assert graph["40"]["inputs"]["lora_name"] == "look.safetensors"
                assert "requested brush texture" not in graph["20"]["inputs"]["text"]
                assert "probe_style" in graph["20"]["inputs"]["text"]
        assert service._load_character("probe").get("panel_overrides", {}) == {}

    asyncio.run(scenario())


@pytest.mark.parametrize("scope", ["persistent", "this_run"])
def test_explicit_no_style_does_not_fall_back_to_character_setting(tmp_path, monkeypatch, scope):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        await service.set_character_style("probe", "probe", 0.6)
        job, value = await pending(service, scope=scope, style_name="")
        await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        generated = await service.preview_character("probe", intent_job_id=job["job_id"])
        assert generated["loras"] == [("person.safetensors", 0.8)]
        assert "40" not in comfy.submitted[-1]
        assert service._load_character("probe").get("style", "") == ("" if scope == "persistent" else "probe")
        assert service._load_character("probe")["style_strength"] == 0.6

    asyncio.run(scenario())


def test_unresolved_style_requires_explicit_deferral_and_preserves_request(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        job, value = await pending(service, style_name=None)
        before = service._load_character("probe")
        with pytest.raises(ValueError, match="画風"):
            await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        assert service._load_character("probe") == before
        value["changes"][0]["style_deferred"] = True
        accepted = await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        assert accepted["accepted"]["changes"][0]["style_deferred"]
        assert accepted["proposal"]["changes"][0]["description_en"] == "requested brush texture"
        generated = await service.preview_character("probe", intent_job_id=job["job_id"])
        assert generated["loras"] == [("person.safetensors", 0.8)]
        assert "blue coat" in generated["prompt"] and "brush" not in generated["prompt"]

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", ["unknown", "untrained", "panel", "stale"])
def test_invalid_style_selection_does_not_write_record(tmp_path, monkeypatch, bad):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        job, value = await pending(service, stage="sheet", scope="persistent")
        if bad == "unknown":
            value["changes"][0]["style_name"] = "missing"
        elif bad == "untrained":
            style = service._load_style("probe")
            style["lora_name"] = ""
            service._save_style(style)
        elif bad == "panel":
            value["changes"][0].update(scope="panel", panel_key="turn_front")
        else:
            await service.set_character_style("probe", "probe")
        before = service._load_character("probe")
        with pytest.raises(ValueError):
            await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        assert service._load_character("probe") == before

    asyncio.run(scenario())


def test_manual_style_conflict_stops_before_gpu(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        job, value = await pending(service, style_name="")
        await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        with pytest.raises(ValueError, match="手動選択"):
            await service.preview_character("probe", style="probe", intent_job_id=job["job_id"])
        assert not comfy.submitted

    asyncio.run(scenario())


@pytest.mark.parametrize("saved_style", ["", "probe"])
def test_redraw_ignores_character_style_changes(tmp_path, monkeypatch, saved_style):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        await service.set_character_style("probe", saved_style, 0.6)
        approve_sheet(service, "probe")
        original = await service.generate_character_bible("probe")
        record = service._load_character("probe")
        assert "loras" not in record["bible"] and "trigger" not in record["bible"] and "style" not in record["bible"]
        await service.set_character_style("probe", "" if saved_style else "probe", 1.2)
        changed_style = service._load_style("probe")
        changed_style.update(lora_name="new-look.safetensors", trigger="new_style")
        service._save_style(changed_style)
        redraw = await service.redraw_panel("probe", "turn_front")
        assert redraw["prompt"].startswith(original["trigger"])
        assert "new_style" not in redraw["prompt"]
        assert comfy.submitted[-1]["4"]["inputs"]["lora_name"] == "person.safetensors"
        if saved_style:
            assert "40" not in comfy.submitted[-1]
        else:
            assert comfy.submitted[-1]["40"]["inputs"]["lora_name"] == "new-look.safetensors"
        assert "probe_style" not in redraw["prompt"]
        assert comfy.submitted[-1]["20"]["inputs"]["text"] == redraw["prompt"]
        job = await service.save_comment(IntentRequest(name="probe", stage="panel", panel="turn_front", comment="別の画風で"))
        value = proposal(scope="this_run", feature="style", text="")
        value["changes"][0]["style_name"] = "" if saved_style else "probe"
        job.update(status="awaiting_confirmation", proposal=value)
        service.events.save_job(job)
        count = len(comfy.submitted)
        with pytest.raises(ValueError, match="部分描き直し"):
            await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        assert len(comfy.submitted) == count
        value["changes"][0].update(style_name=None, style_deferred=True)
        job.update(status="awaiting_confirmation", proposal=value)
        service.events.save_job(job)
        accepted = await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        assert "style" not in accepted["effective_conditions"]
        commented = await service.redraw_panel("probe", "turn_front", intent_job_id=job["job_id"])
        assert len(comfy.submitted) == count + 1
        assert comfy.submitted[-1]["4"]["inputs"]["lora_name"] == "person.safetensors"
        if saved_style:
            assert "40" not in comfy.submitted[-1]
        else:
            assert comfy.submitted[-1]["40"]["inputs"]["lora_name"] == "new-look.safetensors"
        assert "probe_style" not in commented["prompt"]
        assert comfy.submitted[-1]["20"]["inputs"]["text"] == commented["prompt"]

    asyncio.run(scenario())


def test_legacy_sheet_without_reference_does_not_guess_source(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        approve_sheet(service, "probe")
        await service.generate_character_bible("probe")
        record = service._load_character("probe")
        record["bible"].pop("reference_dir")
        record["bible"]["job_id"] = "missing"
        service._save_character(record)
        count = len(comfy.submitted)
        with pytest.raises(ValueError, match="合格シートから切り出した参照"):
            await service.redraw_panel("probe", "turn_front")
        assert len(comfy.submitted) == count

    asyncio.run(scenario())


def test_style_course_can_defer_wish_but_cannot_replace_its_own_lora(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        job = await service.save_comment(IntentRequest(name="probe", kind="style", stage="drawing", comment="違う質感で森を描いて"))
        value = proposal(scope="this_run", feature="style", text="")
        value["changes"][0]["style_name"] = "probe"
        value["changes"] += proposal(scope="this_run", feature="subject", text="a forest")["changes"]
        job.update(status="awaiting_confirmation", proposal=value)
        service.events.save_job(job)
        with pytest.raises(ValueError, match="素材と学習"):
            await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        value["changes"][0].update(style_name=None, style_deferred=True)
        await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))
        generated = await service.generate_image("", "probe", intent_job_id=job["job_id"])
        assert generated["loras"] == [("look.safetensors", 0.8)]
        assert generated["prompt"] == "probe_style, a forest"

    asyncio.run(scenario())
