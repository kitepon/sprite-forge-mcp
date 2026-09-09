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


SAME = "Draw the same character as in the reference image, keeping the face, hair and outfit identical."
KEEP_FACE = "Keep the face, hairstyle and hair ornaments exactly as in the reference image."
STRIP_OUTFIT = "Remove the original top, sleeves, collar, skirt, gloves and footwear; none of them remain."
CHIBI = ("Redraw the character in chibi super deformed style: the head is as large as the whole body, "
         "the limbs are short and stubby, and there are only two head-heights in total. "
         "Keep the face, hairstyle and outfit design recognisable.")
# 参照から置き換える特徴。ここに挙げた特徴だけを命令文の主節へ出し、残りは末尾に並べる。
REPLACED = {"full": ("outfit",), "item": ("outfit", "accessory")}


def edit_instruction(panel, conditions, tags=""):
    """合格シートから切り出した人物へ、このパネルの内容を描かせる文。

    編集モデルは文頭の命令を強く採り、後ろのタグを装飾として扱う。衣装替え・チビ・小物は、替える内容を
    主節へ置き、残すものを従属節へ回した時だけ頼んだ絵になった（evidence/bible-sheet-source-20260910）。"""
    replaced = REPLACED.get(panel.kind, ())
    if tags:
        # 英語の自由入力は特徴に分かれていない。小物のパネルではその文が品物の指定なので主節へ置く。
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
        return (f"Remove the character completely. Draw only the {change}, laid out on their own "
                f"as a still life. {content}")
    if panel.kind == "chibi":
        return f"{CHIBI} {content}"
    if change:
        return f"Replace the character's clothes with: {change}. {STRIP_OUTFIT} {KEEP_FACE} {content}"
    return f"{SAME} {content}"


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
