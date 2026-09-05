"""親が画像と照合した隔離解釈を確認し、GPUを呼ばずパネル条件を解決する。"""
import argparse
import asyncio
import json
from pathlib import Path

from backend import bible
from backend.events import EventStore
from backend.intent import Proposal
from backend.panel_intent import resolve_panel
from backend.services import Services


async def main(root):
    native = json.loads((root / "interpretation.json").read_text())
    service = Services(events=EventStore(root / "events.ndjson", root / "jobs"),
                       characters_root=root / "characters", styles_root=root / "styles",
                       uploads_root=root / "uploads", generated_root=root / "generated")
    if native["proposal"]["questions"]:
        result = {"state": "needs_confirmation", "questions": native["proposal"]["questions"], "requests": []}
    else:
        job = service.events.load_job(native["job_id"])
        if job["status"] == "awaiting_confirmation":
            job = await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(native["proposal"]))
        record = await service.character_info(native["name"])
        intent = service._generation_intent(record, "character", job["stage"], job["job_id"], job["panel"])
        requests = [{"panel": p.key, "label": p.label, "section": p.section,
                     **resolve_panel(p, record["trigger"], record["char_desc"], intent["intent_conditions"],
                                     intent["intent_changes"], record.get("panel_overrides", {}).get(p.key, {}), job["job_id"])}
                    for p in bible.PANELS if not job["panel"] or p.key == job["panel"]]
        result = {"state": "resolved_without_gpu", "record_description": record["char_desc"],
                  "common_conditions": record.get("intent_conditions", {}), "requests": requests}
        # 生成成功後にだけ保存するpanel案がないケースでは、解釈ID省略時も実測する。
        if not any(c["scope"] == "panel" for c in job["accepted"]["changes"]):
            repeated = service._generation_intent(record, "character", job["stage"])
            result["without_order"] = [{"panel": p.key,
                **resolve_panel(p, record["trigger"], record["char_desc"], repeated["intent_conditions"], [],
                                record.get("panel_overrides", {}).get(p.key, {}))}
                for p in bible.PANELS if not job["panel"] or p.key == job["panel"]]
    (root / "resolved.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"state": result["state"], "panels": len(result["requests"])}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    asyncio.run(main(parser.parse_args().cache.resolve()))
