"""本人のNGだけをプレビュー判定へ載せ、教材見直し案を作る。研究用指摘は混ぜない。"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.events import EventStore
from backend.config import CACHE
from backend.material_revision import revision_html
from backend.preview_intent import ReviewMeaning
from backend.preview_reviews import PreviewReview
from backend.services import Services


OWNER = "本人のNG"


def owner_reviews(compiled):
    meanings = {item["id"]: item["meaning"] for item in compiled["results"]}
    selected = []
    for case in compiled["cases"]:
        if case["origin"] != OWNER:
            continue
        meaning = meanings[case["id"]]
        questions = [meaning["question_ja"]] if meaning.get("question_ja") else []
        fix = [meaning["observed_ng_ja"]] if meaning.get("observed_ng_ja") else []
        selected.append({
            "number": case["number"], "id": f"candidate-{case['number']:02}",
            "comment": case["comment"],
            "meaning": {"fix": fix, "preserve": meaning.get("preserve_ja") or [], "questions": questions},
        })
    if not selected:
        raise ValueError("本人のNGがありません。")
    return selected


def remap_selection(selection, record):
    if not selection:
        return None
    copied = json.loads(json.dumps(selection))
    by_index = {sample["index"]: sample for sample in record["samples"]}
    for item in copied.get("samples") or []:
        sample = by_index[item["reference"]["sample_index"]]
        item["reference"] = {"record_key": record["key"], "sample_index": sample["index"], "path": sample["path"]}
    copied["references"] = [{"record_key": record["key"], "sample_index": sample["index"], "path": sample["path"]}
                            for sample in record["samples"]]
    return copied


async def import_character(service, source, samples_dir):
    original = json.loads(source.read_text())
    await service.create_character(original["name"], original["char_desc"], trigger=original["trigger"])
    for sample in original["samples"]:
        path = samples_dir / Path(sample["path"]).name
        await service.add_samples(original["name"], str(path), sample.get("caption") or "")
    record = service._load_character(original["name"])
    for sample, prior in zip(record["samples"], original["samples"]):
        sample["caption"] = prior.get("caption") or ""
        if prior.get("training_caption"):
            sample["training_caption"] = prior["training_caption"]
    record["training_selection"] = remap_selection(original.get("training_selection"), record)
    record["intent_conditions"] = original.get("intent_conditions") or {}
    record["lora_name"] = original.get("lora_name") or ""
    return service._save_character(record)


async def import_preview(service, record, pictures, prompt, negative, lora_name, reviews):
    job_id = str(uuid.uuid4())
    imported = []
    for picture in pictures:
        content = Path(picture["path"]).read_bytes()
        path = service._write_generated(f"{picture['id']}.png", content)
        imported.append({**picture, "path": str(path), "sha256": hashlib.sha256(content).hexdigest()})
    job = {"job_id": job_id, "kind": "preview", "status": "completed", "name": record["name"],
           "prompt": prompt, "negative": negative, "loras": [[lora_name, 0.8]],
           "pictures": imported, "character_created": record["created"],
           "created_at": record["created"],
           "generation": {"model": "anima-base-v1.0.safetensors", "text_encoder": "qwen_3_06b_base.safetensors",
                          "vae": "qwen_image_vae.safetensors", "width": 832, "height": 1216, "turbo": False,
                          "steps": 8, "cfg": 4, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}}
    service.events.save_job(job)
    for review in reviews:
        saved = await service.save_preview_review(
            record["name"], job_id, review["id"],
            PreviewReview(rating="ng", revision=0, comment=review["comment"]))
        saved["meaning"] = ReviewMeaning.model_validate(review["meaning"]).model_dump()
        saved["meaning_source"] = "inherited"
        service._store_review_meaning(record["name"], job_id, review["id"], saved)
    return job


def save_public(root, job, cache):
    root.mkdir(parents=True, exist_ok=True)
    (root / "report.json").write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html = Path(job["report_html"]).read_text(encoding="utf-8") if job.get("report_html") else revision_html(
        {"status": job.get("status"), "samples": job.get("samples") or [], "ng": job.get("ng") or [],
         "questions": job.get("questions") or [], "changes": (job.get("proposal") or {}).get("changes") or []},
        cache)
    (root / "report.html").write_text(html, encoding="utf-8")


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in ("characters", "styles", "jobs", "generated", "uploads"):
        path = root / name
        if path.exists():
            shutil.rmtree(path)
    (root / "events.ndjson").unlink(missing_ok=True)
    compiled = json.loads(args.compiled.read_text())
    reviews = owner_reviews(compiled)
    service = Services(events=EventStore(root / "events.ndjson", root / "jobs"),
                       generated_root=root / "generated", uploads_root=root / "uploads",
                       characters_root=root / "characters", styles_root=root / "styles")
    record = await import_character(service, args.character, args.samples)
    baseline = json.loads(args.baseline.read_text())["input"]
    pictures = []
    for review in reviews:
        pictures.append({"id": review["id"], "number": review["number"],
                         "path": str(args.images / f"candidate-{review['number']:02}.png"),
                         "seed": 500 + review["number"]})
    preview = await import_preview(service, record, pictures, baseline["prompt"], baseline["negative"],
                                   Path(baseline["lora"]).name, reviews)
    request_id = args.request_id or str(uuid.uuid4())
    job = await service.propose_material_revision(record["name"], preview["job_id"], request_id)
    save_public(root, job, CACHE)
    print(json.dumps({"request_id": request_id, "preview_job_id": preview["job_id"],
                      "status": job["status"], "questions": job.get("questions") or [],
                      "ng": len(job["ng"]), "lora_before": job.get("lora_before")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--character", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--request-id")
    asyncio.run(main(parser.parse_args()))
