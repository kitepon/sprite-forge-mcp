"""実エージェントの保存済み構成案を、UI確定前の隔離台帳へ用意する。"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx


async def prepare(service, original, native, references):
    """元応答を変更せず、同じ画像順の参照を隔離台帳へ結び直す。"""
    from backend.intent import IntentRequest
    from backend.sheet_layout import LayoutProposal, LayoutUpdate, validate_layout_proposal

    if native["stage"] != "layout" or native["proposal"]["questions"]:
        raise ValueError("質問のない、確認済みの実構成案を指定してください。")
    if len(references) != len(native["references"]):
        raise ValueError("元応答と同じ順序・枚数の参考画像が必要です。")
    if not original.get("lora_name"):
        raise ValueError("学習済みLoRAを持つ比較元が必要です。")
    name = original["name"]
    await service.create_character(name, native["record_description"], original.get("attr", ""),
                                   original["trigger"], original["lora_name"])
    for reference in references:
        await service.add_samples(name, str(reference))
    before = await service.get_sheet_layout(name)
    await service.save_sheet_layout(name, LayoutUpdate.model_validate({"expected": before, "panels": native["sheet_layout"]}))
    job = await service.save_comment(IntentRequest(name=name, stage="layout", comment=native["original_comment"]))
    refs = {ref["sample_index"]: job["references"][i] for i, ref in enumerate(native["references"])}
    proposal = deepcopy(native["proposal"])
    for panel in proposal["panels"]:
        if panel["reference"] is not None:
            panel["reference"] = refs[panel["reference"]["sample_index"]]
    validate_layout_proposal(LayoutProposal.model_validate(proposal), job)
    job.update(status="awaiting_confirmation", proposal=proposal, interpreter=deepcopy(native["interpreter"]),
               probe_replay={"source_job_id": native["job_id"], "mode": "retained_response"})
    service.events.save_job(job)
    return job


async def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(args.output.resolve())
    from backend.services import Services

    native_bytes = args.interpretation.read_bytes()
    native = json.loads(native_bytes)
    references = [args.reference_dir / Path(ref["path"]).name for ref in native["references"]]
    service = Services()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{args.source}/api/characters/{quote(args.name)}")
            response.raise_for_status()
            original = response.json()
        if original.get("style"):
            raise ValueError("この比較入口は画風を重ねていないキャラクターを対象にしています。")
        job = await prepare(service, original, native, references)
        for filename, data in (("source-record.json", original), ("prepared.json", job),
                               ("source-response.json", native)):
            (args.output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        proof = {"source_response_sha256": hashlib.sha256(native_bytes).hexdigest(),
                 "reference_sha256": [hashlib.sha256(path.read_bytes()).hexdigest() for path in references],
                 "job_id": job["job_id"], "state": "awaiting_confirmation", "gpu_executed": False}
        (args.output / "preparation.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2))
        print(json.dumps(proof, ensure_ascii=False), flush=True)
    finally:
        await service.comfy.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interpretation", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--name", required=True)
    asyncio.run(main(parser.parse_args()))
