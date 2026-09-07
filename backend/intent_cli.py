"""fox の ComfyUI 視覚言語モデルで、一回の画像解釈を実行する。"""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import sys
import time
import uuid

from .comfy import Comfy
from .intent import Proposal
from .preview_intent import IdentityInstructionDraft, ReviewMeaning
from .sheet_layout import LayoutProposal
from . import workflows

# 8B は否定の逆転で不採用。32B-FP8 は fox の transformers が kernels 0.16 を要求して失敗した。
MODEL = "Qwen3-VL-32B-Instruct"
QUANTIZATION = "8-bit (Balanced)"
AUTH = "comfy"


def result_model(packet: dict):
    stage = packet["input"].get("stage")
    if stage == "preview_review":
        return ReviewMeaning
    if stage == "preview_instruction":
        return IdentityInstructionDraft
    if stage == "layout":
        return LayoutProposal
    return Proposal


def schema_for(model) -> dict:
    schema = model.model_json_schema()
    # 保存済みの旧応答の省略は読めるが、新しい出力では全項目を返す。
    def require_properties(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if "properties" in value:
                value["required"] = list(value["properties"])
            for nested in value.values():
                require_properties(nested)
        elif isinstance(value, list):
            for nested in value:
                require_properties(nested)
    require_properties(schema)
    return schema


def instruction_name(packet: dict) -> str:
    stage = packet["input"].get("stage")
    if stage == "preview_review":
        return "preview_review_instructions.txt"
    if stage == "preview_instruction":
        return "preview_instruction_instructions.txt"
    if stage == "layout":
        return "layout_instructions.txt"
    if stage == "material_revision":
        return "material_revision_instructions.txt"
    return "intent_instructions.txt"


def prompt_for(packet: dict) -> str:
    instruction = Path(__file__).with_name(instruction_name(packet)).read_text()
    schema = json.dumps(schema_for(result_model(packet)), ensure_ascii=False)
    if not packet.get("images"):
        order = "この入力に画像はありません。"
    elif len(packet["images"]) == 1:
        order = "添付は1枚の静止画です。"
    else:
        order = "添付は複数の静止画です。各枚の観察は入力末尾のobservationsにあります。動画としては扱いません。"
    return (instruction + "\n" + order
            + "\n出力は次のJSON Schemaに一致するJSONオブジェクトだけです。前後の説明やコードフェンスは付けないでください。\n"
            + schema + "\n入力:\n" + json.dumps(packet["input"], ensure_ascii=False))


def observation_prompt(index: int, total: int) -> str:
    return (f"これは{total}枚中{index}枚目の静止画です。見えている被写体だけを日本語で書いてください。"
            "希望・判定・見えない特徴の推測は書かないでください。動画ではありません。"
            f'出力は次のJSONオブジェクトだけです。{{"index": {index}, "appearance_ja": ""}}')


def parse_json_object(text: str) -> dict:
    stripped = (text or "").strip()
    if not stripped:
        raise RuntimeError("解釈結果が空です。")
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[:stripped.rfind("```")]
        stripped = stripped.strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].lstrip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("解釈結果がJSONではありません。") from None
        value = json.loads(stripped[start:end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("解釈結果がJSONオブジェクトではありません。")
    return value


def parse_observation(text: str, index: int) -> dict:
    value = parse_json_object(text)
    if value.keys() != {"index", "appearance_ja"} or value.get("index") != index or not isinstance(value.get("appearance_ja"), str):
        raise RuntimeError("静止画の観察が所定のJSONではありません。")
    if not value["appearance_ja"].strip():
        raise RuntimeError("静止画の観察が空です。")
    return value


def text_from_history(history: dict) -> str:
    for output in history.get("outputs", {}).values():
        text = output.get("text")
        if isinstance(text, list) and text:
            return "\n".join(str(part) for part in text)
        if isinstance(text, str) and text.strip():
            return text
    raise RuntimeError("ComfyUIの解釈結果に文字列がありません。")


async def wait_until_done(comfy: Comfy, prompt_id: str) -> dict:
    missing = 0
    while True:
        history = await comfy.history(prompt_id)
        status = history.get("status", {})
        if status.get("completed"):
            return history
        if status.get("status_str") == "error":
            raise RuntimeError(f"解釈に失敗しました: {status.get('messages')}")
        if not history:
            queue = await comfy.queue()
            queued = any(item[1] == prompt_id for lane in ("queue_running", "queue_pending") for item in queue.get(lane, []))
            missing = 0 if queued else missing + 1
            if missing >= 3:
                raise RuntimeError(f"ComfyUI dropped prompt {prompt_id}: not in queue, not in history")
        await asyncio.sleep(1)


async def generate_text(comfy: Comfy, prompt: str, image: str | None, keep_model_loaded: bool) -> str:
    prompt_id = await comfy.submit(
        workflows.qwen_vl_interpret(prompt, image, model=MODEL, quantization=QUANTIZATION, keep_model_loaded=keep_model_loaded),
        "sprite-intent")
    return text_from_history(await wait_until_done(comfy, prompt_id))


async def execute(packet: dict, comfy: Comfy) -> dict:
    model = result_model(packet)
    names = []
    prefix = f"sprite-intent-{uuid.uuid4().hex}"
    for index, encoded in enumerate(packet["images"]):
        content = base64.b64decode(encoded, validate=True)
        names.append(await comfy.upload(content, f"{prefix}-{index + 1}.png"))
    queue = await comfy.queue()
    if not queue.get("queue_running") and not queue.get("queue_pending"):
        await comfy.free()
    started = time.monotonic()
    if len(names) <= 1:
        text = await generate_text(comfy, prompt_for(packet), names[0] if names else None, False)
    else:
        notes = []
        for offset, name in enumerate(names):
            notes.append(parse_observation(
                await generate_text(comfy, observation_prompt(offset + 1, len(names)), name, True),
                offset + 1))
        compose = prompt_for(packet) + "\nobservations:\n" + json.dumps(notes, ensure_ascii=False)
        text = await generate_text(comfy, compose, None, False)
    proposal = model.model_validate(parse_json_object(text))
    return {"proposal": proposal.model_dump(), "model": MODEL,
            "elapsed_seconds": round(time.monotonic() - started, 2), "auth": AUTH}


def run(packet: dict, comfy: Comfy | None = None) -> dict:
    async def once():
        client = comfy or Comfy()
        owned = comfy is None
        try:
            return await execute(packet, client)
        finally:
            if owned:
                await client.close()
    return asyncio.run(once())


def main():
    try:
        result = run(json.load(sys.stdin))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
