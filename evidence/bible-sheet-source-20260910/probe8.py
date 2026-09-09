"""合格シートを SAM 3.1 で人物一体にして、設定画のパネルを joy_edit で描かせる。

probe4 までは投影（白い谷）でシートを割っていたが、題字・顔アップ・チビ・色見本の位置が生成ごとに
変わるため、人物一体だけを取れなかった。probe7 で SAM3_Detect が人物の全身マスクを 1 個返すことを
確かめたので、マスクの外を白で塗って bbox で切る方式に替える。

確かめるのは二つ:
  1. 参照が人物一体になったか（色見本・隣の人物・題字が入らないか）
  2. 顔アップ・チビ・小物・別衣装・体型図が、頼んだ構図で出るか
顔アップは参照を全身と頭部の二通りで出し、どちらを製品にするか決める。

使い方: uv run python evidence/bible-sheet-source-20260910/probe8.py /tmp/approved_sheet.png
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

from backend import bible, workflows
from backend.comfy import Comfy

OUT = Path(__file__).resolve().parent / "out8"
SEED = 1
# (label, panel_key, 参照の作り方)
CASES = (
    ("turn_back", "turn_back", "figure"),
    ("body_front", "body_front", "figure"),
    ("cos_casual", "cos_casual", "figure"),
    ("chibi_big", "chibi_big", "figure"),
    ("item_head", "item_head", "figure"),
    ("ex_smile-figure", "ex_smile", "figure"),
    ("ex_smile-head", "ex_smile", "head"),
)


def sam_individual(image_name: str, prompt: str) -> dict[str, Any]:
    graph = workflows.sam3_mask(image_name, prompt)
    graph["4"]["inputs"]["individual_masks"] = True
    return graph


async def wait(comfy: Comfy, label: str, graph: dict) -> tuple[list[dict], float]:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe8-{label}")
    while True:
        history = await comfy.history(prompt_id)
        status = history.get("status", {})
        if status.get("completed"):
            break
        if status.get("status_str") == "error":
            raise RuntimeError(json.dumps(status, ensure_ascii=False)[:2000])
        await asyncio.sleep(2)
    images = [image for output in history["outputs"].values() for image in output.get("images", [])]
    return images, round(time.time() - started, 1)


def on_white(sheet: Image.Image, mask: Image.Image) -> Image.Image:
    """マスクの外を白で塗り、その個体の bbox で切る。"""
    box = mask.getbbox()
    white = Image.new("RGB", sheet.size, "white")
    return Image.composite(sheet, white, mask).crop(box)


def head_of(figure: Image.Image, share: float = .34) -> Image.Image:
    head = figure.crop((0, 0, figure.width, max(1, round(figure.height * share))))
    box = bible._ink_mask(head).getbbox()
    return head.crop(box) if box else head


async def main(sheet_path: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comfy = Comfy()
    sheet = Image.open(sheet_path).convert("RGB")
    uploaded = await comfy.upload(sheet_path.read_bytes(), "probe8-sheet.png")

    masks, seconds = await wait(comfy, "sam", sam_individual(uploaded, "girl"))
    report: dict[str, Any] = {"sheet": sheet_path.name, "sheet_size": list(sheet.size),
                              "sam": {"count": len(masks), "seconds": seconds}, "cases": []}
    figures = []
    for index, image in enumerate(masks):
        path = OUT / f"mask{index}.png"
        path.write_bytes(await comfy.view(image))
        mask = Image.open(path).convert("L").point(lambda v: 255 if v > 127 else 0)
        if mask.getbbox():
            figures.append(mask)
    if not figures:
        raise RuntimeError("SAM が人物を見つけませんでした")
    figures.sort(key=lambda m: m.getbbox()[3] - m.getbbox()[1], reverse=True)
    figure = on_white(sheet, figures[0])
    figure.save(OUT / "reference-figure.png", "PNG")
    head = head_of(figure)
    head.save(OUT / "reference-head.png", "PNG")
    report["sam"]["boxes"] = [list(m.getbbox()) for m in figures]
    report["reference"] = {"figure": list(figure.size), "head": list(head.size)}
    print(json.dumps(report["sam"], ensure_ascii=False), flush=True)

    refs = {}
    for name, image in (("figure", figure), ("head", head)):
        refs[name] = await comfy.upload((OUT / f"reference-{name}.png").read_bytes(), f"probe8-{name}.png")

    for label, key, which in CASES:
        panel = next(p for p in bible.PANELS if p.key == key)
        instruction = bible.edit_instruction(panel, panel.tags)
        graph = workflows.joy_edit(refs[which], instruction, SEED,
                                   negative=bible.NEGATIVE, size=bible.size(panel))
        images, seconds = await wait(comfy, label, graph)
        (OUT / f"{label}.png").write_bytes(await comfy.view(images[-1]))
        entry = {"label": label, "panel": key, "reference": which, "seconds": seconds,
                 "size": list(bible.size(panel)), "instruction": instruction}
        report["cases"].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
