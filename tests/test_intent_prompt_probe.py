"""切り分け実験が肯定文以外を変えないことを確認する。"""
from copy import deepcopy

import pytest

from scripts.probe_intent_prompt import replace_positive


def test_probe_changes_only_requested_phrase():
    graph = {"20": {"inputs": {"text": "standing, side view, smiling"}},
             "21": {"inputs": {"text": "bad hands"}},
             "23": {"inputs": {"seed": 2, "steps": 28}}}
    original = deepcopy(graph)
    result = replace_positive(graph, "side view", "profile view")
    assert graph == original
    assert result["20"]["inputs"]["text"] == "standing, profile view, smiling"
    result["20"]["inputs"]["text"] = original["20"]["inputs"]["text"]
    assert result == original


@pytest.mark.parametrize("text, old", [("abc", ""), ("abc", "xyz"), ("abc abc", "abc")])
def test_probe_rejects_ambiguous_external_input(text, old):
    with pytest.raises(ValueError, match="一箇所"):
        replace_positive({"20": {"inputs": {"text": text}}}, old, "new")
