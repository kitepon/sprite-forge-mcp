"""設定画の全体条件と、個別パネルの注文を分けて検証する。"""
from copy import deepcopy
import asyncio
from pathlib import Path

import pytest

from backend import bible
from backend.intent import Proposal, validate_proposal
from backend.intent import IntentRequest
from tests.test_intent import proposal
from tests.test_style import make, png


def change(feature, text, scope="this_run", panel=None):
    value = proposal(feature=feature, text=text, scope=scope)["changes"][0]
    value["panel_key"] = panel
    return value


def test_sheet_accepts_global_and_targeted_changes_without_collapsing_them():
    job = {"stage": "sheet", "panel": "", "record_kind": "character", "references": [],
           "panel_specs": [{"key": p.key} for p in bible.PANELS]}
    value = Proposal.model_validate({"observations": [], "questions": [], "changes": [
        change("outfit", "a coat and boots"), change("outfit", "red boots", panel="item_shoes"),
        change("accessory", "silver crown", "panel", "item_head")]})
    validate_proposal(value, job)
    for scope, key in [("persistent", "turn_front"), ("panel", None), ("this_run", "missing")]:
        bad = value.model_copy(deep=True)
        bad.changes[0].scope, bad.changes[0].panel_key = scope, key
        with pytest.raises(ValueError, match="パネル"):
            validate_proposal(bad, job)


def test_panel_resolution_keeps_roles_and_separates_shoes():
    from backend.panel_intent import resolve_panel
    panels = {p.key: p for p in bible.PANELS}
    common = {"hair": change("hair", "short hair", "persistent"),
              "outfit": change("outfit", "a coat and black boots", "persistent"),
              "pose": change("pose", "front view", "persistent")}
    changes = [change("outfit", "a yellow coat and red boots"), change("outfit", "red boots", panel="item_shoes")]
    before = deepcopy((common, changes))
    side = resolve_panel(panels["turn_side"], "fixture", "she/her", common, changes, {})
    assert "from side" in side["prompt"] and "front view" not in side["prompt"]
    assert "a yellow coat and red boots" in side["prompt"] and "short hair" in side["prompt"]
    shoes = resolve_panel(panels["item_shoes"], "fixture", "she/her", common, changes, {})
    assert "red boots" in shoes["prompt"]
    assert all(word not in shoes["prompt"] for word in ("coat", "short hair", "front view", "1girl"))
    assert "no humans" in shoes["prompt"]
    armor = resolve_panel(panels["cos_armor"], "fixture", "she/her", common, [], {})
    assert "plate armor" in armor["prompt"] and "a coat" not in armor["prompt"]
    outfit = resolve_panel(panels["item_outfit"], "fixture", "she/her", common, [], {})
    assert "a coat and black boots" in outfit["prompt"] and "no humans" in outfit["prompt"]
    assert (common, changes) == before


def test_targeted_temporary_condition_overrides_saved_but_does_not_mutate_it():
    from backend.panel_intent import resolve_panel
    panel = bible.PANELS[0]
    saved = {"conditions": {"outfit": change("outfit", "blue coat", "panel", panel.key)}}
    changes = [change("outfit", "green coat", "panel", panel.key), change("outfit", "red coat", panel=panel.key)]
    result = resolve_panel(panel, "fixture", "she/her", {}, changes, saved)
    assert "red coat" in result["prompt"] and "green coat" not in result["prompt"]
    assert saved["conditions"]["outfit"]["description_en"] == "blue coat"
    global_result = resolve_panel(panel, "fixture", "she/her", {}, [change("outfit", "red uniform")], saved)
    assert "red uniform" in global_result["prompt"] and "blue coat" not in global_result["prompt"]


