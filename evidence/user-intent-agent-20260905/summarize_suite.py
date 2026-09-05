"""Reproducible P1 mechanical checks, deliberately separate from human review."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from intent_experiment import cases, check_bindings


# Expectations belong to the evaluator, never the interpretation prompt.
EXPECTED = {
    "fourth_outfit": [("outfit", "this_run", 3)],
    "reordered_new_request": [("outfit", "this_run", 1)],
    "face_and_outfit": [("face", "this_run", 0), ("outfit", "this_run", 3)],
    "one_run": [("pose", "this_run", None), ("expression", "this_run", None)],
    "replace_persistent": [("outfit", "persistent", 1)],
    "observed_vs_desired": [("outfit", "this_run", 3)],
    "ambiguous_expression": [],
    "panel_accessory": [("accessory", "panel", None)],
    "style_only": [("style", "this_run", 0)],
    "missing_deleted_ambiguous": [],
    "quoted_text": [("expression", "this_run", None)],
    "heldout_other_outfit": [("outfit", "this_run", 0)],
}


def evaluate(path):
    request = json.loads((path / "input.json").read_text())
    result = json.loads((path / "result.json").read_text())
    meta = json.loads((path / "metadata.json").read_text())
    errors = check_bindings(result, request)
    actual = [(item["feature"], item["scope"],
               item["reference"]["sample_index"] if item["reference"] else None)
              for item in result["changes"]]
    if sorted(actual, key=repr) != sorted(EXPECTED[meta["case"]], key=repr):
        errors.append("unexpected change feature/scope/reference")
    if meta["case"] in ("ambiguous_expression", "missing_deleted_ambiguous"):
        if not result["questions"] or result["generation_description_en"]:
            errors.append("unresolved request has no question or has generation text")
    elif meta["case"] == "fourth_outfit":
        if not result["questions"]:
            errors.append("missing duration question")
    elif result["questions"]:
        errors.append("unexpected clarification")
    event_types = []
    completed_turns = 0
    for line in (path / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event["type"] == "item.completed":
            event_types.append(event["item"]["type"])
        if event["type"] in ("error", "turn.failed"):
            errors.append("CLI error event")
        if event["type"] == "turn.completed":
            completed_turns += 1
    if completed_turns != 1 or event_types != ["agent_message"] or meta["exit_code"] != 0:
        errors.append("unexpected execution trace")
    return {"case": meta["case"], "repeat": meta["repeat"],
            "seconds": meta["elapsed_seconds"], "mechanical_errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    config = json.loads((args.batch / "batch.json").read_text())
    results, missing = [], []
    for repeat in range(1, config["repeats"] + 1):
        for name in config["cases"]:
            path = args.batch / f"{name}-{repeat}"
            if not (path / "result.json").exists():
                missing.append(path.name)
            else:
                results.append(evaluate(path))
    times = [r["seconds"] for r in results]
    report = {"completed": len(results), "missing": missing,
              "mechanical_failures": [r for r in results if r["mechanical_errors"]],
              "latency_seconds": {"min": min(times), "median": statistics.median(times), "max": max(times)} if times else None,
              "per_case": {case["name"]: [r for r in results if r["case"] == case["name"]] for case in cases()},
              "meaning_and_visual_quality": "requires separate human review"}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
