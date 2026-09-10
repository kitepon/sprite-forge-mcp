"""fox の ComfyUI QwenVL で、一回の画像解釈を実行する。"""
from __future__ import annotations

import asyncio
import json
import re
import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from . import workflows
from .comfy import execution_failure
from .intent import (
    GenerationProposal, IntentRevision, Observation, Proposal, Reference, StrictModel, TrainingRevision,
)
from .preview_intent import BatchPrompt, ReviewMeaning
from .preview_learning import SPATIAL_FOCUS, mask_is_empty, spatial_keys_from_focus_and_text, union_masks
from .sheet_layout import LayoutChange, merge_layout_change

MODEL = "Qwen3-VL-32B-Instruct"
AUTH = "comfy"
CLIENT_ID = "sprite-forge-intent"
OBSERVE_MARK = "この画像の見た目を JSON で返してください。画風を表す語句は書かないでください。"
TRAINING_OBSERVE_MARK = "この画像の学習用説明を JSON で返してください。"
INTERPRET_MAX_SIDE = 512
OBSERVE_TOPIC_JA = {"hair": "髪", "face": "顔", "outfit": "衣装", "body": "体", "style": "画風"}


class Sighting(StrictModel):
    appearance_ja: str
    caption_en: str


def _strict_schema(model):
    schema = model.model_json_schema()

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


def _parse_json_text(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"解釈の応答をJSONとして読めません: {error}") from error


def _output_text(output: dict):
    for key in ("text", "string"):
        value = output.get(key)
        if isinstance(value, list) and value:
            item = value[0]
            return item if isinstance(item, str) else str(item)
        if isinstance(value, str):
            return value
    return None


def _history_text(history: dict) -> str:
    outputs = history.get("outputs") or {}
    for node in ("3", "2"):
        if node in outputs:
            text = _output_text(outputs[node])
            if text is not None:
                return text
    for output in outputs.values():
        text = _output_text(output)
        if text is not None:
            return text
    raise RuntimeError("解釈の応答テキストを受け取れませんでした。")


async def _history_until_done(comfy, prompt_id: str) -> dict:
    missing = 0
    while True:
        history = await comfy.history(prompt_id)
        status = history.get("status", {})
        if status.get("completed"):
            return history
        if status.get("status_str") == "error":
            raise RuntimeError(execution_failure(status))
        if not history:
            queue = await comfy.queue()
            queued = any(item[1] == prompt_id for lane in ("queue_running", "queue_pending") for item in queue.get(lane, []))
            missing = 0 if queued else missing + 1
            if missing >= 3:
                raise RuntimeError(f"ComfyUI dropped prompt {prompt_id}: not in queue, not in history")
        await asyncio.sleep(1)


def _stage_model(payload: dict):
    stage = payload.get("stage")
    if stage == "preview_review":
        return ReviewMeaning
    if stage == "preview_batch_prompt":
        return BatchPrompt
    if stage == "layout":
        return LayoutChange
    if stage in ("samples", "training"):
        return Proposal
    # 生成工程では training_samples をスキーマから外し、max_tokens 内で切れないようにする。
    return GenerationProposal


def _instruction_name(payload: dict) -> str:
    stage = payload.get("stage")
    if stage == "preview_review":
        return "preview_review_instructions.txt"
    if stage == "preview_batch_prompt":
        return "preview_batch_prompt_instructions.txt"
    if stage == "layout":
        return "layout_instructions.txt"
    return "intent_instructions.txt"


def observe_range(payload: dict) -> dict:
    """判定の観察範囲。画像を見せる前に、部位指定とユーザーの文から決める。"""
    focus = payload.get("focus")
    comment = (payload.get("comment") or "").strip()
    regions = list(spatial_keys_from_focus_and_text(focus, comment))
    topics = list(regions)
    if isinstance(focus, list) and "style" in focus and "style" not in topics:
        topics.append("style")
    return {
        "regions": regions,
        "topics": topics,
        "comment": comment,
        "intent": "preserve" if payload.get("rating") == "ok" else "fix",
    }


def _training_purpose(payload: dict, index: int) -> dict | None:
    """学習観察へ渡す、この画像の用途。生成工程の観察範囲とは別。"""
    if payload.get("stage") not in ("samples", "training"):
        return None
    comments = payload.get("image_comments") or []
    comment = comments[index].strip() if index < len(comments) and isinstance(comments[index], str) else ""
    return {"comment": comment, "overall": (payload.get("original_comment") or "").strip()}


