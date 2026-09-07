"""判定から指示文書を更新し、同じLoRAでプレビューを作り直す。"""
from copy import deepcopy
import hashlib
from pathlib import Path
import uuid

from .identity_instruction import (
    character_negative,
    character_prompt,
    insert_include,
    instruction_parts,
    store_instruction,
    strip_include,
)
from .material_revision import representative_ng
from .preview_intent import IdentityInstructionDraft


class PreviewInstruction:
    async def revise_preview_instruction(self, name: str, job_id: str, request_id: str) -> dict:
        """NGの理由から指示を更新し、同じLoRA・同じseedで10枚を作り直す。重みは焼かない。"""
        source = self._preview_review_source(name, job_id)
        existing = self.events.load_job(request_id)
        if existing:
            if existing.get("kind") != "preview_instruction" or existing.get("source_job_id") != job_id or existing.get("name") != name:
                raise ValueError("別の作り直しに使われた要求IDです。")
            if existing["status"] != "awaiting_answers":
                return existing
        uuid.UUID(request_id)
        view = await self.preview_reviews(name, job_id)
        if view["relearning_unavailable_reason"]:
            raise ValueError(view["relearning_unavailable_reason"])
        selected = [deepcopy(p) for p in view["pictures"] if p["review"]["rating"]]
        ng = [p for p in selected if p["review"]["rating"] == "ng"]
        if not ng:
            raise ValueError("作り直しにはNGの画像が必要です。未判定の画像は使いません。")
        if any(not (p["review"].get("comment") or "").strip() for p in ng):
            raise ValueError("NGの画像には、直したい箇所の理由を書いてください。")
        if existing and [(p["id"], p["review"]["revision"]) for p in selected] == [(p["id"], p["review"]["revision"]) for p in existing["reviews"]]:
            return existing
        record = self._load_character(name)
        history = existing.get("preparation_history", []) + [{k: deepcopy(existing[k]) for k in ("reviews", "questions")}] if existing else []
        job = {"job_id": request_id, "kind": "preview_instruction", "status": "interpreting", "name": name,
               "source_job_id": job_id, "character_created": record["created"], "source": deepcopy(source),
               "reviews": selected, "preparation_history": history,
               "lora_name": source["loras"][0][0]}
        self.events.save_job(job)
        with self._job_errors(job):
            samples = deepcopy(record["samples"])
            for picture in selected:
                content = Path(picture["path"]).read_bytes()
                if hashlib.sha256(content).hexdigest() != picture["sha256"]:
                    raise ValueError("判定した画像の内容が変わっています。新しくプレビューを生成してください。")
                await self._interpret_preview_review(name, source, picture, samples)
                self.events.save_job(job)
            questions = [{"image_id": p["id"], "questions": p["review"]["meaning"]["questions"]}
                         for p in selected if p["review"].get("meaning", {}).get("questions")]
            if questions:
                job.update(status="awaiting_answers", questions=questions)
                self.events.save_job(job)
                return job
            draft = await self._compose_identity_instruction(record, source, selected, samples)
            if draft["questions"]:
                job.update(status="awaiting_answers", questions=[{"image_id": "", "questions": draft["questions"]}],
                           instruction_draft=draft)
                self.events.save_job(job)
                return job
            include, avoid = instruction_parts(draft)
            if not include and not avoid:
                raise ValueError("指摘から次の生成で使う内容を作れませんでした。理由を具体的に書いてください。")
            current = record.get("identity_instruction")
            prior = len(record.get("identity_instruction_history") or [])
            snapshot = {
                "include_en": include,
                "avoid_en": avoid,
                "summary_ja": draft["summary_ja"],
                "lora_name": source["loras"][0][0],
                "revision": prior + (2 if current else 1),
                "source_preview_job_id": job_id,
                "instruction_job_id": request_id,
            }
            preview = self._instruction_preview_job(source, record, snapshot, request_id)
            job["identity_instruction"] = snapshot
            job["preview_job_id"] = preview["job_id"]
            job["status"] = "previewing"
            self.events.save_job(job)
            await self._generate_preview_images(preview)
            snapshot["preview_job_id"] = preview["job_id"]
            preview["identity_instruction"] = deepcopy(snapshot)
            self.events.save_job(preview)
            store_instruction(record, snapshot)
            self._save_character(record)
            job["identity_instruction"] = snapshot
            job["status"] = "completed"
            self.events.save_job(job)
            return job

    def _instruction_preview_job(self, source, record, snapshot, request_id):
        parts = source.get("prompt_parts")
        if parts:
            prompt = character_prompt(parts["trigger"], snapshot, parts.get("style_word", ""),
                                      parts.get("subject", ""), parts.get("content", ""), parts.get("background", ""))
            negative = character_negative(source.get("base_negative") or source["negative"], snapshot)
        else:
            previous = (source.get("identity_instruction") or {}).get("include_en", "")
            stripped = strip_include(source["prompt"], record["trigger"], previous)
            prompt = insert_include(stripped, record["trigger"], snapshot["include_en"])
            negative = character_negative(source.get("base_negative") or source["negative"], snapshot)
        preview = {k: deepcopy(v) for k, v in source.items() if k not in ("created_at", "updated_at")}
        preview.update(job_id=str(uuid.uuid4()), status="queued", pictures=[], total_images=source.get("total_images") or 10,
                       instruction_job_id=request_id, prompt=prompt, negative=negative,
                       identity_instruction=deepcopy(snapshot), loras=deepcopy(source["loras"]), seed=source["seed"])
        preview.pop("learning_job_id", None)
        preview["prompt_parts"] = deepcopy(parts) if parts else {
            "trigger": record["trigger"], "style_word": "", "subject": "", "content": "", "background": ""}
        preview["base_negative"] = source.get("base_negative") or source["negative"]
        return preview

    async def _compose_identity_instruction(self, record, source, selected, samples):
        attached = representative_ng(selected)
        attached_index = {item["id"]: len(samples) + offset for offset, item in enumerate(attached)}
        packet = {"stage": "preview_instruction", "instruction_input": {
            "stage": "preview_instruction",
            "prompt": source["prompt"],
            "negative": source["negative"],
            "previous": {key: (record.get("identity_instruction") or {}).get(key, "")
                         for key in ("include_en", "avoid_en", "summary_ja")},
            "references": [{"kind": "sample", "index": sample["index"], "caption": sample.get("caption", "")}
                           for sample in samples],
            "reviews": [{"id": picture["id"], "rating": picture["review"]["rating"],
                         "comment": picture["review"].get("comment") or "",
                         "meaning": picture["review"].get("meaning"),
                         "attachment_index": attached_index.get(picture["id"])}
                        for picture in selected]}}
        images = [Path(sample["path"]).read_bytes() for sample in samples]
        images.extend(Path(picture["path"]).read_bytes() for picture in attached)
        return IdentityInstructionDraft.model_validate(await self.intent_interpreter(packet, images)).model_dump()
