"""実画像確認の台帳を隔離cacheへ作る。本番は読取りだけ、学習は呼ばない。"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import quote

import httpx

from backend.app import services


async def main(args):
    if services._character_dir(args.target).exists() or services._style_dir(args.style).exists():
        raise ValueError("試験台帳が既にあります。上書きはしません。")
    async with httpx.AsyncClient(base_url=args.source, timeout=60) as client:
        async def get(endpoint, **params):
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            return response

        original = (await get(f"/api/characters/{quote(args.name)}")).json()
        style = (await get(f"/api/styles/{quote(args.style)}")).json()
        await services.create_character(args.target, original["char_desc"], original.get("attr", ""),
                                        original["trigger"], original["lora_name"])
        for sample in original["samples"]:
            image = await get("/api/file", path=sample["path"])
            path = services.save_upload(image.content, f"reference-{sample['index']}.png")
            await services.add_samples(args.target, str(path), sample.get("caption", ""))
        copied = deepcopy(style)
        copied["samples"] = []
        copied.pop("samples_sheet", None)
        services._save_style(copied)
        for sample in style["samples"]:
            image = await get("/api/file", path=sample["path"])
            path = services.save_upload(image.content, f"style-reference-{sample['index']}.png")
            await services.add_style_samples(args.style, str(path), sample.get("caption", ""))
        proof = {"source": original, "source_style": style, "target": await services.character_info(args.target)}
        (services.characters_root.parent / "generation-probe-source.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2))
        assert original == (await get(f"/api/characters/{quote(args.name)}")).json()
        assert style == (await get(f"/api/styles/{quote(args.style)}")).json()
        print(json.dumps({"name": args.target, "samples": len(original["samples"]),
                          "lora": original["lora_name"], "style_lora": style["lora_name"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--style", required=True)
    asyncio.run(main(parser.parse_args()))
