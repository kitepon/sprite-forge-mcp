"""合格シートの人物一体を SAM 3.1 で切り出せるか確かめる。

投影（行・列の白い谷）で割る方式は、このシートで破れた。題字・顔アップ・チビ・色見本の位置が
生成ごとに変わるうえ、背面図の列に色見本が同居するため、列を割っても人物だけにならない。
SAM3_Detect は個体ごとのマスクを返すので、いちばん背の高い個体を選べば推測が要らない。

確かめるのは三つ: 個体が分かれるか、いちばん背の高い個体が人物一体か、その切り出しを
joy_edit へ渡すと求めた構図のパネルが出るか。

使い方: uv run python evidence/bible-sheet-source-20260910/probe6.py /tmp/approved_sheet.png
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

from backend.comfy import Comfy

OUT = Path(__file__).resolve().parent / "out6"


def sam3_individual(image_name: str, prompt: str) -> dict[str, Any]:
    """`workflows.sam3_mask` の個体版。個体ごとのマスクを画像として全部保存する。"""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sam3.1_multiplex_fp16.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "4": {"class_type": "SAM3_Detect", "inputs": {"model": ["1", 0], "image": ["3", 0], "threshold": .5,
                                                      "refine_iterations": 2, "individual_masks": True,
                                                      "conditioning": ["2", 0]}},
        "5": {"class_type": "MaskToImage", "inputs": {"mask": ["4", 0]}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "sprite-forge/probe6-mask"}},
    }


async def run(comfy: Comfy, label: str, graph: dict) -> list[dict]:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe6-{label}")
    while True:
        history = await comfy.history(prompt_id)
        status = history.get("status", {})
        if status.get("completed"):
            break
        if status.get("status_str") == "error":
            raise RuntimeError(json.dumps(status, ensure_ascii=False)[:2000])
        await asyncio.sleep(2)
    images = [image for output in history["outputs"].values() for image in output.get("images", [])]
    print(f"{label}: {len(images)} images in {time.time() - started:.1f}s", flush=True)
    return images


async def main(sheet_path: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comfy = Comfy()
    sheet = Image.open(sheet_path).convert("RGB")
    uploaded = await comfy.upload(sheet_path.read_bytes(), "probe6-sheet.png")
    report: dict[str, Any] = {"sheet": sheet_path.name, "size": list(sheet.size), "prompts": {}}
    for prompt in ("girl", "person", "character"):
        images = await run(comfy, prompt, sam3_individual(uploaded, prompt))
        boxes = []
        for index, image in enumerate(images):
            mask_path = OUT / f"{prompt}-{index}.png"
            mask_path.write_bytes(await comfy.view(image))
            box = Image.open(mask_path).convert("L").point(lambda v: 255 if v > 127 else 0).getbbox()
            boxes.append(box)
        report["prompts"][prompt] = {"count": len(images), "boxes": [list(b) if b else None for b in boxes]}
        solid = [b for b in boxes if b]
        if solid:
            tallest = max(solid, key=lambda b: b[3] - b[1])
            sheet.crop(tallest).save(OUT / f"{prompt}-tallest-crop.png", "PNG")
            report["prompts"][prompt]["tallest"] = list(tallest)
        print(json.dumps(report["prompts"][prompt], ensure_ascii=False), flush=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
