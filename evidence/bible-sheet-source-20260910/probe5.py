"""直した `bible.figure_crop` と新しい `bible.reference_crop` を実物で確かめる。

probe4 では切り出しに色見本の帯と隣の人物の裾が入り、顔アップを頼んでも全身が出た。
切り出しを「行の帯 → 列」の順に割る方式へ直し、顔のパネルには人物の上部だけを渡すようにした。
確かめるのは二つ: 切り出しが人物一体だけになったか、顔・チビ・小物のパネルが求めた構図で出るか。

使い方: uv run python evidence/bible-sheet-source-20260910/probe5.py <sheet.png>
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from backend import bible
from backend.comfy import Comfy

OUT = Path(__file__).resolve().parent / "out5"
SEED = 1
PANELS = ("ex_smile", "chibi_big", "item_head", "turn_back")


async def run(comfy: Comfy, label: str, graph: dict) -> dict:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe5-{label}")
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
    return {"label": label, "seconds": round(time.time() - started, 1)}


async def main(sheet_path: Path) -> None:
    from backend import workflows

    OUT.mkdir(parents=True, exist_ok=True)
    comfy = Comfy()
    report = []
    for key in PANELS:
        panel = next(p for p in bible.PANELS if p.key == key)
        crop = bible.reference_crop(sheet_path, panel)
        crop_path = OUT / f"reference-{key}.png"
        crop.save(crop_path, "PNG")
        instruction = bible.edit_instruction(panel, panel.tags)
        width, height = bible.size(panel)
        reference = await comfy.upload(crop_path.read_bytes(), f"probe5-{key}.png")
        result = await run(comfy, key, workflows.joy_edit(reference, instruction, SEED,
                                                         negative=bible.NEGATIVE, size=(width, height)))
        result.update(reference_size=list(crop.size), instruction=instruction)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        report.append(result)
    (OUT / "report.json").write_text(json.dumps(
        {"sheet": sheet_path.name, "seed": SEED, "negative": bible.NEGATIVE, "results": report},
        ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
