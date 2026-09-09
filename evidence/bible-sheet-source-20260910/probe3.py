"""合格シートから切り出した「一体だけ」を参照に、設定画パネルを描けるかを fox で実測する。

probe2 でシート全体を JoyAI へ渡すと、出力もシート構図（複数ビュー＋パレット）を写した。
入力の構図が出力へ写るなら、参照を単体像にすれば単体パネルが出るはず——それを確かめる。
使い方: uv run python evidence/bible-sheet-source-20260910/probe3.py <sheet.png>
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

OUT = Path(__file__).resolve().parent / "out3"

QUALITY = "lowres, bad anatomy, bad hands, text, watermark"
SINGLE_VIEW = "multiple views, reference sheet, collage, color palette, multiple panels"
SEED, WIDTH, HEIGHT = 1, 832, 1216

PANELS = {
    "h-back-view": "full body, standing, back view, from behind",
    "i-front-smiling": "full body, standing, front view, looking at viewer, smiling",
    "j-sitting": "full body, sitting on the floor, side view",
}


def figure_columns(sheet: Path, floor: int = 240, gap: int = 2) -> list[tuple[int, int]]:
    """白い谷でシートを縦に割り、人物の列範囲を返す。人物が接触した列はまとまったまま返る。"""
    grey = Image.open(sheet).convert("L")
    width, height = grey.size
    pixels = grey.load()
    runs: list[tuple[int, int]] = []
    start = None
    for x in range(width):
        ink = sum(1 for y in range(0, height, 4) if pixels[x, y] < floor)
        if ink > gap and start is None:
            start = x
        elif ink <= gap and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, width))
    return [(a, b) for a, b in runs if b - a > 20]


async def run(comfy: Comfy, label: str, graph: dict) -> dict:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe3-{label}")
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
    OUT.mkdir(parents=True, exist_ok=True)
    columns = figure_columns(sheet_path)
    single = min(columns, key=lambda run: run[1] - run[0])
    crop_path = OUT / "reference-single-figure.png"
    Image.open(sheet_path).convert("RGB").crop((single[0], 0, single[1], Image.open(sheet_path).height)).save(crop_path)
    print("columns:", columns, "-> single:", single, flush=True)

    comfy = Comfy()
    reference = await comfy.upload(crop_path.read_bytes(), "probe3-single-figure.png")
    print("uploaded:", reference, flush=True)
    report = []
    for label, panel in PANELS.items():
        prompt = (f"Draw the same character as in the reference image, keeping the face, hair and outfit "
                  f"identical. {panel}, solo, plain white background")
        graph = workflows.joy_edit(reference, prompt, SEED,
                                   negative=f"{QUALITY}, {SINGLE_VIEW}", size=(WIDTH, HEIGHT))
        result = await run(comfy, label, graph)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        report.append(result)
    (OUT / "report.json").write_text(json.dumps(
        {"sheet": sheet_path.name, "columns": columns, "reference_column": single, "seed": SEED,
         "size": [WIDTH, HEIGHT], "panels": PANELS, "results": report}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
