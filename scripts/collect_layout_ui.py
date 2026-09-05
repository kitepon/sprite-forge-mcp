"""隔離UIで生成した記録を、GPU履歴と本番の前後比較で照合する。"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx


async def main(args):
    os.environ["SPRITEFORGE_CACHE"] = str(args.cache.resolve())
    from backend import bible, workflows
    from backend.comfy import Comfy
    from backend.sheet_layout import panel_from

    def load(path):
        return json.loads(path.read_text())

    job = load(args.cache / "jobs" / f"{args.job_id}.json")
    prepared = load(args.cache / "prepared.json")
    accepted = load(args.cache / "jobs" / f"{prepared['job_id']}.json")
    original = load(args.cache / "source-record.json")
    assert job["status"] == "completed" and accepted["status"] == "confirmed"
    assert accepted["accepted"] == prepared["proposal"]
    assert accepted["confirmed_layout"] == job["layout"]
    assert job["completed_panels"] == job["total_panels"] == len(job["layout"])
    comfy = Comfy()
    try:
        response = await comfy.client.get(f"{comfy.base_url}/history")
        response.raise_for_status()
        history = {key: value for key, value in response.json().items()
                   if value["prompt"][3].get("client_id") == args.job_id}
        assert len(history) == len(job["layout"])
        results = []
        for panel, request, path in zip(job["layout"], job["panel_requests"], job["panels"], strict=True):
            width, height = bible.size(panel_from(panel))
            expected = workflows.anima_txt2img(request["prompt"], request["seed"], loras=job["loras"],
                                                negative=request["negative"], width=width, height=height)
            matches = [(key, value) for key, value in history.items() if value["prompt"][2] == expected]
            assert len(matches) == 1, f"実グラフと一致しません: {panel['key']}"
            prompt_id, actual = matches[0]
            assert actual["status"]["completed"]
            image = actual["outputs"]["25"]["images"][0]
            response = await comfy.client.get(f"{comfy.base_url}/view", params=image)
            response.raise_for_status()
            saved = Path(path).read_bytes()
            assert bible.crop_nonwhite(response.content) == saved
            results.append({"panel": panel["key"], "prompt_id": prompt_id,
                            "image_sha256": hashlib.sha256(saved).hexdigest()})
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{args.source}/api/characters/{quote(job['name'])}")
            response.raise_for_status()
            after = response.json()
        (args.cache / "source-record-after.json").write_text(json.dumps(after, ensure_ascii=False, indent=2))
        assert original == after, "本番台帳が前回の読取りから変わっています。"
        for filename, value in (("gpu-history.json", history), ("gpu-info.json", await comfy.stats()),
                                ("verification.json", {"job_id": args.job_id, "panels": results, "production_unchanged": True})):
            (args.cache / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2))
        print(json.dumps({"panels_verified": len(results), "production_unchanged": True}, ensure_ascii=False))
    finally:
        await comfy.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--source", required=True)
    asyncio.run(main(parser.parse_args()))
