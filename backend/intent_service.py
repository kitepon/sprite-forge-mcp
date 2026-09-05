"""原文・提案・確定条件の保存。RESTとMCPが共用する工程。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import get_args
import uuid

from . import bible
from .intent import Feature, IntentRequest, Observation, Proposal, PREVIEW_CONDITIONS, effective_conditions, prompt_parts, validate_proposal
from .panel_intent import inherited, role_conditions


class IntentServices:
    def _generation_intent(self, record: dict, kind: str, stage: str, job_id: str = "", panel: str = "") -> dict:
        conditions = deepcopy(record.get("intent_conditions", {}))
        if job_id:
            job = self.events.load_job(job_id)
            if (not job or job.get("kind") != "intent" or job["status"] != "confirmed"
                    or job["record_kind"] != kind or job["record_key"] != record["key"]
                    or job["record_created"] != record["created"] or job["stage"] != stage or job["panel"] != panel):
                raise ValueError("この工程で採用した解釈を指定してください。")
            if stage in ("sheet", "panel"):
                self._check_intent_layout(job, record)
            conditions = deepcopy(job["effective_conditions"])
            if stage in ("sheet", "panel"):
                conditions = deepcopy(job.get("common_conditions", job["base_conditions"]))
        # 画風の希望は画風LoRAの選択・学習で反映する。内容文へ平坦化しない。
        style = conditions.get("style", {})
        if style.get("description_en") or style.get("avoid_en"):
            raise ValueError("画風の希望は、画風の学習・選択で反映する必要があります。内容の注文と分けて確認してください。")
        positive, negative = prompt_parts(conditions)
        result = {"intent_job_id": job_id or None, "intent_conditions": conditions,
                  "intent_positive": positive, "intent_negative": negative}
        if stage in ("sheet", "panel"):
            result["intent_changes"] = deepcopy(job["accepted"]["changes"]) if job_id else []
            if stage == "panel":
                for change in result["intent_changes"]:
                    if change["scope"] == "this_run" and change["panel_key"] is None:
                        change["panel_key"] = panel
        return result

    def _intent_record(self, name: str, kind: str):
        return self._load_character(name) if kind == "character" else self._load_style(name)

    def _save_intent_record(self, record: dict, kind: str):
        return self._save_character(record) if kind == "character" else self._save_style(record)

    def _check_intent_layout(self, job, record):
        from .sheet_layout import layout_for, legacy_layout
        expected = job["sheet_layout"] if "sheet_layout" in job else legacy_layout()
        if expected != layout_for(record, generated=job["stage"] == "panel"):
            raise ValueError("シート構成が変わっています。今の構成で注文を読み直してください。")
        if job["stage"] == "panel" and ("source_bible_id" not in job or job["source_bible_id"] != record.get("bible", {}).get("job_id")):
            raise ValueError("対象の設定画が変わったか、古い注文に対象の記録がありません。今の設定画で注文を読み直してください。")

    async def save_comment(self, request: IntentRequest) -> dict:
        """注文と画像順を保存する。モデルや画像生成は呼ばない。"""
        record = self._intent_record(request.name, request.kind)
        from .sheet_layout import layout_for, panel_from
        layout = layout_for(record, generated=request.stage == "panel")
        if request.layout_panels is not None:
            if request.stage != "layout":
                raise ValueError("編集中の構成は構成工程だけで指定してください。")
            if request.layout_expected != layout:
                raise ValueError("構成が更新されています。最新の構成を確認してから注文してください。")
            from .sheet_layout import LayoutUpdate
            working = LayoutUpdate.model_validate({"expected": layout, "panels": request.layout_panels})
        if request.kind == "style" and request.stage in ("panel", "sheet", "layout"):
            raise ValueError("設定画とパネルはキャラクターの工程です。")
        if request.stage == "panel" and request.panel not in {p["key"] for p in layout}:
            raise ValueError("描き直すパネルを指定してください。")
        if request.stage != "panel" and request.panel:
            raise ValueError("パネルの指定は描き直し工程で使ってください。")
        indices = request.sample_indices
        if indices is None:
            indices = [s["index"] for s in record["samples"]]
        samples = {s["index"]: s for s in record["samples"]}
        if len(set(indices)) != len(indices) or any(i not in samples for i in indices):
            raise ValueError("参考画像が更新されています。画像一覧を読み直してください。")
        selected = [samples[i] for i in indices]
        job = {"job_id": str(uuid.uuid4()), "kind": "intent", "status": "draft",
               "name": request.name, "record_kind": request.kind, "record_key": record["key"],
               "record_created": record["created"], "stage": request.stage, "panel": request.panel,
               "original_comment": request.comment,
               "record_description": record.get("char_desc", record.get("note", "")),
               "existing_settings": {key: deepcopy(record[key]) for key in ("char_desc", "attr", "style", "style_strength", "panel_overrides") if key in record},
               "references": [{"record_key": record["key"], "sample_index": s["index"], "path": s["path"]} for s in selected],
               "image_comments": [s.get("caption", "") for s in selected],
               "training_captions": [deepcopy(s.get("training_caption")) for s in selected],
               "stage_conditions": deepcopy(PREVIEW_CONDITIONS) if request.kind == "character" and request.stage == "preview" else {},
               "base_conditions": deepcopy(record.get("intent_conditions", {}))}
        if request.stage in ("sheet", "panel", "layout"):
            job["sheet_layout"] = layout
            if request.layout_panels is not None:
                job["working_layout"] = [p.model_dump() for p in working.panels]
            if request.stage == "panel":
                job["source_bible_id"] = record.get("bible", {}).get("job_id")
                job["existing_settings"]["panel_overrides"] = deepcopy(record.get("bible", {}).get("panel_overrides", record.get("panel_overrides", {})))
            job["stage_conditions"] = {"background": {"description_en": bible.COMMON, "avoid_en": ""}}
            job["panel_specs"] = [{"key": p.key, "section": p.section, "label": p.label, "kind": p.kind,
                                   "conditions": p.conditions,
                                   "role_features": sorted(role_conditions(p)),
                                   "inherited_features": sorted(inherited(p, {key: {} for key in get_args(Feature)}))}
                                  for p in map(panel_from, layout) if not request.panel or p.key == request.panel]
        self.events.save_job(job)
        return job

    async def interpret_comment(self, request: IntentRequest) -> dict:
        """注文を保存して解釈案を返す。採用や学習・画像生成は行わない。"""
        job = await self.save_comment(request)
        return await self.interpret_saved_comment(job["job_id"])

    async def interpret_saved_comment(self, job_id: str) -> dict:
        """保存した注文を一回解釈する。失敗した呼出しは再試行しない。"""
        job = self.events.load_job(job_id)
        if not job or job.get("kind") != "intent" or job["status"] != "draft":
            raise ValueError("未解釈の注文が見つかりません。注文を保存してください。")
        job["status"] = "running"
        self.events.save_job(job)
        self.events.append(job["job_id"], "interpreting", {"name": job["name"]})
        with self._job_errors(job):
            if job["stage"] not in ("samples", "training") and not job["original_comment"].strip() and not any(c.strip() for c in job["image_comments"]):
                raise ValueError("制作への注文か、画像ごとのコメントを入力してください。")
            # 呼出し前に画像も固定する。解釈中の削除で別画像へ差し替わらない。
            images = [Path(ref["path"]).read_bytes() for ref in job["references"]]
            result = await self.intent_interpreter(job, images)
            if job["stage"] == "layout":
                from .sheet_layout import LayoutProposal, validate_layout_proposal
                proposal = LayoutProposal.model_validate(result)
                validate_layout_proposal(proposal, job)
            else:
                proposal = Proposal.model_validate(result)
                validate_proposal(proposal, job)
            job.update(status="awaiting_confirmation", proposal=proposal.model_dump())
            self.events.save_job(job)
            self.events.append(job["job_id"], "interpretation_ready", {})
        return job

    async def confirm_training_observations(self, job_id: str, observations: list[Observation]) -> dict:
        """画像の観察だけを教材説明として確認する。希望の採用・学習はしない。"""
        job = self.events.load_job(job_id)
        if (not job or job.get("kind") != "intent" or job["stage"] not in ("samples", "training")
                or job["status"] not in ("awaiting_confirmation", "confirmed")):
            raise ValueError("参考画像・学習工程の解釈案を指定してください。")
        if job.get("accepted_observations"):
            raise ValueError("この画像説明は確認済みです。訂正する場合は注文を読み直してください。")
        refs = [item.reference.model_dump() for item in observations]
        if len(refs) != len(job["references"]) or any(refs.count(ref) != 1 for ref in job["references"]):
            raise ValueError("渡した参考画像すべての教材の説明を、一枚ずつ確認してください。")
        if any(not item.caption_en.strip() or not item.appearance_ja.strip() for item in observations):
            raise ValueError("教材の説明には、画像の観察と英語の両方を入力してください。")
        record = self._intent_record(job["name"], job["record_kind"])
        if record["created"] != job["record_created"]:
            raise ValueError("対象が作り直されています。注文を読み直してください。")
        samples = {s["index"]: s for s in record["samples"]}
        for item in observations:
            ref = item.reference.model_dump()
            sample = samples.get(item.reference.sample_index)
            if not sample or sample["path"] != item.reference.path:
                raise ValueError("参照画像が外されています。注文を読み直してください。")
            prior = job.get("training_captions", [None] * len(job["references"]))[job["references"].index(ref)]
            if sample.get("training_caption") != prior:
                raise ValueError("同じ画像の教材の説明が更新されています。注文を読み直してください。")
        for item in observations:
            samples[item.reference.sample_index]["training_caption"] = {
                "caption_en": item.caption_en, "appearance_ja": item.appearance_ja, "intent_job_id": job_id}
        self._save_intent_record(record, job["record_kind"])
        job["accepted_observations"] = [item.model_dump() for item in observations]
        self.events.save_job(job)
        self.events.append(job_id, "training_observations_confirmed", {})
        return job

    async def list_comment_intents(self, name: str, kind: str = "character") -> list[dict]:
        if kind not in ("character", "style"):
            raise ValueError("対象はcharacterかstyleを指定してください。")
        record = self._intent_record(name, kind)
        return sorted([job for job in self.events.list_jobs()
                if job.get("kind") == "intent" and job.get("record_kind") == kind
                and job.get("record_key") == record["key"] and job.get("record_created") == record["created"]],
                key=lambda job: job["created_at"], reverse=True)

    async def confirm_comment_intent(self, job_id: str, proposal: Proposal) -> dict:
        """利用者が確認・訂正した提案を採用する。共通条件以外は台帳へ昇格させない。"""
        candidate = self.events.load_job(job_id)
        if candidate and candidate.get("stage") == "layout":
            raise ValueError("構成案は構成の確定操作で保存してください。")
        job = self.events.load_job(job_id)
        if not job or job.get("kind") != "intent":
            raise ValueError("コメントの解釈記録が見つかりません。")
        if job["status"] != "awaiting_confirmation":
            raise ValueError("この解釈案は確認待ちではありません。注文を読み直してください。")
        validate_proposal(proposal, job)
        if proposal.questions:
            raise ValueError("確認事項に答えてから、注文を読み直してください。")
        if any(change.feature == "style" for change in proposal.changes):
            raise ValueError("画風の解釈は学習・選択への接続が未完了です。画風LoRAを選んでください。この提案はまだ採用していません。")
        record = self._intent_record(job["name"], job["record_kind"])
        if record["created"] != job["record_created"]:
            raise ValueError("対象が作り直されています。注文を読み直してください。")
        if job["stage"] in ("sheet", "panel"):
            self._check_intent_layout(job, record)
        current_refs = [{"record_key": record["key"], "sample_index": s["index"], "path": s["path"]} for s in record["samples"]]
        for item in [*proposal.observations, *proposal.changes]:
            if item.reference is not None and item.reference.model_dump() not in current_refs:
                raise ValueError("参照画像が外されています。注文を読み直してください。")
        common = record.setdefault("intent_conditions", {})
        for change in proposal.changes:
            if common.get(change.feature) != job["base_conditions"].get(change.feature):
                raise ValueError("同じ特徴の条件が更新されています。注文を読み直してください。")
        for change in proposal.changes:
            if change.scope == "persistent":
                common[change.feature] = change.model_dump()
        self._save_intent_record(record, job["record_kind"])
        job.update(status="confirmed", accepted=proposal.model_dump(),
                   common_conditions=deepcopy(common),
                   effective_conditions=effective_conditions(common, [c for c in proposal.changes if c.panel_key is None])
                   if job["stage"] in ("sheet", "panel") else effective_conditions(common, proposal.changes))
        self.events.save_job(job)
        self.events.append(job_id, "interpretation_confirmed", {})
        return job
