"""Offline experiment wiring tests; not evidence of model or image quality."""
from copy import deepcopy
import json
import pytest
import subprocess
import sys

from intent_experiment import cases, payload, reference, check_bindings, validate_shape
import run_terra_suite as runner
from summarize_suite import evaluate


def empty_result(request):
    return {"original_comment": request["comment"], "observations": [], "changes": [],
            "preserved_conditions": [], "generation_description_en": "", "questions": []}


def test_casebook_and_no_evaluator_leak():
    book = cases()
    assert len(book) == len({c["name"] for c in book}) == 12
    for case in book:
        request = payload(case)
        assert case["human_review"] not in json.dumps(request, ensure_ascii=False)
        assert "human_review" not in request
        assert check_bindings(empty_result(request), request) == []


def test_order_changes_only_new_display_binding():
    case = cases()[1]
    before = deepcopy(case)
    request = payload(case)
    assert request["images_in_attachment_order"][3]["reference"] == reference(1)
    assert request["prior_comments"][0]["bound_reference"] == reference(3)
    assert case == before


def test_deleted_reference_not_present_as_image():
    request = payload(cases()[9])
    assert reference(3) not in [i["reference"] for i in request["images_in_attachment_order"]]
    result = empty_result(request)
    result["observations"] = [{"reference": reference(3), "appearance_ja": "fabricated"}]
    assert check_bindings(result, request)


@pytest.mark.parametrize("bad", ["3", True, 3.0])
def test_sample_index_must_be_integer_not_display_text(bad):
    result = empty_result(payload(cases()[0]))
    result["observations"] = [{"reference": {**reference(3), "sample_index": bad}, "appearance_ja": "x"}]
    with pytest.raises(ValueError):
        validate_shape(result)


def test_reference_tuple_and_original_are_exact():
    request = payload(cases()[0])
    result = empty_result(request)
    result["original_comment"] = "rewritten"
    result["observations"] = [{"reference": {**reference(3), "path": "other.png"}, "appearance_ja": "x"}]
    assert len(check_bindings(result, request)) == 2


def test_panel_scope_is_local():
    request = payload(cases()[7])
    result = empty_result(request)
    change = {"feature": "accessory", "scope": "panel", "panel_key": "run_front",
              "reference": None, "description_en": "remove hat", "reason_ja": "注文"}
    result["changes"] = [change]
    assert check_bindings(result, request) == []
    change["panel_key"] = "wrong"
    assert check_bindings(result, request)
    change["scope"] = "persistent"
    assert check_bindings(result, request)


def test_wrapped_or_extra_output_is_not_repaired():
    result = empty_result(payload(cases()[0]))
    for invalid in ({"result": result}, {**result, "extra": True}):
        with pytest.raises(ValueError):
            validate_shape(invalid)


def test_trial_uses_exact_order_native_login_and_no_api_override(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    images = tmp_path / "private" / "inputs"
    images.mkdir(parents=True)
    for index in range(4):
        (images / f"{index + 1:02d}.png").write_bytes(bytes([index]))
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.setenv(key, "test-only-value")
    case = cases()[1]

    def fake_run(command, **kwargs):
        assert all(key not in kwargs["env"] for key in
                   ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"))
        assert 'forced_login_method="chatgpt"' in command
        assert command[command.index("--model") + 1] == "gpt-5.6-terra"
        assert [command[i + 1] for i, value in enumerate(command) if value == "--image"] == [
            str(images / f"{i + 1:02d}.png") for i in case["order"]]
        assert case["human_review"] not in kwargs["input"]
        runner.write_json(kwargs["cwd"] / "result.json", empty_result(payload(case)))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.trial(case, 1, tmp_path)
    assert result["mechanical_errors"] == []
    metadata = json.loads((tmp_path / "reordered_new_request-1" / "metadata.json").read_text())
    assert [item["reference"]["sample_index"] for item in metadata["images"]] == case["order"]
    with pytest.raises(FileExistsError):
        runner.trial(case, 1, tmp_path)


def test_suite_does_not_launch_next_wave_after_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    (tmp_path / "private").mkdir()
    monkeypatch.setattr(sys, "argv", ["suite", "--batch", "test", "--workers", "2"])
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *a, **kw: "test CLI")
    monkeypatch.setattr(runner, "cases", lambda: [{"name": n} for n in ("a", "b", "c")])
    called = []

    def failed_trial(case, repeat, batch, revision):
        called.append((case["name"], repeat))
        return {"case": case["name"], "exit_code": 1, "mechanical_errors": ["failure"]}

    monkeypatch.setattr(runner, "trial", failed_trial)
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 1
    assert sorted(called) == [("a", 1), ("b", 1)]


def test_instruction_revision_is_explicit_and_case_expectations_stay_private():
    case = cases()[0]
    v3 = payload(case, "v3")
    v4 = payload(case, "v4")
    assert v4["instruction"].startswith(v3["instruction"])
    assert v3["instruction"] != v4["instruction"]
    assert {k: v for k, v in v3.items() if k != "instruction"} == {k: v for k, v in v4.items() if k != "instruction"}
    for request in (v3, v4):
        assert case["human_review"] not in json.dumps(request, ensure_ascii=False)
    with pytest.raises(ValueError):
        payload(case, "unrecorded")


@pytest.mark.parametrize("defect", ["wrong_image", "unnecessary_question", "tool_execution"])
def test_evaluator_rejects_semantic_routing_or_execution_defects(tmp_path, defect):
    case = cases()[8]
    request = payload(case)
    result = empty_result(request)
    result["generation_description_en"] = "Use the selected brushwork."
    result["changes"] = [{"feature": "style", "scope": "this_run", "panel_key": None,
                          "reference": reference(0), "description_en": "brushwork", "reason_ja": "注文"}]
    events = [{"type": "item.completed", "item": {"type": "agent_message"}}, {"type": "turn.completed"}]
    if defect == "wrong_image":
        result["changes"][0]["reference"] = reference(1)
    elif defect == "unnecessary_question":
        result["questions"] = ["今後も？"]
    else:
        events.insert(0, {"type": "item.completed", "item": {"type": "command_execution"}})
    runner.write_json(tmp_path / "input.json", request)
    runner.write_json(tmp_path / "result.json", result)
    runner.write_json(tmp_path / "metadata.json", {"case": case["name"], "repeat": 1, "elapsed_seconds": 1, "exit_code": 0})
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    assert evaluate(tmp_path)["mechanical_errors"]
