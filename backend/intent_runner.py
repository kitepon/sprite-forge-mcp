"""アプリから一回の画像解釈へ接続する。待機中にHTTP処理を止めない。"""
import base64

from .comfy import Comfy
from .intent_cli import execute


async def interpret(job: dict, images: list[bytes], comfy: Comfy | None = None) -> dict:
    if job['stage'] == 'preview_review':
        return await _interpret_packet(job, job['review_input'], images, comfy)
    if job['stage'] == 'preview_instruction':
        return await _interpret_packet(job, job['instruction_input'], images, comfy)
    if job['stage'] == 'material_revision':
        return await _interpret_packet(job, job['revision_input'], images, comfy)
    payload = {key: job[key] for key in ("original_comment", "record_description", "existing_settings", "references", "image_comments", "base_conditions", "stage", "panel")}
    # 旧記録には当時の工程既定がない。現在の既定で過去を補わない。
    payload["stage_conditions"] = job.get("stage_conditions", {})
    payload["panel_specs"] = job.get("panel_specs", [])
    payload["available_styles"] = job.get("available_styles", [])
    payload["training_captions"] = job.get("training_captions", [])
    payload["record_kind"] = job["record_kind"]
    payload["learning_request"] = "learning_steps" in job
    if job["stage"] == "layout":
        payload["sheet_layout"] = job.get("working_layout", job["sheet_layout"])
    return await _interpret_packet(job, payload, images, comfy)


async def _interpret_packet(job, payload, images, comfy):
    packet = {"input": payload, "images": [base64.b64encode(image).decode("ascii") for image in images]}
    owned = comfy is None
    client = comfy or Comfy()
    try:
        result = await execute(packet, client)
    finally:
        if owned:
            await client.close()
    job["interpreter"] = {key: result[key] for key in ("model", "elapsed_seconds", "auth")}
    return result["proposal"]
