"""P1-only typed interpretation inputs. Not imported by the application."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def obj(**properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


STRING = {"type": "string"}
REF = obj(record_key=STRING, sample_index={"type": "integer"}, path=STRING)
SCHEMA = obj(
    original_comment=STRING,
    observations=array(obj(reference=REF, appearance_ja=STRING)),
    changes=array(obj(
        feature={"type": "string", "enum": ["face", "hair", "outfit", "style",
                                              "expression", "pose", "accessory", "background"]},
        scope={"type": "string", "enum": ["persistent", "this_run", "panel"]},
        panel_key={"type": ["string", "null"]},
        reference={"anyOf": [REF, {"type": "null"}]},
        description_en=STRING, reason_ja=STRING,
    )),
    preserved_conditions=array(STRING),
    generation_description_en=STRING,
    questions=array(STRING),
)


def reference(index):
    return {"record_key": "ndac1de01", "sample_index": index,
            "path": f"/app/.cache/characters/ndac1de01/samples/{index:03d}.png"}


def payload(case, revision="v3"):
    """Display order is a snapshot; historical bindings are never renumbered."""
    instruction = (ROOT / "instruction-v2.txt").read_text() + "\n" + (ROOT / "instruction-v3.txt").read_text()
    if revision == "v4":
        instruction += "\n" + (ROOT / "instruction-v4.txt").read_text()
    elif revision != "v3":
        raise ValueError("unknown instruction revision")
    return {
        "instruction": instruction,
        "comment": case["comment"],
        "existing_conditions": deepcopy(case["existing_conditions"]),
        "prior_comments": deepcopy(case.get("prior_comments", [])),
        "current_panel_key": case.get("current_panel_key"),
        "images_in_attachment_order": [
            {"display_number": position + 1, "reference": reference(index)}
            for position, index in enumerate(case["order"])
        ],
    }


def validate_shape(value, schema=SCHEMA, location="result"):
    """Validate this experiment's small schema subset, without repairing output."""
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate_shape(value, option, location)
                return
            except ValueError:
                pass
        raise ValueError(f"{location}: no matching alternative")
    types = schema["type"]
    types = types if isinstance(types, list) else [types]
    matches = {"null": value is None, "string": isinstance(value, str),
               "integer": type(value) is int, "array": isinstance(value, list),
               "object": isinstance(value, dict)}
    if not any(matches[t] for t in types):
        raise ValueError(f"{location}: expected {types}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{location}: invalid enum")
    if isinstance(value, dict):
        if set(value) != set(schema["properties"]):
            raise ValueError(f"{location}: missing or additional properties")
        for key, child in value.items():
            validate_shape(child, schema["properties"][key], f"{location}.{key}")
    if isinstance(value, list):
        for index, child in enumerate(value):
            validate_shape(child, schema["items"], f"{location}[{index}]")


def check_bindings(result, request):
    """Mechanical experiment checks only; these do not grade visual quality."""
    validate_shape(result)
    errors = []
    if result["original_comment"] != request["comment"]:
        errors.append("original comment changed")
    refs = [item["reference"] for item in request["images_in_attachment_order"]]
    for item in result["observations"] + result["changes"]:
        if item["reference"] is not None and item["reference"] not in refs:
            errors.append("reference is not an attached existing sample")
    for change in result["changes"]:
        if change["scope"] == "panel":
            if not request["current_panel_key"] or change["panel_key"] != request["current_panel_key"]:
                errors.append("wrong panel target")
        elif change["panel_key"] is not None:
            errors.append("non-panel change has panel target")
    return errors


def cases():
    return json.loads((ROOT / "cases-v3.json").read_text())
