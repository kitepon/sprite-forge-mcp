"""SAM 3.1 に人物一体を見つけさせる対象語を選ぶ。

probe7・probe8 では "girl" で測ったが、製品は性別も人外かどうかも決め打ちできない。台帳から作れる語
（"character"・"person"）で同じ結果になるかを確かめ、ならなければ台帳の被写体語を使う必要がある。

見るのは、返ったマスクの数、最も背の高いマスクの外接矩形、切り出した参照画像。

使い方: uv run python evidence/bible-sheet-source-20260910/probe11.py /tmp/approved_sheet.png
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from PIL import Image

from backend import workflows
from backend.comfy import Comfy

OUT = Path(__file__).resolve().parent / "out11"
PROMPTS = ("character", "person", "girl")


async def masks_for(comfy: Comfy, uploaded: str, prompt: str) -> tuple[list[bytes], float]:
    graph = workflows.sam3_mask(uploaded, prompt)
    graph["4"]["inputs"]["individual_masks"] = True
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe11-{prompt}")
    while True:
        history = await comfy.history(prompt_id)
        status = history.get("status", {})
        if status.get("completed"):
            break
        if status.get("status_str") == "error":
            raise RuntimeError(json.dumps(status, ensure_ascii=False)[:2000])
        await asyncio.sleep(2)
    images = [image for output in history["outputs"].values() for image in output.get("images", [])]
    return [await comfy.view(image) for image in images], round(time.time() - started, 1)


async def main(sheet_path: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comfy = Comfy()
    sheet = Image.open(sheet_path).convert("RGB")
    uploaded = await comfy.upload(sheet_path.read_bytes(), "probe11-sheet.png")
    report = {"sheet": sheet_path.name, "sheet_size": list(sheet.size), "prompts": []}
    for prompt in PROMPTS:
        contents, seconds = await masks_for(comfy, uploaded, prompt)
        boxes = []
        for index, content in enumerate(contents):
            path = OUT / f"{prompt}-mask{index}.png"
            path.write_bytes(content)
            mask = Image.open(path).convert("L").point(lambda v: 255 if v > 127 else 0)
            if mask.getbbox():
                boxes.append((mask, mask.getbbox()))
        entry = {"prompt": prompt, "seconds": seconds, "masks": len(contents),
                 "boxes": [list(box) for _, box in boxes]}
        if boxes:
            mask, box = max(boxes, key=lambda pair: pair[1][3] - pair[1][1])
            white = Image.new("RGB", sheet.size, "white")
            Image.composite(sheet, white, mask).crop(box).save(OUT / f"{prompt}-figure.png", "PNG")
            entry["tallest"] = list(box)
        report["prompts"].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
