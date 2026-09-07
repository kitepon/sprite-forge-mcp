"""確認待ちの教材見直しから、Anima Base で新しい LoRA を学習する。採用中の LoRA は置き換えない。"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.config import CACHE
from backend.events import EventStore
from backend.intent import Proposal
from backend.services import Services
from probe_remake import save_public


async def main(args):
    root = args.output.resolve()
    service = Services(events=EventStore(root / "events.ndjson", root / "jobs"),
                       generated_root=root / "generated", uploads_root=root / "uploads",
                       characters_root=root / "characters", styles_root=root / "styles")
    if args.publish_only:
        job = service.events.load_job(args.request_id)
        if not job:
            raise SystemExit("見直しジョブがありません。")
        record = service._load_character(args.name)
        service._store_revision_view(job, record, Proposal.model_validate(job["proposal"]))
        service.events.save_job(job)
        save_public(root, job, CACHE)
        print(json.dumps({"status": job["status"], "report": str(root / "report.html")}, ensure_ascii=False))
        return
    job = await service.remake_lora_from_revision(args.name, args.request_id, steps=args.steps)
    save_public(root, job, CACHE)
    record = service._load_character(args.name)
    print(json.dumps({
        "request_id": args.request_id,
        "status": job["status"],
        "lora_before": job.get("lora_before"),
        "lora_name": job.get("lora_name"),
        "adopted_lora": record.get("lora_name"),
        "training_job_id": job.get("training_job_id"),
        "questions": job.get("questions") or [],
        "proposal_priorities": [
            {"index": item.reference.sample_index, "priority": item.priority, "features": item.features}
            for item in Proposal.model_validate(job["proposal"]).training_samples or []
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--publish-only", action="store_true")
    asyncio.run(main(parser.parse_args()))
