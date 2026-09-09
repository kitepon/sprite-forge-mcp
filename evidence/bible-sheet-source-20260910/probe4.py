"""合格シートの一体切り出しを参照に、設定画の残り 5 種類のパネルが描けるかを fox で実測する。

probe3 で「向きの違う全身」は描けた。設定画には他に、顔アップ・チビ・別衣装・小物（人物なし）・
レオタードの体型参照がある。参照の構図が出力へ写る性質は、これらでは不利にも働く——顔だけを
求めているのに全身が出る、別衣装を求めているのに元の衣装が残る、といった失敗があり得る。
製品コードの `bible.figure_crop` と `bible.edit_instruction` をそのまま使い、実物で確かめる。

使い方: uv run python evidence/bible-sheet-source-20260910/probe4.py <sheet.png>
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from backend import bible
from backend.comfy import Comfy

OUT = Path(__file__).resolve().parent / "out4"
SEED = 1
PANELS = ("ex_smile", "chibi_big", "cos_armor", "item_head", "body_front")


async def run(comfy: Comfy, label: str, graph: dict) -> dict:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe4-{label}")
    while True:
        history = await comfy.history(prompt_id)
        status = history.get("status", {})
        if status.get("completed"):
            break
        if status.get("status_str") == "error":
            return {"label": label, "error": json.dumps(status, ensure_ascii=False)[:1500]}
        await asyncio.sleep(3)
    images = [image for output in history["outputs"].values() for image in output.get("images", [])]
    content = await comfy.view(images[-1])
    (OUT / f"{label}.png").write_bytes(content)
    return {"label": label, "seconds": round(time.time() - started, 1), "bytes": len(content)}


async def main(sheet_path: Path) -> None:
    from backend import workflows

    OUT.mkdir(parents=True, exist_ok=True)
    figure = bible.figure_crop(sheet_path)
    crop_path = OUT / "reference-figure.png"
    figure.save(crop_path, "PNG")
    print("figure crop:", figure.size, flush=True)

    comfy = Comfy()
    reference = await comfy.upload(crop_path.read_bytes(), "probe4-figure.png")
    print("uploaded:", reference, flush=True)
    report = []
    for key in PANELS:
        panel = next(p for p in bible.PANELS if p.key == key)
        instruction = bible.edit_instruction(panel, panel.tags)
        width, height = bible.size(panel)
        graph = workflows.joy_edit(reference, instruction, SEED,
                                   negative=bible.NEGATIVE, size=(width, height))
        result = await run(comfy, key, graph)
        result["instruction"] = instruction
        print(json.dumps(result, ensure_ascii=False), flush=True)
        report.append(result)
    (OUT / "report.json").write_text(json.dumps(
        {"sheet": sheet_path.name, "figure_crop": list(figure.size), "seed": SEED,
         "negative": bible.NEGATIVE, "results": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
