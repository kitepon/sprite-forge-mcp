"""隔離台帳から実際の解釈入口を一回検証する。画像生成・学習は実行しない。"""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path


async def apply_retained(service, name, native, *, stage="preview"):
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
        job = await service.interpret_comment(IntentRequest(name=name, stage=stage, comment=native["original_comment"]))
        return await service.confirm_comment_intent(job["job_id"], Proposal.model_validate(job["proposal"]))
    finally:
        service.intent_interpreter = original_interpreter


async def main(args):
    args.cache.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(args.cache.resolve())
    from backend.services import Services
    from backend.intent import IntentRequest

    service = Services()
    await service.create_character("解釈検証", args.description)
    for path in args.reference:
        await service.add_samples("解釈検証", str(path.resolve()))
    if args.layout_from:
        from backend.sheet_layout import LayoutProposal, LayoutUpdate, proposed_layout
        retained = LayoutProposal.model_validate(json.loads(args.layout_from.read_text())["proposal"])
        if retained.questions:
            raise ValueError("未解決の質問がある構成案は実験へ適用できません。")
        before = await service.get_sheet_layout("解釈検証")
        await service.save_sheet_layout("解釈検証", LayoutUpdate.model_validate({"expected": before, "panels": proposed_layout(retained)}))
    if args.base_interpretation:
        await apply_retained(service, "解釈検証", json.loads(args.base_interpretation.read_text()))
    job = await service.interpret_comment(IntentRequest(name="解釈検証", stage=args.stage, panel=args.panel, comment=args.comment))
    (args.cache / "interpretation.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(job, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--description", default="she/her")
    parser.add_argument("--stage", choices=("preview", "samples", "training", "sheet", "panel", "drawing", "layout"), default="preview")
    parser.add_argument("--panel", default="")
    parser.add_argument("--base-interpretation", type=Path)
    parser.add_argument("--layout-from", type=Path, help="親が確認した構成解釈のJSON。描画条件だけを隔離台帳へ使う。")
    asyncio.run(main(parser.parse_args()))
