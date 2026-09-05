"""実測表示で構成の役割と対象別注文を正しく使う。モデル・GPUは呼ばない。"""
import importlib.util
from pathlib import Path

from backend.sheet_layout import legacy_layout
from tests.test_sheet_panel_intent import change

spec = importlib.util.spec_from_file_location("reference_probe", Path(__file__).parents[1] / "evidence/user-intent-agent-20260905/render_reference_probe.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_preview_uses_custom_roles_and_targeted_changes_without_saving():
    layout = legacy_layout()[:1]
    layout[0]["parts"].append({"feature": "outfit", "description_en": "red cape", "avoid_en": ""})
    layout[0]["role_features"].append("outfit")
    value = {"stage": "sheet", "record_description": "he/him", "base_conditions": {}, "existing_settings": {},
             "sheet_layout": layout, "proposal": {"questions": [], "changes": [change("outfit", "green cape")]}}
    assert "red cape" in module.resolve_candidate(value)[0]["prompt"]
    value["proposal"]["changes"].append(change("outfit", "green cape", panel=layout[0]["key"]))
    result = module.resolve_candidate(value)[0]
    assert "green cape" in result["prompt"] and "red cape" not in result["prompt"]
    assert value["base_conditions"] == {}


def test_unanswered_or_layout_proposals_do_not_claim_resolved_generation():
    assert module.resolve_candidate({"stage": "layout"}) == []
    assert module.resolve_candidate({"stage": "sheet", "proposal": {"questions": ["参照はどれ？"]}}) == []
