"""設定画パネルを、合格した一枚シートを見て描けるかを fox で実測する。

同じ LoRA・同じ注文・同じ seed で、参照の渡し方だけを変えて並べる。
使い方: uv run python evidence/bible-sheet-source-20260910/probe.py <sheet.png>
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from backend import workflows
from backend.comfy import Comfy

OUT = Path(__file__).resolve().parent / "out"

LORA = "ndac1de01_preference_f24a5a97-167b-492e-b7b1-85c6f767efe5.safetensors"
PROMPT = ("ndac1de01, slim young adult woman with a slightly stylized roughly six-head-tall proportion, "
          "full body, standing, front view, looking at viewer, arms at sides, white cropped top with a fluffy fur "
          "collar and diamond chest opening, gold trim and star ornaments, layered white ruffled mini skirt, "
          "white fur-trimmed knee-high boots, simple background, white background")
QUALITY = "lowres, bad anatomy, bad hands, text, watermark"
SINGLE_VIEW = "multiple views, reference sheet, collage"
SEED, WIDTH, HEIGHT = 1, 832, 1216


def with_reference(sheet: str, negative: str) -> dict:
    """現行のパネル生成に、シートを参照 latent として足しただけのグラフ。"""
    graph = workflows.anima_txt2img(PROMPT, SEED, loras=[(LORA, 0.8)], negative=negative,
                                    width=WIDTH, height=HEIGHT)
    graph["30"] = {"class_type": "LoadImage", "inputs": {"image": sheet}}
    graph["31"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["30", 0], "vae": ["3", 0]}}
    graph["32"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["20", 0], "latent": ["31", 0]}}
    graph["23"]["inputs"]["positive"] = ["32", 0]
    return graph


async def run(comfy: Comfy, label: str, graph: dict) -> dict:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe-{label}")
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
    comfy = Comfy()
    sheet = await comfy.upload(sheet_path.read_bytes(), "probe-approved-sheet.png")
    print("uploaded:", sheet, flush=True)
    cases = {
        "a-baseline-txt2img": workflows.anima_txt2img(
            PROMPT, SEED, loras=[(LORA, 0.8)], negative=f"{QUALITY}, {SINGLE_VIEW}", width=WIDTH, height=HEIGHT),
        "b-reference-latent": with_reference(sheet, f"{QUALITY}, {SINGLE_VIEW}"),
        "c-reference-latent-without-single-view-negative": with_reference(sheet, QUALITY),
        "d-joy-edit": workflows.joy_edit(sheet, PROMPT, SEED, negative=f"{QUALITY}, {SINGLE_VIEW}",
                                        size=(WIDTH, HEIGHT)),
    }
    report = []
    for label, graph in cases.items():
        result = await run(comfy, label, graph)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        report.append(result)
    (OUT / "report.json").write_text(json.dumps(
        {"sheet": sheet_path.name, "lora": LORA, "seed": SEED, "size": [WIDTH, HEIGHT],
         "prompt": PROMPT, "results": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
