"""見直し済み元教材に、本人OKの生成6枚を足してAnima Baseから学習する。採用中LoRAは置き換えない。"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend.events import EventStore
from backend.intent import Proposal
from backend.material_revision import freeze_revised_materials
from backend.services import Services
from ok_materials import USER_OK, add_ok_materials, ok_source


async def main(args):
    root = args.output.resolve()
    for role, seed in USER_OK:
        path = ok_source(root, role, seed)
        if not path.is_file():
            raise SystemExit(f"本人OKの画像がありません: {path}")
    service = Services(events=EventStore(root / "events.ndjson", root / "jobs"),
                       generated_root=root / "generated", uploads_root=root / "uploads",
                       characters_root=root / "characters", styles_root=root / "styles")
    record = service._load_character(args.name)
    adopted = record.get("lora_name")
    revision = service.events.load_job(args.revision_id)
    if not revision or revision.get("kind") != "material_revision":
        raise SystemExit("教材見直しがありません。")
    proposal = Proposal.model_validate(revision["proposal"])
    request_id = args.request_id or str(uuid.uuid4())
    stem = f"{record['key']}_ok_{request_id.replace('-', '')[:8]}"
    panels = service.generated_root / "training" / request_id / f"dataset_{stem}"
    if panels.exists():
        raise SystemExit("同じ学習先が残っています。新しい要求IDを指定してください。")
    panels.mkdir(parents=True)
    materials = freeze_revised_materials(record, proposal, panels)
    materials.extend(add_ok_materials(record, panels, root))
    train = {"job_id": str(uuid.uuid4()), "kind": "lora_train", "status": "awaiting_confirmation",
             "name": record["name"], "record_kind": "character", "record_key": record["key"],
             "record_created": record["created"], "tool": "train_character_lora",
             "materials": materials, "trigger": record["trigger"], "steps": args.steps,
             "progress": {"step": 0, "total": args.steps}, "lora_name": f"{stem}.safetensors",
             "dataset": str(panels), "images": len(materials),
             "ok_seeds": [seed for _, seed in USER_OK],
             "source_revision": args.revision_id,
             "training_selection": {
                 "intent_job_id": args.revision_id,
                 "references": revision["packet"]["references"],
                 "image_comments": revision["packet"]["image_comments"],
                 "source_comments": revision["packet"]["original_comment"],
                 "samples": revision["proposal"]["training_samples"],
             }}
    service.events.save_job(train)
    trained = await service._train_lora(record, "character", args.steps, train["job_id"])
    current = service._load_character(args.name)
    if current.get("lora_name") != adopted:
        raise RuntimeError("作り直し中に採用中のLoRAが変わりました。新版は採用していません。")
    result = {"request_id": request_id, "training_job_id": trained["job_id"], "status": trained["status"],
              "lora_name": trained["lora_name"], "adopted_lora": current.get("lora_name"),
              "images": len(materials), "ok": len(USER_OK), "dataset": trained["dataset"]}
    (root / "ok-train.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--steps", type=int, default=1200)
    asyncio.run(main(parser.parse_args()))
