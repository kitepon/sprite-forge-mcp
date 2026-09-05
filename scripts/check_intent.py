"""隔離台帳から実際の解釈入口を一回検証する。画像生成・学習は実行しない。"""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path


async def apply_retained(service, name, native):
    """親が確認済みの既存応答を、同じ画像順の隔離台帳へ適用する。"""
    from backend.intent import IntentRequest, Proposal

    async def retained(job, images):
        proposal = deepcopy(native["proposal"])
        references = {ref["sample_index"]: job["references"][i]
                      for i, ref in enumerate(native["references"])}
        for item in [*proposal["observations"], *proposal["changes"]]:
            if item["reference"] is not None:
                item["reference"] = references[item["reference"]["sample_index"]]
        job["interpreter"] = native["interpreter"]
        return proposal

    original_interpreter = service.intent_interpreter
    service.intent_interpreter = retained
    try:
        job = await service.interpret_comment(IntentRequest(name=name, stage="preview", comment=native["original_comment"]))
        return await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(job["proposal"]))
    finally:
        service.intent_interpreter = original_interpreter


async def main(args):
    args.cache.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(args.cache.resolve())
    from backend.services import Services
    from backend.intent import IntentRequest

    service = Services()
    await service.create_character("解釈検証", "she/her")
    for path in args.reference:
        await service.add_samples("解釈検証", str(path.resolve()))
    if args.base_interpretation:
        await apply_retained(service, "解釈検証", json.loads(args.base_interpretation.read_text()))
    job = await service.interpret_comment(IntentRequest(name="解釈検証", stage="preview", comment=args.comment))
    (args.cache / "interpretation.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(job, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--base-interpretation", type=Path)
    asyncio.run(main(parser.parse_args()))
