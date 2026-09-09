"""別衣装パネルだけ、除去する部位を並べた文で再測する。

probe9 で体型図（レオタード）は成功し、別衣装（カジュアル）は上半身が元の衣装のまま残った。
二つの指示の違いは、成功した方が「スカート・袖・襟・ブーツを含めて」と外す部位を並べていたこと。
編集モデルは「元の衣装を全部外す」という抽象的な否定より、部位名の列挙に従うと読める。部位名は
衣類の一般語なので、キャラクターごとの知識を要さずに書ける。

カジュアルと鎧の二つで確かめる。鎧は輪郭が大きく変わるので、列挙が効くなら汎用性の根拠になる。

使い方: uv run python evidence/bible-sheet-source-20260910/probe10.py
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from backend import bible, workflows
from backend.comfy import Comfy

HERE = Path(__file__).resolve().parent
REF = HERE / "out8"
OUT = HERE / "out10"
SEED = 1
STRIP = ("Remove the original top, sleeves, collar, skirt, gloves and footwear; none of them remain.")


def instruction(outfit: str) -> str:
    return (f"Replace the character's clothes with: {outfit}. {STRIP} "
            "Keep the face, hairstyle and hair ornaments exactly as in the reference image. "
            f"full body, standing, front view, solo, {bible.COMMON}")


CASES = (("cos_casual", "hoodie, denim shorts, sneakers, casual clothes"),
         ("cos_armor", "plate armor, knight, breastplate, pauldrons, gauntlets"))


async def wait(comfy: Comfy, label: str, graph: dict) -> tuple[list[dict], float]:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe10-{label}")
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


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comfy = Comfy()
    reference = await comfy.upload((REF / "reference-figure.png").read_bytes(), "probe10-figure.png")
    report = []
    for key, outfit in CASES:
        panel = next(p for p in bible.PANELS if p.key == key)
        text = instruction(outfit)
        images, seconds = await wait(comfy, key, workflows.joy_edit(
            reference, text, SEED, negative=bible.NEGATIVE, size=bible.size(panel)))
        (OUT / f"{key}.png").write_bytes(await comfy.view(images[-1]))
        entry = {"panel": key, "seconds": seconds, "instruction": text}
        report.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main())