def test_human_custom_role_order_keeps_face_hair_views_armor_and_shoes():
    from backend.panel_intent import resolve_panel
    from backend.sheet_layout import legacy_layout, panel_from
    layouts = {p["key"]: p for p in legacy_layout()}
    for key in ("turn_front", "turn_side"):
        layouts[key]["parts"].extend([
            {"feature": "outfit", "description_en": "red cape, blue tunic, brown boots", "avoid_en": "white trousers"},
            {"feature": "face", "description_en": "blue eyes", "avoid_en": ""},
            {"feature": "hair", "description_en": "short brown hair", "avoid_en": ""}])
        layouts[key]["role_features"].extend(["outfit", "face", "hair"])
    common = {"outfit": change("outfit", "red cape, blue tunic, brown boots", "persistent")}
    changes = [change("outfit", "green cape, blue tunic, brown boots", panel=key) for key in ("turn_front", "turn_side")]
    for item in changes:
        item.update(avoid_en="white trousers", avoid_ja="白いズボン")
    saved = {"conditions": {"outfit": change("outfit", "brown boots", "panel", "item_shoes")}}
    front = resolve_panel(panel_from(layouts["turn_front"]), "fixture", "he/him", common, changes, {})
    side = resolve_panel(panel_from(layouts["turn_side"]), "fixture", "he/him", common, changes, {})
    for value in (front, side):
        assert "green cape" in value["prompt"] and "red cape" not in value["prompt"]
        assert "blue eyes" in value["prompt"] and "short brown hair" in value["prompt"]
        assert "white trousers" in value["negative"]
    assert "front view" in front["prompt"] and "from side" in side["prompt"]
    assert "front view" not in side["prompt"]
    armor = resolve_panel(panel_from(layouts["cos_armor"]), "fixture", "he/him", common, changes, {})
    shoes = resolve_panel(panel_from(layouts["item_shoes"]), "fixture", "he/him", common, changes, saved)
    assert "plate armor" in armor["prompt"] and "green cape" not in armor["prompt"]
    assert "brown boots" in shoes["prompt"] and all(text not in shoes["prompt"] for text in ("cape", "tunic", "blue eyes"))


def test_legacy_content_is_unchanged_and_mixing_requires_targeted_confirmation():
    from backend.panel_intent import resolve_panel
    panel = bible.PANELS[0]
    legacy = {"tags": "a person sitting in a room", "avoid": "hat", "seed": 8}
    result = resolve_panel(panel, "fixture", "she/her", {}, [], legacy)
    assert result["prompt"] == bible.panel_prompt(panel, "fixture", "she/her", legacy["tags"])
    assert result["negative"] == bible.NEGATIVE + ", hat"
    unrelated = resolve_panel(panel, "fixture", "she/her", {},
        [change("outfit", "blue boots", panel="item_shoes")], legacy, "confirmed")
    assert unrelated == result
    with pytest.raises(ValueError, match="英語"):
        resolve_panel(panel, "fixture", "she/her", {"hair": change("hair", "short hair")}, [], legacy)
    result = resolve_panel(panel, "fixture", "she/her", {}, [change("pose", "sitting", "panel", panel.key)], legacy)
    assert "sitting" in result["prompt"] and "a person sitting in a room" not in result["prompt"]


def test_static_face_and_common_outfit_leave_expression_and_temporary_scope_separate():
    from backend.panel_intent import resolve_panel, saved_corrections
    panels = {p.key: p for p in bible.PANELS}
    common = {"outfit": change("outfit", "red cape, blue tunic", "persistent")}
    changes = [change("face", "blue eyes, small nose"),
               change("outfit", "red cape, blue tunic", "panel", "turn_front"),
               change("outfit", "green cape, blue tunic", panel="turn_front")]
    before = deepcopy((common, changes))
    for key in ("ex_smile", "ex_surp"):
        result = resolve_panel(panels[key], "fixture", "he/him", common, changes, {})
        assert "open mouth" in result["prompt"] and "closed mouth" not in result["prompt"]
        assert "blue eyes, small nose" in result["prompt"]
        assert result["conditions"]["expression"] == panels[key].conditions["expression"]
    front = resolve_panel(panels["turn_front"], "fixture", "he/him", common, changes, {})
    saved = saved_corrections({}, {}, changes, {"turn_front": 12}, "test")
    assert "green cape" in front["prompt"]
    assert saved["turn_front"]["conditions"]["outfit"]["description_en"] == "red cape, blue tunic"
    next_side = resolve_panel(panels["turn_side"], "fixture", "he/him", common, [], {})
    assert "red cape" in next_side["prompt"] and "green cape" not in next_side["prompt"]
    assert (common, changes) == before


