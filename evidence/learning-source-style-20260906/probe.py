"""本番を読み取り、独立した台帳で画像解釈・実機学習を検証する。"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx

from backend.events import EventStore
from backend.intent import IntentRequest, Proposal
from backend.services import Services


async def run(args):
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    service = Services(events=EventStore(root / "events.ndjson", root / "jobs"),
                       generated_root=root / "generated", uploads_root=root / "uploads",
                       characters_root=root / "characters", styles_root=root / "styles")
    pointer = root / "probe.json"
    if args.action == "interpret":
        async with httpx.AsyncClient(base_url=args.url, timeout=60) as client:
            response = await client.get(f"/api/characters/{args.name}"); response.raise_for_status()
            original = response.json()
            response = await client.get("/api/intents", params={"name": args.name, "kind": "character"}); response.raise_for_status()
            history = response.json()
            name = "素材学習検証"
            await service.create_character(name, original["char_desc"], trigger=original["trigger"])
            for sample in original["samples"]:
                response = await client.get("/api/file", params={"path": sample["path"]}); response.raise_for_status()
                source = service.save_upload(response.content)
                await service.add_samples(name, str(source), sample.get("caption", ""))
            for stage in ("samples", "training"):
                comment = next((j["original_comment"] for j in history if j["stage"] == stage and "learning_steps" not in j), "")
                await service.save_comment(IntentRequest(name=name, stage=stage, comment=comment))
        job = await service.start_learning(name, steps=args.steps)
        pointer.write_text(json.dumps({"name": name, "job_id": job["job_id"]}, ensure_ascii=False))
        print(json.dumps({"status": job["status"], "interpreter": job.get("interpreter"),
                          "proposal": job["proposal"]}, ensure_ascii=False, indent=2))
    else:
        state = json.loads(pointer.read_text())
        job = service.events.load_job(state["job_id"])
        if args.action == "train":
            await service.confirm_learning(job["job_id"], Proposal.model_validate(job["proposal"]))
            job = service.events.load_job(job["job_id"])
            trained = service.events.load_job(job["training_job_id"])
            print(json.dumps({k: trained[k] for k in ("job_id", "status", "images", "steps", "lora_name", "log_path")}, ensure_ascii=False))
        elif args.action == "preview":
            result = await service.preview_character(state["name"], seed=42)
            print(json.dumps(result, ensure_ascii=False))
    await service.comfy.client.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("interpret", "train", "preview"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--url", default="http://192.168.1.2:8766")
    parser.add_argument("--name", default="ベル")
    parser.add_argument("--steps", type=int, default=1200)
    asyncio.run(run(parser.parse_args()))
