"""注文から解釈入力を組み立て、fox の QwenVL へ渡す。"""


async def interpret(job: dict, images: list[bytes], *, comfy=None, keep_model_loaded: bool = False,
                    reclaim_memory: bool = True) -> dict:
    from .intent_cli import execute

    if job["stage"] == "preview_review":
        payload = job["review_input"]
    else:
        payload = {key: job[key] for key in ("original_comment", "record_description", "existing_settings",
                                             "references", "image_comments", "base_conditions", "stage", "panel")}
        # 旧記録には当時の工程既定がない。現在の既定で過去を補わない。
        payload["stage_conditions"] = job.get("stage_conditions", {})
        payload["panel_specs"] = job.get("panel_specs", [])
        payload["available_styles"] = job.get("available_styles", [])
        payload["training_captions"] = job.get("training_captions", [])
        payload["record_kind"] = job["record_kind"]
        payload["learning_request"] = "learning_steps" in job
        if job["stage"] == "layout":
            payload["sheet_layout"] = job.get("working_layout", job["sheet_layout"])
    result = await execute(payload, images, comfy=comfy, keep_model_loaded=keep_model_loaded,
                           reclaim_memory=reclaim_memory)
    job["interpreter"] = {key: result[key] for key in ("model", "elapsed_seconds", "auth")}
    return result["proposal"]