async def setup(service, tmp_path):
    source = tmp_path / "reference.png"
    source.write_bytes(png())
    await service.create_character("probe", "she/her", lora_name="person.safetensors")
    record = await service.add_samples("probe", str(source))
    root = tmp_path / "panels"
    root.mkdir()
    for panel in bible.PANELS:
        (root / f"{panel.key}.png").write_bytes(png())
    record["bible"] = {"job_id": "initial", "panels_dir": str(root),
                       "sheet_path": str(tmp_path / "sheet.png"), "html_path": str(tmp_path / "sheet.html")}
    service._save_character(record)


async def accept(service, changes, stage="sheet", panel=""):
    job = await service.save_comment(IntentRequest(name="probe", stage=stage, panel=panel, comment="今回の注文"))
    value = {"observations": [], "questions": [], "changes": changes}
    job.update(status="awaiting_confirmation", proposal=value)
    service.events.save_job(job)
    return await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(value))


def test_sheet_preserves_scope_records_actual_inputs_and_reuses_panel_correction(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        intent = await accept(service, [change("outfit", "white coat", "persistent"),
                                        change("outfit", "yellow coat"),
                                        change("outfit", "red boots", "panel", "item_shoes")])
        assert len(intent["accepted"]["changes"]) == 3
        assert "panel_overrides" not in await service.character_info("probe")
        result = await service.generate_character_bible("probe", seed=10, intent_job_id=intent["job_id"])
        assert len(result["panel_requests"]) == len(comfy.submitted) == 23
        for request, graph in zip(result["panel_requests"], comfy.submitted):
            assert graph["20"]["inputs"]["text"] == request["prompt"]
            assert graph["21"]["inputs"]["text"] == request["negative"]
            assert graph["23"]["inputs"]["seed"] == request["seed"]
        assert "yellow coat" in result["panel_requests"][0]["prompt"]
        assert "red boots" in result["panel_requests"][-1]["prompt"]
        assert "coat" not in result["panel_requests"][-1]["prompt"]
        record = await service.character_info("probe")
        assert record["intent_conditions"]["outfit"]["description_en"] == "white coat"
        assert set(record["panel_overrides"]) == {"item_shoes"}
        assert record["panel_overrides"]["item_shoes"]["seed"] == 32
        next_job = await service.generate_character_bible("probe", seed=99)
        assert "white coat" in next_job["panel_requests"][0]["prompt"]
        assert "yellow coat" not in next_job["panel_requests"][0]["prompt"]
        assert "red boots" in next_job["panel_requests"][-1]["prompt"]
        assert next_job["panel_requests"][-1]["seed"] == 32
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["intent", "english"])
def test_explicit_redraw_mode_preserves_legacy_or_replaces_structured(tmp_path, monkeypatch, mode):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        record = await service.character_info("probe")
        saved = {"tags": "waving", "avoid": "hat", "seed": 7} if mode == "intent" else {
            "conditions": {"outfit": change("outfit", "blue coat", "panel", "turn_front")}, "seed": 7}
        record["panel_overrides"] = {"turn_front": saved}
        if mode == "english":
            record["intent_conditions"] = {"hair": change("hair", "short hair", "persistent")}
        service._save_character(record)
        result = await service.redraw_panel("probe", "turn_front", tags="green coat" if mode == "english" else "",
                                            input_mode=mode)
        current = (await service.character_info("probe"))["panel_overrides"]["turn_front"]
        if mode == "intent":
            assert "waving" in result["prompt"] and result["negative"].endswith(", hat")
            assert current == saved
        else:
            assert "green coat" in result["prompt"] and "blue coat" not in result["prompt"]
            assert "short hair" not in result["prompt"]
            assert result["intent_positive"] == result["intent_negative"] == ""
            assert result["intent_conditions"] == {} and result["intent_changes"] == []
            assert current == {"tags": "green coat", "avoid": "", "seed": 1}
            reset = await service.redraw_panel("probe", "turn_front", input_mode="english")
            assert reset["prompt"] == bible.panel_prompt(bible.PANELS[0], record["trigger"], record["char_desc"])
    asyncio.run(scenario())


