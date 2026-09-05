"""ブラウザー確認用の隔離サーバー。GPUは常にfixture、解釈は明示指定で実CLI。"""
import argparse
import asyncio
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--real-interpreter", action="store_true")
    parser.add_argument("--with-bible", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
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
        if "失敗試験" in job["original_comment"]:
            raise RuntimeError("試験用の解釈エラー")
        return {"observations": [{"reference": job["references"][-1], "appearance_ja": "確認用の画像観察"}],
                "questions": [], "changes": [{"feature": "outfit", "scope": "persistent", "panel_key": None,
                "reference": job["references"][-1], "description_en": "separate top and skirt",
                "avoid_en": "", "avoid_ja": "", "reason_ja": "最後の画像の衣装を今後も共通に使います"}]}

    service._view = view
    service.comfy.stats = stats
    if not args.real_interpreter:
        service.intent_interpreter = interpret

    async def setup():
        await service.create_character("確認用", "she/her", lora_name="fixture.safetensors")
        for path in args.reference:
            await service.add_samples("確認用", str(path.resolve()))
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
