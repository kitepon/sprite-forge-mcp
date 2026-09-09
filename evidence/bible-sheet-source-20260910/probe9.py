"""probe8 で参照に負けた 4 パネルを、指示文を書き直して再測する。

probe8 の結果:
  背面図・顔アップ（頭部参照）は成功。
  衣装替え（cos_casual・body_front）は上半身が元の衣装のまま。
  チビ（chibi_big）は頭が少し大きいだけで SD になっていない。
  小物（item_head）は人物が描かれた。

失敗の共通点は、指示が「同じ人物を描く」から始まり、変えてほしい部分を後ろのタグに置いていること。
編集モデルは冒頭の「同じものを描く」を強く採り、後ろのタグを装飾として扱ったと読める。そこで
変更を命令文の主語にして、残すものを従属節へ回した文を試す。参照は probe8 で作った SAM 一体を使う。

使い方: uv run python evidence/bible-sheet-source-20260910/probe9.py
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
OUT = HERE / "out9"
SEED = 1

# (label, panel_key, 参照, 指示文)
CASES = (
    ("cos_casual", "cos_casual", "figure",
     "Replace the character's entire outfit with: hoodie, denim shorts, sneakers, casual clothes. "
     "Keep the face, hairstyle and hair ornaments exactly as in the reference image. "
     "Remove every part of the original costume. full body, standing, front view, solo, "
     f"{bible.COMMON}"),
    ("body_front", "body_front", "figure",
     "Replace the character's entire outfit with a plain white leotard covering only the torso. "
     "Keep the face, hairstyle and hair ornaments exactly as in the reference image. "
     "Remove every part of the original costume, including the skirt, sleeves, collar and boots. "
     "full body, standing, front view, bare arms, bare legs, barefoot, solo, "
     f"{bible.COMMON}"),
    ("chibi_big", "chibi_big", "figure",
     "Redraw the character in chibi super deformed style: the head is as large as the whole body, "
     "the limbs are short and stubby, and there are only two head-heights in total. "
     "Keep the face, hairstyle and outfit design recognisable. full body, standing, "
     f"looking at viewer, solo, {bible.COMMON}"),
    ("item_head", "item_head", "figure",
     "Remove the character completely. Draw only her hair ornament and headwear, laid out on their "
     f"own as a still life. no humans, no body, object focus, close-up, {bible.COMMON}"),
)


async def wait(comfy: Comfy, label: str, graph: dict) -> tuple[list[dict], float]:
    started = time.time()
    prompt_id = await comfy.submit(graph, f"probe9-{label}")
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
    refs = {name: await comfy.upload((REF / f"reference-{name}.png").read_bytes(), f"probe9-{name}.png")
            for name in ("figure", "head")}
    report = []
    for label, key, which, instruction in CASES:
        panel = next(p for p in bible.PANELS if p.key == key)
        graph = workflows.joy_edit(refs[which], instruction, SEED,
                                   negative=bible.NEGATIVE, size=bible.size(panel))
        images, seconds = await wait(comfy, label, graph)
        (OUT / f"{label}.png").write_bytes(await comfy.view(images[-1]))
        entry = {"label": label, "reference": which, "seconds": seconds, "instruction": instruction}
        report.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    await comfy.close()


if __name__ == "__main__":
    asyncio.run(main())
