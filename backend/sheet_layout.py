"""利用者が確認した構成と、完成済みシートの構成を区別する。"""
from copy import deepcopy
from typing import Literal, get_args

from pydantic import Field, model_validator

from . import bible
from .intent import Feature, Reference, StrictModel
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


class LayoutPanel(PanelDesign):
    description_ja: str = Field(min_length=1)
    reference: Reference | None


class LayoutProposal(StrictModel):
    summary_ja: str
    panels: list[LayoutPanel] = Field(min_length=1)
    questions: list[str]


def proposed_layout(proposal):
    return [panel.model_dump(exclude={"description_ja", "reference"}) for panel in proposal.panels]


def validate_layout_proposal(proposal, job):
    LayoutUpdate.model_validate({"expected": job["sheet_layout"], "panels": proposed_layout(proposal)})
    previous = {p["key"]: p for p in job.get("working_layout", job["sheet_layout"])}
    previous_offsets = {p["seed_offset"] for p in previous.values()}
    for panel in proposal.panels:
        if panel.reference is not None and panel.reference.model_dump() not in job["references"]:
            raise ValueError("構成案が渡していない画像を参照しています。")
        if panel.key in previous and panel.seed_offset != previous[panel.key]["seed_offset"]:
            raise ValueError("既存項目のSeedの差分は変更しないでください。")
        if panel.key not in previous and panel.seed_offset in previous_offsets:
            raise ValueError("既存項目の識別子を変更しないでください。新しい項目には未使用のSeedの差分を指定してください。")


def legacy_layout():
    return [{"key": p.key, "section": p.section, "label": p.label, "kind": p.kind,
             "parts": [{"feature": f, "description_en": text,
                        "avoid_en": p.conditions[f]["avoid_en"] if f not in dict(p.parts[:index]) else ""}
                       for index, (f, text) in enumerate(p.parts)],
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
    async def discard_sheet_layout(self, job_id: str) -> dict:
        """構成案を使わないことを記録する。原文・案は履歴から消さない。"""
        job = self.events.load_job(job_id)
        if not job or job.get("kind") != "intent" or job.get("stage") != "layout" or job["status"] not in ("draft", "awaiting_confirmation", "failed"):
            raise ValueError("解釈中でも確定済みでもない構成案を指定してください。")
        job["status"] = "discarded"
        self.events.save_job(job)
        self.events.append(job_id, "layout_discarded", {})
        return job

    async def confirm_sheet_layout(self, job_id: str, proposal: LayoutProposal) -> dict:
        """訂正後の構成案を確定する。注文・解釈案はそのまま履歴に残す。"""
        job = self.events.load_job(job_id)
        if not job or job.get("kind") != "intent" or job.get("stage") != "layout" or job["status"] != "awaiting_confirmation":
            raise ValueError("未確定の構成案を指定してください。")
        if proposal.questions:
            raise ValueError("確認したい点に回答して、構成案を読み直してください。")
        record = self._load_character(job["name"])
        if record["created"] != job["record_created"]:
            raise ValueError("対象が作り直されています。構成案を読み直してください。")
        validate_layout_proposal(proposal, job)
        current_refs = [{"record_key": record["key"], "sample_index": s["index"], "path": s["path"]} for s in record["samples"]]
        if any(p.reference is not None and p.reference.model_dump() not in current_refs for p in proposal.panels):
            raise ValueError("参照画像が外されています。構成案を読み直してください。")
        layout = await self.save_sheet_layout(job["name"], LayoutUpdate.model_validate({"expected": job["sheet_layout"], "panels": proposed_layout(proposal)}))
        job.update(status="confirmed", accepted=proposal.model_dump(), confirmed_layout=layout)
        self.events.save_job(job)
        self.events.append(job_id, "layout_confirmed", {})
        return job

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
        if any(not any(part["description_en"].strip() for part in panel["parts"]) for panel in after):
            raise ValueError("各項目の描く内容を指定してください。言葉から構成案を作ることもできます。")
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