def _observe_prompt(index: int, schema: dict, view: dict | None = None, purpose: dict | None = None) -> str:
    if purpose is not None:
        extra = ["利用者の文が示す、この画像の用途に必要な見た目だけを書いてください。"]
        if purpose["overall"]:
            extra.append(f"全体の希望: {purpose['overall']}")
        extra.append(f"この画像への文: {purpose['comment']}" if purpose["comment"]
                     else "この画像への個別の文はありません。全体の希望がこの枚に割り当てる用途だけを書いてください。")
        extra.append(
            "用途が画風なら、線・塗り・質感・光の扱いだけを書く。写っている別の衣装や体形は学習文にしない。"
            "用途が衣装や等身なら、部品、つながり、覆う範囲と見える範囲を落とさず書く。短い総称で切れ目や露出を消さない。"
            "用途がポーズや構図の例なら、姿勢と構図だけを書く。"
            "利用者の希望そのもの、画像番号、呼び出し語は書かない。"
        )
        lead = f"{TRAINING_OBSERVE_MARK}{''.join(extra)}これは{index}枚目の参考画像です。"
    else:
        lead = f"{OBSERVE_MARK}これは{index}枚目の参考画像です。"
        if view is not None:
            labels = [OBSERVE_TOPIC_JA[key] for key in view["topics"] if key in OBSERVE_TOPIC_JA]
            extra = []
            if labels:
                if view.get("intent") == "preserve":
                    extra.append(f"残したい範囲は{'、'.join(labels)}です。差があっても直す内容は書かないでください。残したい内容だけ書いてください。")
                else:
                    extra.append(f"見る範囲は{'、'.join(labels)}だけです。指定していない部位の特徴は書かないでください。description_enも{'、'.join(labels)}の英語タグだけにしてください。")
            if view["comment"]:
                extra.append(f"ユーザーの文: {view['comment']}")
                if not labels:
                    extra.append("文が示す範囲だけを見てください。文にない部位の特徴は書かないでください。")
            if extra:
                lead = f"{OBSERVE_MARK}{''.join(extra)}これは{index}枚目の参考画像です。"
    return (
        lead
        + "出力は次の JSON Schema に厳密に従い、前後に説明を付けないでください。\n"
        + json.dumps(schema, ensure_ascii=False)
    )


def _as_rgba_png(content: bytes) -> bytes:
    image = Image.open(BytesIO(content)).convert("RGBA")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _first_image(history: dict) -> dict:
    for output in (history.get("outputs") or {}).values():
        images = output.get("images") or []
        if images:
            return images[0]
    raise RuntimeError("ComfyUI history has no image output")


def _keep_region_pixels(content: bytes, mask_png: bytes) -> bytes:
    image = Image.open(BytesIO(content)).convert("RGBA")
    mask = Image.open(BytesIO(mask_png)).convert("L").resize(image.size)
    black = Image.new("RGBA", image.size, (0, 0, 0, 255))
    output = BytesIO()
    Image.composite(image, black, mask).save(output, format="PNG")
    return output.getvalue()


async def _region_mask_png(comfy, content: bytes, prompt: str, name: str) -> bytes:
    uploaded = await comfy.upload(content, name)
    prompt_id = await comfy.submit(workflows.sam3_mask(uploaded, prompt), CLIENT_ID)
    png = _as_rgba_png(await comfy.view(_first_image(await _history_until_done(comfy, prompt_id))))
    if mask_is_empty(png):
        raise RuntimeError(f"マスクが空です: {prompt}")
    return png


async def _restrict_image(comfy, content: bytes, regions: list[str], index: int) -> bytes:
    parts = []
    for region in regions:
        prompt = SPATIAL_FOCUS[region]
        parts.append(await _region_mask_png(comfy, content, prompt, f"intent-{index}-{region}.png"))
    return _keep_region_pixels(content, union_masks(parts))


