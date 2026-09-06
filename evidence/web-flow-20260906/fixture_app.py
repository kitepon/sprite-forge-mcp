"""導線のブラウザー試験用。画像解析とGPU学習だけを模擬し、台帳・HTTPは実物を使う。"""
import asyncio

from backend.app import app, services


async def interpret(job, images):
    await asyncio.sleep(3)
    if "失敗を確認" in job["original_comment"]:
        raise RuntimeError("検証用の画像解析エラー")
    return {"observations": [{"reference": ref, "appearance_ja": "検証用の色の画像", "caption_en": "colored test image"} for ref in job["references"]],
            "training_samples": [{"reference": ref, "priority": "primary" if job["original_comment"].strip() else "normal",
                                  "features": ["style"] if job["original_comment"].strip() else [],
                                  "reason_ja": "この素材の画風を学びます"} for ref in job["references"]],
            "questions": ["どの画像の顔を使いますか？"] if "質問を確認" in job["original_comment"] else [],
            "changes": [{"feature": "style", "scope": "persistent", "panel_key": None, "reference": job["references"][0],
                         "description_en": "", "avoid_en": "", "avoid_ja": "", "reason_ja": "素材の画風を学びます"}]
            if job["original_comment"].strip() or any(job["image_comments"]) else []}


async def train(job, *_args):
    job["status"] = "running"
    services.events.save_job(job)
    for i in range(1, 4):
        await asyncio.sleep(1)
        job["progress"] = {"step": i, "total": 3}
        services.events.save_job(job)
    job["status"] = "completed"
    services.events.save_job(job)
    return job


async def gpu():
    return {"devices": [{"name": "UI検証用・GPUは使用しません"}]}


services.intent_interpreter = interpret
services._execute_training = train
# FastAPIへ登録済みのハンドラーも同じComfyオブジェクトを見る。
services.comfy.stats = gpu
