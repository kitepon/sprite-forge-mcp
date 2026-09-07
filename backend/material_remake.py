"""NG指摘から元教材を見直し、既存LoRAを触らずに作り直す。"""
from copy import deepcopy
from pathlib import Path
import uuid

from .config import CACHE
from .intent import Proposal
from .material_revision import (
    freeze_revised_materials,
    revision_html,
    revision_images,
    revision_packet,
    selection_rows,
    validate_revision,
)


class MaterialRemake:
    async def propose_material_revision(self, name: str, job_id: str, request_id: str) -> dict:
        """NG指摘から教材の採否と説明の見直し案を作る。台帳のLoRAは変えない。"""
        uuid.UUID(request_id)
        existing = self.events.load_job(request_id)
        if existing:
            if existing.get("kind") != "material_revision" or existing.get("source_job_id") != job_id or existing.get("name") != name:
                raise ValueError("別の学習に使われた要求IDです。")
            return existing
        view = await self.preview_reviews(name, job_id)
        record = self._load_character(name)
        source = self.events.load_job(job_id)
        pictures = deepcopy(view["pictures"])
        for picture in pictures:
            if picture["review"]["rating"] != "ng":
                continue
            await self._interpret_preview_review(name, source, picture, record["samples"])
        packet = revision_packet(record, pictures, await self._learning_comments(name, "character"))
        images = revision_images(record, pictures)
        job = {"job_id": request_id, "kind": "material_revision", "status": "interpreting", "name": name,
               "source_job_id": job_id, "character_created": record["created"],
               "record_key": record["key"], "lora_before": record.get("lora_name", ""),
               "samples": deepcopy(record["samples"]), "ng": [p for p in pictures if p["review"]["rating"] == "ng"],
               "packet": packet, "baseline_prompt": {"prompt": source.get("prompt"), "negative": source.get("negative"),
                                                     "loras": source.get("loras"), "generation": source.get("generation")}}
        self.events.save_job(job)
        with self._job_errors(job):
            interpreter_job = {"stage": "material_revision", "revision_input": packet}
            proposal = Proposal.model_validate(await self.intent_interpreter(interpreter_job, images))
            validate_revision(proposal, packet)
            job["proposal"] = proposal.model_dump()
            job["interpreter"] = interpreter_job.get("interpreter")
            if proposal.questions:
                job.update(status="awaiting_answers", questions=proposal.questions)
            else:
                job["status"] = "awaiting_confirmation"
            self._store_revision_view(job, record, proposal)
            self.events.save_job(job)
            return job

    async def remake_lora_from_revision(self, name: str, request_id: str, steps: int = 1200) -> dict:
        """見直し案でAnima Baseから新しいLoRAを学習する。採用中のLoRAは置き換えない。"""
        if steps < 1:
            raise ValueError("学習ステップは1以上を指定してください。")
        job = self.events.load_job(request_id)
        if not job or job.get("kind") != "material_revision" or job.get("name") != name:
            raise ValueError("このキャラクターの教材見直しを指定してください。")
        if job["status"] == "completed":
            return job
        if job["status"] != "awaiting_confirmation":
            raise ValueError("確認待ちの教材見直しから学習してください。")
        record = self._load_character(name)
        if record["created"] != job["character_created"] or record["key"] != job["record_key"]:
            raise ValueError("対象が作り直されています。見直しを読み直してください。")
        if record.get("lora_name") != job.get("lora_before"):
            raise ValueError("採用中のLoRAが変わっています。見直しを読み直してください。")
        proposal = Proposal.model_validate(job["proposal"])
        validate_revision(proposal, job["packet"])
        stem = f"{record['key']}_remake_{request_id.replace('-', '')[:8]}"
        panels = self.generated_root / "training" / request_id / f"dataset_{stem}"
        panels.mkdir(parents=True)
        materials = freeze_revised_materials(record, proposal, panels)
        train = {"job_id": str(uuid.uuid4()), "kind": "lora_train", "status": "awaiting_confirmation",
                 "name": name, "record_kind": "character", "record_key": record["key"],
                 "record_created": record["created"], "tool": "train_character_lora",
                 "materials": materials, "trigger": record["trigger"], "steps": steps,
                 "progress": {"step": 0, "total": steps}, "lora_name": f"{stem}.safetensors",
                 "dataset": str(panels), "images": len(materials),
                 "training_selection": {
                     "intent_job_id": request_id, "references": job["packet"]["references"],
                     "image_comments": job["packet"]["image_comments"],
                     "source_comments": job["packet"]["original_comment"],
                     "samples": job["proposal"]["training_samples"],
                 }}
        self.events.save_job(train)
        job.update(status="queued", training_job_id=train["job_id"], lora_name=train["lora_name"], steps=steps)
        self.events.save_job(job)
        with self._job_errors(job):
            trained = await self._train_lora(record, "character", steps, train["job_id"])
            current = self._load_character(name)
            if current.get("lora_name") != job.get("lora_before"):
                raise RuntimeError("作り直し中に採用中のLoRAが変わりました。新版は採用していません。")
            job.update(status="completed", training_job_id=trained["job_id"],
                       lora_name=trained["lora_name"], dataset=trained["dataset"])
            self._store_revision_view(job, record, proposal)
            self.events.save_job(job)
            return job

    def _store_revision_view(self, job: dict, record: dict, proposal: Proposal) -> None:
        before = {item["reference"]["sample_index"]: item for item in selection_rows(record.get("training_selection"))}
        after = {item.reference.sample_index: item.model_dump() for item in proposal.training_samples or []}
        observed = {item.reference.sample_index: item for item in proposal.observations}
        samples = []
        for sample in record["samples"]:
            item = deepcopy(sample)
            item["before_policy"] = before.get(sample["index"])
            item["after_policy"] = after.get(sample["index"])
            item["after_caption"] = observed[sample["index"]].caption_en if sample["index"] in observed else ""
            samples.append(item)
        report = {"status": job["status"], "samples": samples, "ng": job["ng"],
                  "questions": proposal.questions, "changes": [item.model_dump() for item in proposal.changes],
                  "lora_before": job.get("lora_before"), "lora_name": job.get("lora_name")}
        root = self.generated_root / f"material-revision-{job['job_id']}"
        root.mkdir(parents=True, exist_ok=True)
        (root / "report.html").write_text(revision_html(report, CACHE), encoding="utf-8")
        job["report_html"] = str(root / "report.html")
