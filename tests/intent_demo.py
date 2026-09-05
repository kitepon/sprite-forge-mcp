"""ブラウザー確認用の隔離サーバー。GPUは常にfixture、解釈は明示指定で実CLI。"""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--real-interpreter", action="store_true")
    parser.add_argument("--interpretation", type=Path)
    parser.add_argument("--with-bible", action="store_true")
    parser.add_argument("--with-style", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.real_interpreter and args.interpretation:
        parser.error("実CLIと保存済み解釈は同時に指定できません。")
    args.cache.mkdir(parents=True, exist_ok=False)
    os.environ["SPRITEFORGE_CACHE"] = str(args.cache.resolve())
    from backend import app
    from tests.test_style import ComfyFixture, png
    import uvicorn

    service = app.services
    service.comfy = ComfyFixture()

    async def view(_image):
        return png()

    async def stats():
        return {"devices": [{"name": "試験用（GPU未接続）", "vram_total": 0, "vram_free": 0}]}

    async def interpret(job, images):
        if args.interpretation:
            native = json.loads(args.interpretation.read_text())
            if len(native["references"]) != len(job["references"]):
                raise ValueError("保存済み解釈と同じ枚数の画像が必要です。")
            result = deepcopy(native["proposal"])
            refs = {ref["sample_index"]: job["references"][i] for i, ref in enumerate(native["references"])}
            for item in [*result["observations"], *result["changes"]]:
                if item["reference"] is not None:
                    item["reference"] = refs[item["reference"]["sample_index"]]
            job["interpreter"] = native["interpreter"]
            return result
        if "失敗試験" in job["original_comment"]:
            raise RuntimeError("試験用の解釈エラー")
        return {"observations": [{"reference": ref, "appearance_ja": "確認用の画像観察", "caption_en": "fixture subject"} for ref in job["references"]],
                "questions": [], "changes": [{"feature": "outfit", "scope": "panel" if job["stage"] == "panel" else "this_run" if job["record_kind"] == "style" else "persistent", "panel_key": job["panel"] or None,
                "reference": job["references"][-1], "description_en": "separate top and skirt",
                "avoid_en": "", "avoid_ja": "", "reason_ja": "最後の画像の衣装を使う確認用の提案です"}]}

    service._view = view
    service.comfy.stats = stats
    async def training(job, panels, stem, remote_root, steps):
        # 画面確認では学習器・SSH・GPUを一切呼ばない。
        for step in range(1, 4):
            job.update(status="running", progress={"step": steps * step // 3, "total": steps})
            service.events.save_job(job)
            service.events.append(job["job_id"], "progress", job["progress"])
            await asyncio.sleep(1)
        job.update(status="completed", fixture_training=True)
        service.events.save_job(job)
        return job
    service._execute_training = training
    if not args.real_interpreter:
        service.intent_interpreter = interpret

    async def setup():
        await service.create_character("確認用", "she/her", lora_name="fixture.safetensors")
        for path in args.reference:
            await service.add_samples("確認用", str(path.resolve()))
        if args.with_style:
            style = await service.create_style("確認用の画風")
            style["lora_name"] = "fixture-style.safetensors"
            service._save_style(style)
            for path in args.reference:
                await service.add_style_samples(style["name"], str(path.resolve()))
        if args.with_bible:
            from backend.bible import PANELS
            directory = args.cache.resolve() / "panels"
            directory.mkdir()
            for panel in PANELS:
                (directory / f"{panel.key}.png").write_bytes(png())
            record = await service.character_info("確認用")
            record["bible"] = {"sheet_path": record["samples_sheet"], "panels_dir": str(directory), "at": "確認用"}
            service._save_character(record)

    asyncio.run(setup())
    uvicorn.run(app.app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
