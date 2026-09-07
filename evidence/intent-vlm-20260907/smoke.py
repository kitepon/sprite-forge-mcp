"""fox の Qwen-VL が、静止画1枚で指示スキーマを守るか測る。動画入力は使わない。"""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.comfy import Comfy
from backend.intent_cli import MODEL, execute
from backend.preview_intent import IdentityInstructionDraft, ReviewMeaning


ROOT = Path(__file__).resolve().parent


def png() -> bytes:
    image = Image.new("RGBA", (64, 96), "#88aacc")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def encoded(content: bytes) -> str:
    import base64
    return base64.b64encode(content).decode("ascii")


async def main():
    picture = encoded(png())
    comfy = Comfy()
    report = {"model": MODEL, "video_input": False, "cases": []}
    try:
        review = await execute({
            "input": {
                "stage": "preview_review",
                "image_id": "preview-1",
                "rating": "ng",
                "comment": "髪型がツインテールではない。衣装は合っている。",
                "focus": ["髪"],
            },
            "images": [picture],
        }, comfy)
        meaning = ReviewMeaning.model_validate(review["proposal"])
        review_ok = (
            any("髪" in item or "ツイン" in item for item in meaning.fix)
            and any("衣装" in item for item in meaning.preserve)
            and not any("衣装" in item for item in meaning.fix)
        )
        report["cases"].append({
            "stage": "preview_review",
            "elapsed_seconds": review["elapsed_seconds"],
            "proposal": review["proposal"],
            "schema_ok": True,
            "direction_ok": review_ok,
        })
        instruction = await execute({
            "input": {
                "stage": "preview_instruction",
                "prompt": "ndac1de01, full body",
                "negative": "",
                "previous": {"include_en": "", "avoid_en": "", "summary_ja": ""},
                "reviews": [{"id": "preview-1", "rating": "ng",
                             "comment": "髪型がツインテールではない。衣装は合っている。",
                             "meaning": meaning.model_dump()}],
            },
            "images": [picture],
        }, comfy)
        draft = IdentityInstructionDraft.model_validate(instruction["proposal"])
        lowered = f"{draft.include_en} {draft.avoid_en}".lower()
        instruction_ok = (
            "twin" in lowered
            and "anime style" not in lowered
            and not draft.include_en.lower().startswith("bob")
        )
        report["cases"].append({
            "stage": "preview_instruction",
            "elapsed_seconds": instruction["elapsed_seconds"],
            "proposal": instruction["proposal"],
            "schema_ok": True,
            "direction_ok": instruction_ok,
        })
        report["passed"] = all(case["schema_ok"] and case["direction_ok"] for case in report["cases"])
    except Exception as error:
        report["passed"] = False
        report["error"] = str(error)
    finally:
        await comfy.close()
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.get("passed") else 1)


if __name__ == "__main__":
    asyncio.run(main())
