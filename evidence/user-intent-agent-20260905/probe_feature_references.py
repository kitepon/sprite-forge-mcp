"""画像別コメントによる特徴の参照先を実CLIで確認する。学習はしない。"""
import asyncio
import json
from pathlib import Path
import sys

from backend.intent import Proposal, validate_proposal
from backend.intent_runner import interpret


async def main():
    root = Path(__file__).parent / "private"
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    refs = [{"record_key": "probe", "sample_index": i, "path": f"/probe/{i}.png"} for i in range(4)]
    job = {"original_comment": "", "record_description": "人物", "existing_settings": {},
           "references": refs, "image_comments": ["", "この画像の顔立ちを強く採用してほしい", "",
           "この画像の体格・頭身と服装を強く採用してほしい"],
           "base_conditions": {}, "stage_conditions": {}, "stage": "samples", "panel": "",
           "record_kind": "character", "training_captions": [None] * 4, "available_styles": []}
    images = [(root / f"lora-identity-v2/dataset_ndac1de01/{i:03d}.png").read_bytes() for i in range(4)]
    result = await interpret(job, images)
    validate_proposal(Proposal.model_validate(result), job)
    (output / "result.json").write_text(json.dumps({"job": job, "proposal": result}, ensure_ascii=False, indent=2))
    print(json.dumps({"interpreter": job["interpreter"], "changes": result["changes"], "questions": result["questions"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
