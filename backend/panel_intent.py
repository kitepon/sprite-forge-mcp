"""パネルの役割と、確認済みの対象別の注文を合成する。語彙から内容を推測しない。"""
from copy import deepcopy

from . import bible
from .intent import prompt_parts


def inherited(panel, conditions):
    if panel.kind != "item":
        return deepcopy(conditions)
    features = {"background", "lighting"}
    if panel.key == "item_outfit":
        features.add("outfit")
    return {key: deepcopy(value) for key, value in conditions.items() if key in features}


def role_conditions(panel):
    return {key: value for key, value in panel.conditions.items()
            if not (panel.key == "item_outfit" and key == "outfit")}


def resolve_panel(panel, trigger, char_desc, common, changes, saved, intent_job_id=""):
    targeted = [c for c in changes if c["panel_key"] == panel.key]
    shared = inherited(panel, common)
    temporary = inherited(panel, {c["feature"]: c for c in changes
                                  if c["scope"] == "this_run" and c["panel_key"] is None})
    legacy = saved.get("tags") or saved.get("avoid")
    if legacy and not targeted and (shared or temporary):
        raise ValueError(f"{panel.label}の保存済み英語修正を、対象パネルの注文に取り込んで解釈・採用してください。")
    if not shared and not temporary and not targeted and not saved.get("conditions"):
        return {"prompt": bible.panel_prompt(panel, trigger, char_desc, saved.get("tags", "")),
                "negative": ", ".join(p for p in (bible.NEGATIVE, saved.get("avoid", "")) if p),
                "conditions": {}}
    conditions = {"background": {"description_en": bible.COMMON, "avoid_en": ""}}
    if panel.kind != "item":
        conditions["subject"] = {"description_en": bible.subject_tag(char_desc), "avoid_en": ""}
    conditions.update(panel.conditions)
    conditions.update(shared)
    conditions.update(role_conditions(panel))
    conditions.update(deepcopy(saved.get("conditions", {})))
    conditions.update(temporary)
    for scope in ("panel", "this_run"):
        conditions.update({c["feature"]: deepcopy(c) for c in targeted if c["scope"] == scope})
    # 背景は従来同様に末尾へ置く。各特徴の肯定・否定を同じ条件から作る。
    background = conditions.pop("background")
    conditions["background"] = background
    positive, negative = prompt_parts(conditions)
    return {"prompt": ", ".join(p for p in (trigger, positive) if p),
            "negative": ", ".join(p for p in (bible.NEGATIVE, negative) if p), "conditions": conditions}


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
