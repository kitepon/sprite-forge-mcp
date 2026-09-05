"""構図の除外は各パネルが所有し、共通の画質条件と分離する。"""
from copy import deepcopy

from backend import bible
from backend.panel_intent import resolve_panel
from backend.sheet_layout import legacy_layout, panel_from


def test_custom_comparison_does_not_receive_an_unrequested_single_view_exclusion():
    design = deepcopy(legacy_layout()[0])
    design["parts"] = [
        {"feature": "subject", "description_en": "same adult man", "avoid_en": ""},
        {"feature": "composition", "description_en": "two full-body views, front and back", "avoid_en": ""}]
    design["role_features"] = ["composition"]
    result = resolve_panel(panel_from(design), "person", "he/him", {}, [], {})
    assert "two full-body views" in result["prompt"]
    assert result["negative"] == "lowres, bad anatomy, bad hands, text, watermark"


def test_all_legacy_panels_keep_their_original_prompt_and_exclusion():
    for original, value in zip(bible.PANELS, legacy_layout(), strict=True):
        result = resolve_panel(panel_from(value), "person", "she/her", {}, [], {})
        assert result["prompt"] == bible.panel_prompt(original, "person", "she/her")
        assert result["negative"] == "lowres, bad anatomy, bad hands, text, watermark, multiple views, reference sheet, collage"


def test_targeted_composition_replaces_its_old_exclusion_and_keeps_other_exclusions():
    design = deepcopy(legacy_layout()[0])
    design["parts"].append({"feature": "accessory", "description_en": "plain headband", "avoid_en": "hat"})
    change = {"feature": "composition", "description_en": "two full-body views", "avoid_en": "cropped feet",
              "scope": "this_run", "panel_key": design["key"]}
    result = resolve_panel(panel_from(design), "person", "she/her", {}, [change], {})
    assert "multiple views" not in result["negative"]
    assert "cropped feet" in result["negative"] and "hat" in result["negative"]


def test_explicit_subject_and_background_are_not_duplicated_by_the_simple_path():
    design = deepcopy(legacy_layout()[0])
    design["parts"] = [
        {"feature": "subject", "description_en": "two adults", "avoid_en": ""},
        {"feature": "background", "description_en": "gray background", "avoid_en": "white background"}]
    design["role_features"] = ["subject", "background"]
    result = resolve_panel(panel_from(design), "person", "he/him", {}, [], {})
    assert result["prompt"] == "person, two adults, gray background"
    assert "white background" in result["negative"]
