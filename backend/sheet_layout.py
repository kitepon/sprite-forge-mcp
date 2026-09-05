"""利用者が確認した構成と、完成済みシートの構成を区別する。"""
from copy import deepcopy
from typing import Literal, get_args

from pydantic import Field, model_validator

from . import bible
from .intent import Feature, StrictModel
from .panel_intent import inherited, role_conditions


class PanelPart(StrictModel):
    feature: Feature
    description_en: str
    avoid_en: str = ""


class PanelDesign(StrictModel):
    key: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", min_length=1, max_length=80)
    section: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: Literal["full", "face", "item", "chibi"]
    parts: list[PanelPart] = Field(min_length=1)
    role_features: list[Feature]
    inherited_features: list[Feature]
    seed_offset: int = Field(ge=0)

    @model_validator(mode="after")
    def check_content(self):
        if not self.label.strip() or not self.section.strip():
            raise ValueError("項目名と区分を入力してください。")
        if "style" in {part.feature for part in self.parts}:
            raise ValueError("構成に画風を固定せず、画風LoRAで指定してください。")
        if not set(self.role_features) <= {part.feature for part in self.parts}:
            raise ValueError("役割を持つ特徴には、描く内容を指定してください。")
        return self


class LayoutUpdate(StrictModel):
    expected: list[PanelDesign]
    panels: list[PanelDesign] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [panel.key for panel in self.panels]
        if len(keys) != len(set(keys)):
            raise ValueError("同じパネルの識別子を重複して使えません。")
        return self


def legacy_layout():
    return [{"key": p.key, "section": p.section, "label": p.label, "kind": p.kind,
             "parts": [{"feature": f, "description_en": text, "avoid_en": ""} for f, text in p.parts],
             "role_features": sorted(role_conditions(p)),
             "inherited_features": sorted(inherited(p, {key: {} for key in get_args(Feature)})),
             "seed_offset": index} for index, p in enumerate(bible.PANELS)]


def layout_for(record, *, generated=False):
    owner = record.get("bible", {}) if generated else record
    key = "layout" if generated else "sheet_layout"
    # 構成を保存していなかった旧記録は、従来23項目の定義で読む。
    return deepcopy(owner[key]) if key in owner else legacy_layout()


def panel_from(value):
    design = PanelDesign.model_validate(value)
    return bible.Panel(design.key, design.section, design.label, design.kind,
                       tuple((part.feature, part.description_en) for part in design.parts),
                       tuple((part.feature, part.avoid_en) for part in design.parts),
                       tuple(design.role_features), tuple(design.inherited_features))


def meaning(value):
    return {key: value[key] for key in ("kind", "parts", "role_features", "inherited_features")}


def matching_keys(before, after):
    prior = {p["key"]: meaning(p) for p in before}
    return {p["key"] for p in after if prior.get(p["key"]) == meaning(p)}


class LayoutServices:
    async def get_sheet_layout(self, name: str) -> list[dict]:
        """次回の設定画に使う構成を、編集前の比較用データとして返す。"""
        return layout_for(self._load_character(name))

    async def save_sheet_layout(self, name: str, layout: LayoutUpdate) -> list[dict]:
        """利用者が確認した構成を保存する。生成・学習・旧画像の変更は行わない。"""
        import uuid
        record = self._load_character(name)
        before = layout_for(record)
        if before != [p.model_dump() for p in layout.expected]:
            raise ValueError("シート構成が更新されています。最新の構成を読み直してください。")
        after = [p.model_dump() for p in layout.panels]
        previous = deepcopy(record.get("panel_overrides", {}))
        if record.get("bible"):
            record["bible"].setdefault("layout", legacy_layout())
            record["bible"].setdefault("panel_overrides", deepcopy(previous))
        keep = matching_keys(before, after)
        record["sheet_layout"] = after
        record["panel_overrides"] = {key: value for key, value in previous.items() if key in keep}
        self._save_character(record)
        self.events.save_job({"job_id": str(uuid.uuid4()), "kind": "sheet_layout", "status": "completed",
                              "name": name, "before": before, "layout": after,
                              "panel_overrides_before": previous})
        return after
