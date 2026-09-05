"""隔離台帳から実際の解釈入口を一回検証する。画像生成・学習は実行しない。"""
import argparse
import asyncio
import json
import os
from pathlib import Path


async def main(args):
    args.cache.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(args.cache.resolve())
    from backend.services import Services
    from backend.intent import IntentRequest

    service = Services()
    await service.create_character("解釈検証", "she/her")
    for path in args.reference:
        await service.add_samples("解釈検証", str(path.resolve()))
    job = await service.interpret_comment(IntentRequest(name="解釈検証", stage="preview", comment=args.comment))
    print(json.dumps(job, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--comment", required=True)
    asyncio.run(main(parser.parse_args()))