def test_redraw_conflict_does_not_replace_newer_images(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        intent = await accept(service, [change("outfit", "green coat", "panel", "turn_front")], "panel", "turn_front")
        record = await service.character_info("probe")
        paths = [Path(record["bible"]["panels_dir"]) / "turn_front.png",
                 Path(record["bible"]["sheet_path"]), Path(record["bible"]["html_path"])]
        newer = [png("red"), png("red"), b"<html>newer</html>"]

        async def complete_newer(*args):
            fresh = await service.character_info("probe")
            fresh["panel_overrides"] = {"turn_front": {"tags": "newer edit", "seed": 2}}
            service._save_character(fresh)
            for path, content in zip(paths, newer):
                path.write_bytes(content)
            return png("blue"), 0.1

        service._run_edit = complete_newer
        with pytest.raises(ValueError, match="更新"):
            await service.redraw_panel("probe", "turn_front", intent_job_id=intent["job_id"])
        assert [path.read_bytes() for path in paths] == newer
        assert not (paths[0].parent / "history").exists()
    asyncio.run(scenario())


def test_redraw_temporary_changes_do_not_replace_saved_panel_condition(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        intent = await accept(service, [change("outfit", "blue coat", "panel", "turn_front")], "panel", "turn_front")
        first = await service.redraw_panel("probe", "turn_front", seed=8, intent_job_id=intent["job_id"])
        before = (await service.character_info("probe"))["panel_overrides"]
        temp = await accept(service, [change("outfit", "red coat", panel="turn_front")], "panel", "turn_front")
        result = await service.redraw_panel("probe", "turn_front", intent_job_id=temp["job_id"])
        assert "red coat" in result["prompt"] and "blue coat" not in result["prompt"]
        assert (await service.character_info("probe"))["panel_overrides"] == before
        assert result["previous"] and Path(result["previous"]).is_file()
        assert first["intent_job_id"] == intent["job_id"]
        with pytest.raises(ValueError, match="英語"):
            await service.redraw_panel("probe", "turn_front", "green coat", intent_job_id=temp["job_id"])
        assert len(comfy.submitted) == 2
    asyncio.run(scenario())


def test_current_panel_is_the_target_of_unqualified_temporary_order(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        intent = await accept(service, [change("outfit", "purple boots")], "panel", "item_shoes")
        result = await service.redraw_panel("probe", "item_shoes", intent_job_id=intent["job_id"])
        assert "purple boots" in result["prompt"]
        assert "panel_overrides" not in await service.character_info("probe")
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["sheet", "panel"])
@pytest.mark.parametrize("failure", ["html", "same_panel", "other_panel"])
def test_panel_saving_is_after_composition_and_preserves_concurrent_updates(tmp_path, monkeypatch, stage, failure):
    service, comfy = make(tmp_path, monkeypatch)
    original = comfy.submit

    async def submit(graph, client_id):
        if not comfy.submitted and failure != "html":
            record = await service.character_info("probe")
            record["panel_overrides"] = {"turn_front" if failure == "same_panel" else "turn_back":
                                          {"tags": "newer edit", "avoid": "", "seed": 17}}
            service._save_character(record)
        return await original(graph, client_id)

    def fail(*args, **kwargs):
        raise RuntimeError("HTML合成の試験エラー")

    async def scenario():
        await setup(service, tmp_path)
        intent = await accept(service, [change("outfit", "green coat", "panel", "turn_front")],
                              stage, "turn_front" if stage == "panel" else "")
        comfy.submit = submit
        if failure == "html":
            monkeypatch.setattr(bible, "write_html", fail)
        call = (service.generate_character_bible("probe", intent_job_id=intent["job_id"]) if stage == "sheet"
                else service.redraw_panel("probe", "turn_front", intent_job_id=intent["job_id"]))
        if failure == "other_panel":
            result = await call
            assert result["status"] == "completed"
        else:
            with pytest.raises((ValueError, RuntimeError), match="更新|HTML"):
                await call
            failed = next(j for j in service.events.list_jobs() if j["status"] == "failed")
            assert failed["error"]
        record = await service.character_info("probe")
        if failure == "html":
            assert "panel_overrides" not in record
        elif failure == "same_panel":
            assert record["panel_overrides"]["turn_front"]["tags"] == "newer edit"
        else:
            assert record["panel_overrides"]["turn_back"]["tags"] == "newer edit"
            assert record["panel_overrides"]["turn_front"]["conditions"]["outfit"]["description_en"] == "green coat"
    asyncio.run(scenario())


def test_legacy_seed_survives_confirmed_replacement_and_seed_only_is_not_free_text(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        record = await service.character_info("probe")
        record["panel_overrides"] = {"turn_front": {"tags": "old pose", "avoid": "", "seed": 73},
                                      "turn_back": {"tags": "", "avoid": "", "seed": 91}}
        service._save_character(record)
        intent = await accept(service, [change("pose", "sitting", "panel", "turn_front")])
        result = await service.generate_character_bible("probe", seed=2, intent_job_id=intent["job_id"])
        assert result["panel_requests"][0]["seed"] == 73
        current = await service.character_info("probe")
        assert current["panel_overrides"]["turn_front"]["seed"] == 73
        assert current["panel_overrides"]["turn_back"]["seed"] == 91
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["sheet", "panel"])
@pytest.mark.parametrize("invalid", ["unconfirmed", "stage", "recreated", "other_panel"])
def test_wrong_intent_never_starts_panel_generation(tmp_path, monkeypatch, stage, invalid):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        intent = await accept(service, [], stage, "turn_front" if stage == "panel" else "")
        if invalid == "unconfirmed":
            intent["status"] = "awaiting_confirmation"
        elif invalid == "stage":
            intent["stage"] = "drawing"
        elif invalid == "other_panel":
            intent["panel"] = "turn_back"
        else:
            intent["record_created"] = "another-record"
        service.events.save_job(intent)
        with pytest.raises(ValueError, match="工程"):
            if stage == "sheet":
                await service.generate_character_bible("probe", intent_job_id=intent["job_id"])
            else:
                await service.redraw_panel("probe", "turn_front", intent_job_id=intent["job_id"])
        assert not comfy.submitted
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["sheet", "panel"])
@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_public_entry_resolves_the_confirmed_panel_order(tmp_path, monkeypatch, stage, transport):
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from backend import app

    service, comfy = make(tmp_path, monkeypatch)
    for key in ("characters_root", "styles_root", "generated_root", "events", "comfy", "_view"):
        monkeypatch.setattr(app.services, key, getattr(service, key))
    asyncio.run(setup(app.services, tmp_path))
    intent = asyncio.run(accept(app.services, [change("outfit", "green boots", panel="item_shoes")],
                                stage, "item_shoes" if stage == "panel" else ""))
    args = {"name": "probe", "intent_job_id": intent["job_id"], "seed": 7}
    if stage == "panel":
        args["panel"] = "item_shoes"
    if transport == "rest":
        with TestClient(app.app) as client:
            response = client.post("/api/bible" if stage == "sheet" else "/api/panel", params=args)
            assert response.status_code == 200
            result = response.json()
    else:
        async def call():
            async with Client(app.mcp) as client:
                result = await client.call_tool("generate_character_bible" if stage == "sheet" else "redraw_panel", args)
                return result.structured_content
        result = asyncio.run(call())
    assert result["intent_job_id"] == intent["job_id"]
    assert "green boots" in comfy.submitted[-1]["20"]["inputs"]["text"]
