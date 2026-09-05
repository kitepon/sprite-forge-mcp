"""コメントの解釈案。モデル出力と利用者の確定入力を同じ型で受け取る。"""
from __future__ import annotations

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict

RecordKind = Literal["character", "style"]
Stage = Literal["samples", "training", "preview", "sheet", "panel", "drawing"]
Feature = Literal["face", "hair", "outfit", "style", "expression", "pose", "accessory", "background", "subject", "composition", "lighting"]
PREVIEW_TAGS = "full body, standing, front view, looking at viewer"
PREVIEW_CONDITIONS = {
    "composition": {"description_en": "full body", "avoid_en": ""},
    "pose": {"description_en": "standing, front view, looking at viewer", "avoid_en": ""},
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Reference(StrictModel):
    record_key: str
    sample_index: int
    path: str


class IntentRequest(StrictModel):
    name: str
    kind: RecordKind = "character"
    stage: Stage = "samples"
    comment: str
    panel: str = ""
    sample_indices: list[int] | None = None


class Observation(StrictModel):
    reference: Reference
    appearance_ja: str


class Change(StrictModel):
    feature: Feature
    scope: Literal["persistent", "this_run", "panel"]
    panel_key: str | None
    reference: Reference | None
    description_en: str
    avoid_en: str
    avoid_ja: str
    reason_ja: str


class Proposal(StrictModel):
    observations: list[Observation]
    changes: list[Change]
    questions: list[str]


def validate_proposal(proposal: Proposal, job: dict) -> None:
    """外部入力の参照先と範囲を検査する。衣装などの意味の合否は判定しない。"""
    references = job["references"]
    for item in [*proposal.observations, *proposal.changes]:
        if item.reference is not None and item.reference.model_dump() not in references:
            raise ValueError("解釈案が、渡していない参考画像を参照しています。")
    targets = set()
    for change in proposal.changes:
        if bool(change.avoid_en.strip()) != bool(change.avoid_ja.strip()):
            raise ValueError("避ける内容には、日本語と英語の両方の説明が必要です。")
        if job["record_kind"] == "style" and change.scope == "persistent" and change.feature != "style":
            raise ValueError("画風の共通条件へ被写体や衣装は保存できません。今回だけの条件にしてください。")
        if change.scope == "panel":
            if job["stage"] != "panel" or change.panel_key != job["panel"]:
                raise ValueError("パネル指定が今回の対象と一致しません。")
        elif change.panel_key is not None:
            raise ValueError("パネル限定以外の条件にパネル指定があります。")
        target = (change.feature, change.scope, change.panel_key)
        if target in targets:
            raise ValueError("同じ特徴と範囲の変更は一つにまとめてください。")
        targets.add(target)


def effective_conditions(common: dict, changes: list[Change]) -> dict:
    """確定済み共通条件を残し、今回の変更を特徴単位で反映する。"""
    result = deepcopy(common)
    # 今回／パネルの条件を、その呼出しでは共通条件より優先する。
    for scope in ("persistent", "this_run", "panel"):
        for change in changes:
            if change.scope == scope:
                result[change.feature] = change.model_dump()
    return result


def prompt_parts(conditions: dict) -> tuple[str, str]:
    return tuple(
        ", ".join(value[field].strip() for value in conditions.values() if value[field].strip())
        for field in ("description_en", "avoid_en")
    )


def preview_content(tags: str, conditions: dict) -> str:
    """既定の構図・姿勢を、その特徴の確定条件で置き換える。自由文は分解しない。"""
    if not conditions:
        return tags
    if tags and tags != PREVIEW_TAGS:
        raise ValueError("英語の自由入力と解釈した注文は同時に使えません。自由入力の内容を制作への注文に含めて解釈してください。")
    return prompt_parts({**PREVIEW_CONDITIONS, **conditions})[0]
