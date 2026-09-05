"""診断実験が指定した入力以外を変えないことを確認する。"""
from copy import deepcopy

import pytest

from backend.workflows import anima_txt2img
from scripts.probe_sheet_causes import perturb


def test_phrase_probe_changes_only_the_positive_text():
    graph = anima_txt2img("person, character reference, standing", 3, lora_name="person.safetensors")
    before = deepcopy(graph)
    changed = perturb(graph, {"factor": "positive_phrase", "old": "character reference, ", "new": ""})
    expected = deepcopy(graph)
    expected["20"]["inputs"]["text"] = "person, standing"
    assert changed == expected and graph == before


def test_lora_probe_changes_only_both_strengths_and_keeps_source():
    graph = anima_txt2img("person", 3, lora_name="person.safetensors")
    before = deepcopy(graph)
    case = {"factor": "node_inputs", "changes": [
        {"node": "4", "input": field, "before": .8, "after": 0}
        for field in ("strength_model", "strength_clip")]}
    result = perturb(graph, case)
    expected = deepcopy(graph)
    expected["4"]["inputs"].update(strength_model=0, strength_clip=0)
    assert result == expected and graph == before
    case["changes"][0]["before"] = .7
    with pytest.raises(ValueError, match="事前条件"):
        perturb(graph, case)
    assert graph == before
