"""パネルの役割と、確認済みの対象別の注文を合成する。語彙から内容を推測しない。"""
from copy import deepcopy

from . import bible
from .intent import prompt_parts


def inherited(panel, conditions):
    if panel.inherited_features is not None:
        return {key: deepcopy(value) for key, value in conditions.items() if key in panel.inherited_features}
    if panel.kind != "item":
        return deepcopy(conditions)
    features = {"background", "lighting"}
    if panel.key == "item_outfit":
        features.add("outfit")
    return {key: deepcopy(value) for key, value in conditions.items() if key in features}


def role_conditions(panel):
    if panel.role_features is not None:
        return {key: value for key, value in panel.conditions.items() if key in panel.role_features}
    return {key: value for key, value in panel.conditions.items()
            if not (panel.key == "item_outfit" and key == "outfit")}


SHEET = "Use this character sheet as the only reference. Draw one panel."
ONE = "Only one character in the image. Do not draw multiple people. Do not copy the whole sheet."
CHIBI = ("Redraw the character in chibi super deformed style: the head is as large as the whole body, "
         "the limbs are short and stubby, and there are only two head-heights in total.")
REPLACED = {"full": ("outfit",), "item": ("outfit", "accessory")}


def edit_instruction(panel, conditions, tags=""):
    """一枚シートだけを参照に、このパネルを一体で描かせる文。"""
    replaced = REPLACED.get(panel.kind, ())
    if tags:
        change, rest = (tags, []) if panel.kind == "item" else ("", [tags])
    else:
        described = [(feature, value["description_en"]) for feature, value in conditions.items()
                     if value.get("description_en")]
        change = ", ".join(text for feature, text in described if feature in replaced)
        rest = [text for feature, text in described if feature not in replaced]
    if panel.kind != "item":
        rest.append("solo")
    if "background" not in conditions:
        rest.append(bible.COMMON)
    content = ", ".join(part for part in rest if part)
    if panel.kind == "item":
        return (f"Use this character sheet as the only reference. Draw only the {change}, "
                f"laid out as a still life. No character. {content}")
    if panel.kind == "chibi":
        return f"{SHEET} {CHIBI} {content} {ONE}"
    if change:
        return f"{SHEET} Draw them wearing {change}. {content} {ONE}"
    return f"{SHEET} {content} {ONE}"


def resolve_panel(panel, trigger, char_desc, common, changes, saved, intent_job_id=""):
    targeted = [c for c in changes if c["panel_key"] == panel.key]
    shared = inherited(panel, common)
    temporary = inherited(panel, {c["feature"]: c for c in changes
                                  if c["scope"] == "this_run" and c["panel_key"] is None})
    legacy = saved.get("tags") or saved.get("avoid")
    if legacy and not targeted and (shared or temporary):
        raise ValueError(f"{panel.label}の保存済み英語修正を、対象パネルの注文に取り込んで解釈・採用してください。")
    if not shared and not temporary and not targeted and not saved.get("conditions"):
        _, negative = prompt_parts(panel.conditions)
        tags = saved.get("tags", "")
        return {"prompt": bible.panel_prompt(panel, trigger, char_desc, tags),
                "instruction": edit_instruction(panel, panel.conditions, tags),
                "negative": ", ".join(p for p in (bible.QUALITY_NEGATIVE, negative, saved.get("avoid", "")) if p),
                "conditions": {}}
    conditions = {"background": {"description_en": bible.COMMON, "avoid_en": ""}}
    if panel.kind != "item":
        conditions["subject"] = {"description_en": bible.subject_tag(char_desc), "avoid_en": ""}
    conditions.update(panel.conditions)
    conditions.update(shared)
    conditions.update(role_conditions(panel))
    conditions.update(deepcopy(saved.get("conditions", {})))
    conditions.update({key: value for key, value in temporary.items() if key not in role_conditions(panel)})
    for scope in ("panel", "this_run"):
        conditions.update({c["feature"]: deepcopy(c) for c in targeted if c["scope"] == scope})
    # 背景は従来同様に末尾へ置く。各特徴の肯定・否定を同じ条件から作る。
    background = conditions.pop("background")
    conditions["background"] = background
    positive, negative = prompt_parts(conditions)
    return {"prompt": ", ".join(p for p in (trigger, positive) if p),
            "instruction": edit_instruction(panel, conditions),
            "negative": ", ".join(p for p in (bible.QUALITY_NEGATIVE, negative) if p), "conditions": conditions}


def saved_corrections(current, previous, changes, seeds, job_id):
    """成功した対象の保存案だけを差分適用する。別のパネル更新は保持する。"""
    result = deepcopy(current)
    targets = {c["panel_key"] for c in changes if c["scope"] == "panel"}
    for key in targets:
        if current.get(key) != previous.get(key):
            raise ValueError("同じパネルの修正が更新されています。今回の保存案で上書きしていません。")
        conditions = deepcopy(current.get(key, {}).get("conditions", {}))
        conditions.update({c["feature"]: deepcopy(c) for c in changes if c["scope"] == "panel" and c["panel_key"] == key})
        result[key] = {"conditions": conditions, "seed": seeds[key], "intent_job_id": job_id}
    return result