def _interpret_image_png(content: bytes, max_side: int = INTERPRET_MAX_SIDE) -> bytes:
    """解釈用コピーだけ長辺を揃える。台帳の原画像は触らない。拡大しない。"""
    image = Image.open(BytesIO(content))
    image.load()
    if max(image.size) > max_side:
        image = image.copy()
        image.thumbnail((max_side, max_side), Image.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _compose_prompt(payload: dict, schema: dict, observations: list[dict]) -> str:
    instruction = Path(__file__).with_name(_instruction_name(payload)).read_text()
    parts = [instruction.rstrip(), "入力:", json.dumps(payload, ensure_ascii=False)]
    if observations:
        parts += ["観察:", json.dumps(observations, ensure_ascii=False)]
    parts += ["出力は次の JSON Schema に厳密に従い、前後に説明を付けないでください。",
              json.dumps(schema, ensure_ascii=False)]
    return "\n".join(parts)


async def _ask(comfy, prompt: str, *, image: str | None = None, keep_model_loaded: bool = False) -> str:
    prompt_id = await comfy.submit(
        workflows.qwen_vl_interpret(prompt, image=image, keep_model_loaded=keep_model_loaded), CLIENT_ID)
    history = await _history_until_done(comfy, prompt_id)
    return _history_text(history)


def _validate(model, raw: str):
    try:
        return model.model_validate(_parse_json_text(raw))
    except ValidationError as error:
        raise RuntimeError(f"解釈のJSONがスキーマに合いません: {error}") from error


async def _wait_until_idle(comfy) -> None:
    """描画と解釈は同一GPUなので、キューが空いてから解釈を始める。"""
    while True:
        queue = await comfy.queue()
        if not queue.get("queue_running") and not queue.get("queue_pending"):
            return
        await asyncio.sleep(1)


async def execute(payload: dict, images: list[bytes], *, comfy, keep_model_loaded: bool = False,
                  reclaim_memory: bool = True) -> dict:
    if comfy is None:
        raise RuntimeError("Comfyが渡されていない")
    started = time.monotonic()
    if reclaim_memory:
        await _wait_until_idle(comfy)
        await comfy.free()
    model = _stage_model(payload)
    schema = _strict_schema(model)
    view = observe_range(payload) if payload.get("stage") == "preview_review" else None
    if view is not None and view["regions"] and images:
        images = [await _restrict_image(comfy, content, view["regions"], index)
                  for index, content in enumerate(images)]
    names = [await comfy.upload(_interpret_image_png(content), f"intent-{index}.png")
             for index, content in enumerate(images)]
    sightings = []
    training = payload.get("stage") in ("samples", "training")
    if len(names) >= 2 or (training and names):
        observe_schema = _strict_schema(Sighting)
        for index, name in enumerate(names):
            purpose = _training_purpose(payload, index)
            sighting = _validate(Sighting, await _ask(
                comfy, _observe_prompt(index, observe_schema, view, purpose),
                image=name, keep_model_loaded=True))
            sightings.append({"index": index, **sighting.model_dump()})
        compose_image = None
    elif len(names) == 1:
        compose_image = names[0]
    else:
        compose_image = None
    compose_payload = dict(payload)
    if view is not None:
        compose_payload["observe_range"] = view
    # 観察済みなら最終応答は差分だけ。観察を再出力させると max_tokens で JSON が切れる。
    compose_model = (TrainingRevision if (model is Proposal and sightings)
                     else IntentRevision if (model is GenerationProposal and sightings)
                     else model)
    compose_schema = _strict_schema(compose_model)
    proposal = _validate(compose_model, await _ask(comfy, _compose_prompt(compose_payload, compose_schema, sightings),
                                                   image=compose_image, keep_model_loaded=keep_model_loaded))
    if compose_model is LayoutChange:
        # モデルには差分だけを書かせ、全項目の構成はここで現在の構成へ合成する。
        proposal = merge_layout_change(proposal, payload["sheet_layout"])
    elif compose_model in (IntentRevision, TrainingRevision):
        references = payload.get("references") or []
        if len(references) != len(sightings):
            raise RuntimeError(
                f"観察済み画像数({len(sightings)})と参照数({len(references)})が一致しません"
            )
        observations = [
            Observation(
                reference=Reference.model_validate(references[item["index"]]),
                appearance_ja=item["appearance_ja"],
                caption_en=item["caption_en"],
            )
            for item in sightings
        ]
        proposal = Proposal(
            observations=observations,
            changes=proposal.changes,
            questions=proposal.questions,
            training_samples=proposal.training_samples if compose_model is TrainingRevision else None,
        )
    elif model is GenerationProposal:
        # 下流は Proposal 形で揃える。学習欄は生成工程では常に未使用。
        proposal = Proposal(**proposal.model_dump(), training_samples=None)
    return {"proposal": proposal.model_dump(), "model": MODEL,
            "elapsed_seconds": round(time.monotonic() - started, 2), "auth": AUTH}
