"""SAM 3.1 の閾値を振って、合格シートの人物が個体に分かれるか確かめる。

threshold .5 では 1 体しか出なかった。設定画のパネルへ渡す参照は全身が写った一体だけ欲しいので、
何体か出たうちから背の高い個体を選べるようにしたい。マスクが取れれば bbox で切るだけでなく、
マスクの外を白で塗れるので、隣の人物や色見本が一切入らない参照が作れる。

使い方: uv run python evidence/bible-sheet-source-20260910/probe7.py /tmp/approved_sheet.png
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

OUT = Path(__file__).resolve().parent / "out7"
THRESHOLDS = (.5, .3, .15)


def graph(image_name: str, prompt: str, threshold: float) -> dict[str, Any]:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sam3.1_multiplex_fp16.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "4": {"class_type": "SAM3_Detect", "inputs": {"model": ["1", 0], "image": ["3", 0], "threshold": threshold,
                                                      "refine_iterations": 2, "individual_masks": True,
                                                      "conditioning": ["2", 0]}},
        "5": {"class_type": "MaskToImage", "inputs": {"mask": ["4", 0]}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "sprite-forge/probe7"}},
    }


async def run(comfy: Comfy, label: str, prompt_graph: dict) -> list[dict]:
    started = time.time()
    prompt_id = await comfy.submit(prompt_graph, f"probe7-{label}")
    while True:
        history = await comfy.history(prompt_id)
        status = history.get("status", {})
        if status.get("completed"):
            break
        if status.get("status_str") == "error":
            raise RuntimeError(json.dumps(status, ensure_ascii=False)[:2000])
        await asyncio.sleep(2)
    images = [image for output in history["outputs"].values() for image in output.get("images", [])]
    print(f"{label}: {len(images)} masks in {time.time() - started:.1f}s", flush=True)
    return images


def reference(sheet: Image.Image, mask: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """マスクの外を白で塗り、その個体の bbox で切る。隣の人物も色見本も入らない。"""
    white = Image.new("RGB", sheet.size, "white")
    return Image.composite(sheet, white, mask).crop(box)


async def main(sheet_path: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comfy = Comfy()
    sheet = Image.open(sheet_path).convert("RGB")
    uploaded = await comfy.upload(sheet_path.read_bytes(), "probe7-sheet.png")
    report: dict[str, Any] = {"sheet": sheet_path.name, "size": list(sheet.size), "runs": []}
    for threshold in THRESHOLDS:
        label = f"t{threshold}"
        masks = []
        for index, image in enumerate(await run(comfy, label, graph(uploaded, "girl", threshold))):
            mask = Image.open(await save(comfy, image, OUT / f"{label}-mask{index}.png")).convert("L")
            mask = mask.point(lambda v: 255 if v > 127 else 0)
            box = mask.getbbox()
            if box:
                masks.append((mask, box))
        masks.sort(key=lambda pair: pair[1][3] - pair[1][1], reverse=True)
        for index, (mask, box) in enumerate(masks):
            reference(sheet, mask, box).save(OUT / f"{label}-figure{index}.png", "PNG")
        entry = {"threshold": threshold, "count": len(masks),
                 "boxes": [[*box, box[2] - box[0], box[3] - box[1]] for _, box in masks]}
        report["runs"].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


async def save(comfy: Comfy, image: dict, path: Path) -> Path:
    path.write_bytes(await comfy.view(image))
    return path


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
