"""保存済み入力を新しい解釈へ渡す比較。元台帳の変更と学習は行わない。"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx

from backend.intent_runner import interpret
from backend.intent import Proposal, validate_proposal


async def main(args):
    original = json.loads(args.input.read_text())
    job = dict(original)
    args.output.mkdir(parents=True, exist_ok=False)
    with httpx.Client(base_url=args.url, timeout=30) as client:
        images = []
        for index, ref in enumerate(job["references"]):
            response = client.get("/api/file", params={"path": ref["path"]})
            response.raise_for_status()
            images.append(response.content)
            (args.output / f"reference-{index}.png").write_bytes(response.content)
    proposal = await interpret(job, images)
    validate_proposal(Proposal.model_validate(proposal), job)
    (args.output / "result.json").write_text(json.dumps({"proposal": proposal, "interpreter": job["interpreter"]}, ensure_ascii=False, indent=2))
    print(json.dumps({"interpreter": job["interpreter"], "proposal": proposal}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", required=True)
    asyncio.run(main(parser.parse_args()))
