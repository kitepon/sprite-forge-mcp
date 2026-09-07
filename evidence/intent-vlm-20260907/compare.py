"""32B の載せ直しと 4-bit を、同じプレビュー用スキーマで分ける。8B は使わない。"""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import sys
import time

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.comfy import Comfy
from backend.intent_cli import parse_json_object, prompt_for, text_from_history, wait_until_done
from backend.preview_intent import IdentityInstructionDraft, ReviewMeaning
from backend import workflows


ROOT = Path(__file__).resolve().parent
CONFIGS = [
    {"label": "32B-8bit", "model": "Qwen3-VL-32B-Instruct", "quantization": "8-bit (Balanced)"},
    {"label": "32B-4bit", "model": "Qwen3-VL-32B-Instruct", "quantization": "4-bit (VRAM-friendly)"},
]


def png() -> bytes:
    image = Image.new("RGBA", (64, 96), "#88aacc")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def review_packet() -> dict:
    return {
        "input": {
            "stage": "preview_review",
            "image_id": "preview-1",
            "rating": "ng",
            "comment": "髪型がツインテールではない。衣装は合っている。",
            "focus": ["髪"],
        },
        "images": ["still"],
    }


def instruction_packet(meaning: dict) -> dict:
    return {
        "input": {
            "stage": "preview_instruction",
            "prompt": "ndac1de01, full body",
            "negative": "",
            "previous": {"include_en": "", "avoid_en": "", "summary_ja": ""},
            "reviews": [{"id": "preview-1", "rating": "ng",
                         "comment": "髪型がツインテールではない。衣装は合っている。",
                         "meaning": meaning}],
        },
        "images": ["still"],
    }


def review_ok(meaning: ReviewMeaning) -> bool:
    return (
        any("髪" in item or "ツイン" in item for item in meaning.fix)
        and any("衣装" in item for item in meaning.preserve)
        and not any("衣装" in item for item in meaning.fix)
    )


def instruction_ok(draft: IdentityInstructionDraft) -> bool:
    lowered = f"{draft.include_en} {draft.avoid_en}".lower()
    return "twin" in lowered and "anime style" not in lowered and not draft.include_en.lower().startswith("bob")


async def vram(comfy: Comfy) -> dict:
    device = (await comfy.stats())["devices"][0]
    return {
        "vram_free_gb": round(device["vram_free"] / 1e9, 2),
        "torch_used_gb": round((device["torch_vram_total"] - device["torch_vram_free"]) / 1e9, 3),
    }


async def generate(comfy: Comfy, prompt: str, image: str, model: str, quantization: str, keep: bool) -> dict:
    before = await vram(comfy)
    started = time.monotonic()
    prompt_id = await comfy.submit(
        workflows.qwen_vl_interpret(prompt, image, model=model, quantization=quantization, keep_model_loaded=keep),
        "sprite-intent-compare")
    text = text_from_history(await wait_until_done(comfy, prompt_id))
    return {
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "text": text,
        "vram_before": before,
        "vram_after": await vram(comfy),
    }


async def run_config(comfy: Comfy, image: str, config: dict) -> dict:
    await comfy.free()
    record = {"label": config["label"], "model": config["model"],
              "quantization": config["quantization"], "video_input": False, "cases": []}
    try:
        cold = await generate(comfy, prompt_for(review_packet()), image,
                              config["model"], config["quantization"], True)
        meaning = ReviewMeaning.model_validate(parse_json_object(cold["text"]))
        record["cases"].append({
            "stage": "preview_review",
            "role": "cold_keep",
            "elapsed_seconds": cold["elapsed_seconds"],
            "vram_before": cold["vram_before"],
            "vram_after": cold["vram_after"],
            "proposal": meaning.model_dump(),
            "schema_ok": True,
            "direction_ok": review_ok(meaning),
        })
        warm = await generate(comfy, prompt_for(instruction_packet(meaning.model_dump())), image,
                              config["model"], config["quantization"], True)
        draft = IdentityInstructionDraft.model_validate(parse_json_object(warm["text"]))
        record["cases"].append({
            "stage": "preview_instruction",
            "role": "warm_keep",
            "elapsed_seconds": warm["elapsed_seconds"],
            "vram_before": warm["vram_before"],
            "vram_after": warm["vram_after"],
            "proposal": draft.model_dump(),
            "schema_ok": True,
            "direction_ok": instruction_ok(draft),
        })
        record["passed"] = all(case["schema_ok"] and case["direction_ok"] for case in record["cases"])
    except Exception as error:
        record["passed"] = False
        record["error"] = str(error)
    return record


async def main():
    comfy = Comfy()
    report = {
        "video_input": False,
        "skipped": [
            "Qwen3-VL-8B は否定逆転の実測があるため再走しない",
            "unsloth 27B は公式 Qwen3-VL の視覚系列ではないため測らない",
        ],
        "configs": [],
    }
    try:
        name = await comfy.upload(png(), "sprite-intent-compare.png")
        for config in CONFIGS:
            report["configs"].append(await run_config(comfy, name, config))
        report["passed"] = all(item.get("passed") for item in report["configs"])
    except Exception as error:
        report["passed"] = False
        report["error"] = str(error)
    finally:
        await comfy.close()
    (ROOT / "compare.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.get("passed") else 1)


if __name__ == "__main__":
    asyncio.run(main())
