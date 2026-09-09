"""合格した一枚シートを入力に、設定画パネル（別アングル）を描けるかを fox で実測する。

probe.py で ReferenceLatent が Anima に対して無効（出力がベースラインと1ピクセル差もない）
と分かったため、画像を実際に読む経路だけを残して比べる。
使い方: uv run python evidence/bible-sheet-source-20260910/probe2.py <sheet.png>
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from backend import workflows
from backend.comfy import Comfy

OUT = Path(__file__).resolve().parent / "out2"

LORA = "ndac1de01_preference_f24a5a97-167b-492e-b7b1-85c6f767efe5.safetensors"
TRIGGER = "ndac1de01"
BODY = ("slim young adult woman with a slightly stylized roughly six-head-tall proportion, "
        "white cropped top with a fluffy fur collar and diamond chest opening, gold trim and star ornaments, "
        "layered white ruffled mini skirt, white fur-trimmed knee-high boots")
BACK = "full body, standing, back view, from behind, solo, simple background, white background"
QUALITY = "lowres, bad anatomy, bad hands, text, watermark"
SINGLE_VIEW = "multiple views, reference sheet, collage"
SEED, WIDTH, HEIGHT = 1, 832, 1216


def img2img(sheet: str, denoise: float) -> dict:
    """シートを latent の出発点にした、LoRA つきの Anima img2img。"""
    prompt = f"{TRIGGER}, {BODY}, {BACK}"
    graph = workflows.anima_txt2img(prompt, SEED, loras=[(LORA, 0.8)],
                                    negative=f"{QUALITY}, {SINGLE_VIEW}", width=WIDTH, height=HEIGHT)
    graph["30"] = {"class_type": "LoadImage", "inputs": {"image": sheet}}
    graph["31"] = {"class_type": "ImageScale",
                   "inputs": {"image": ["30", 0], "width": WIDTH, "height": HEIGHT,
                              "upscale_method": "lanczos", "crop": "center"}}
    graph["32"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["31", 0], "vae": ["3", 0]}}
    graph["23"]["inputs"]["latent_image"] = ["32", 0]
    graph["23"]["inputs"]["denoise"] = denoise
    return graph


async def run(comfy: Comfy, label: str, graph: dict) -> dict:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe2-{label}")
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
    sheet = await comfy.upload(sheet_path.read_bytes(), "probe2-approved-sheet.png")
    print("uploaded:", sheet, flush=True)
    cases = {
        "e-joy-edit-back-view": workflows.joy_edit(
            sheet, f"Draw the same character as in the reference. {BACK}", SEED,
            negative=f"{QUALITY}, {SINGLE_VIEW}", size=(WIDTH, HEIGHT)),
        "f-img2img-denoise-0.55": img2img(sheet, 0.55),
        "g-img2img-denoise-0.85": img2img(sheet, 0.85),
    }
    report = []
    for label, graph in cases.items():
        result = await run(comfy, label, graph)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        report.append(result)
    (OUT / "report.json").write_text(json.dumps(
        {"sheet": sheet_path.name, "lora": LORA, "seed": SEED, "size": [WIDTH, HEIGHT],
         "panel": BACK, "results": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
