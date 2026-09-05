"""23パネルの既定を固定し、注文の接続で既存の役割を失わないことを確かめる。"""
import hashlib
import json
from typing import get_args

from backend import bible
from backend.intent import Feature


def test_all_existing_panel_defaults_remain_exact():
    rows = [{"key": p.key, "section": p.section, "label": p.label, "kind": p.kind,
             "tags": p.tags, "size": bible.size(p), "prompt": bible.panel_prompt(p, "fixture", "she/her")}
            for p in bible.PANELS]
    assert len(rows) == 23
    assert hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest() == (
        "25e8b8869651a6d6e08415b5fd48050627691e7f4f0a25ca04469d5f717dacd4")


def test_conditions_keep_each_feature_and_collect_nonadjacent_parts():
    panels = {p.key: p for p in bible.PANELS}
    for panel in panels.values():
        assert set(panel.conditions) <= set(get_args(Feature))
        assert all(value["description_en"] and value["avoid_en"] == "" for value in panel.conditions.values())
    assert panels["body_front"].conditions["pose"]["description_en"] == "standing, front view, arms slightly out"
    assert panels["body_front"].conditions["outfit"]["description_en"] == "plain white leotard, bodysuit, bare legs, barefoot"
    assert panels["ex_shy"].conditions["expression"]["description_en"] == "embarrassed, blush, nervous"
    assert panels["ex_shy"].conditions["pose"]["description_en"] == "looking away"
    assert panels["item_shoes"].conditions["outfit"]["description_en"] == "shoes, boots, footwear"
    assert panels["item_head"].conditions["accessory"]["description_en"] == "hair ornament, headwear"
    snapshot = panels["turn_front"].conditions
    snapshot["pose"]["description_en"] = "変更"
    assert panels["turn_front"].conditions["pose"]["description_en"] != "変更"


def test_raw_override_replaces_the_whole_content_without_classifying_words():
    for panel in bible.PANELS:
        subject = "" if panel.kind == "item" else "1girl, "
        assert bible.panel_prompt(panel, "fixture", "she/her", "arbitrary owner content") == (
            f"fixture, {subject}arbitrary owner content, simple background, white background")
        assert bible.panel_prompt(panel, "fixture", "she/her", "") == bible.panel_prompt(panel, "fixture", "she/her")
