"""アプリから一回のCLI実行へ接続する。待機中にHTTP処理を止めない。"""
import asyncio
import base64
import json
import os
from pathlib import Path
import shlex
import sys


async def interpret(job: dict, images: list[bytes]) -> dict:
    payload = {key: job[key] for key in ("original_comment", "record_description", "existing_settings", "references", "image_comments", "base_conditions", "stage", "panel")}
    packet = {"input": payload, "images": [base64.b64encode(image).decode("ascii") for image in images]}
    host = os.environ.get("SPRITEFORGE_INTENT_SSH", "")
    if host:
        root = os.environ["SPRITEFORGE_INTENT_HOST_ROOT"]
        args = ["ssh", "-T", "-o", "BatchMode=yes", host,
                f"cd {shlex.quote(root)} && uv run --no-sync python -m backend.intent_cli"]
    else:
        args = [sys.executable, "-m", "backend.intent_cli"]
    process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                   cwd=Path(__file__).resolve().parents[1])
    stdout, stderr = await process.communicate(json.dumps(packet, ensure_ascii=False).encode())
    if process.returncode:
        raise RuntimeError(stderr.decode(errors="replace").strip() or f"解釈処理が終了値{process.returncode}で失敗しました。")
    result = json.loads(stdout)
    job["interpreter"] = {key: result[key] for key in ("model", "elapsed_seconds", "auth")}
    return result["proposal"]
