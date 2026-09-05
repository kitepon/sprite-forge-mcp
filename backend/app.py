"""Two thin HTTP faces over exactly one ``Services`` instance."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans

from .config import CACHE
from .services import Services

services = Services()
mcp = FastMCP("sprite-forge")


for name, function in (
    ("gpu_status", services.gpu_status),
    ("generate_base", services.start_base),
    ("generate_sprite", services.generate_sprite),
    ("list_loras", services.list_loras),
    ("create_character", services.create_character),
    ("add_samples", services.add_samples),
    ("remove_sample", services.remove_sample),
    ("set_caption", services.set_caption),
    ("character_info", services.character_info),
    ("list_characters", services.list_characters),
    ("preview_character", services.preview_character),
    ("generate_character_bible", services.generate_character_bible),
    ("bible_status", services.bible_status),
    ("list_bible_panels", services.list_bible_panels),
    ("redraw_panel", services.redraw_panel),
    ("train_character_lora", services.train_character_lora),
    ("train_status", services.train_status),
    ("make_mask", services.make_mask),
    ("generate_variant", services.generate_variant),
    ("make_transparent", services.make_transparent),
    ("pixelize", services.pixelize),
    ("generate_from_bible", services.generate_from_bible),
    ("generate_image", services.generate_image),
    ("refine_image", services.refine_image),
    ("set_character_style", services.set_character_style),
    ("create_style", services.create_style),
    ("add_style_samples", services.add_style_samples),
    ("remove_style_sample", services.remove_style_sample),
    ("set_style_caption", services.set_style_caption),
    ("style_info", services.style_info),
    ("list_styles", services.list_styles),
    ("delete_style", services.delete_style),
    ("train_style_lora", services.train_style_lora),
    ("job_status", services.status),
    ("list_jobs", services.list_jobs),
    ("interpret_comment", services.interpret_comment),
    ("save_comment", services.save_comment),
    ("interpret_saved_comment", services.interpret_saved_comment),
    ("confirm_comment_intent", services.confirm_comment_intent),
    ("confirm_training_observations", services.confirm_training_observations),
    ("prepare_training", services.prepare_training),
    ("list_comment_intents", services.list_comment_intents),
):
    mcp.tool(function, name=name)


mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def app_lifespan(_app):
    yield


app = FastAPI(title="sprite-forge", lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))


@app.exception_handler(Exception)
async def report_error(_request: Request, error: Exception) -> JSONResponse:
    """Failures are not hidden: the WebUI shows the reason instead of a bare HTTP 500."""
    return JSONResponse(status_code=500, content={"detail": f"{type(error).__name__}: {error}"})



for path, methods, function in (
    ("/api/gpu", ["GET"], services.gpu_status),
    ("/api/base", ["POST"], services.start_base),
    ("/api/generate", ["POST"], services.generate_sprite),
    ("/api/loras", ["GET"], services.list_loras),
    ("/api/characters", ["GET"], services.list_characters),
    ("/api/characters", ["POST"], services.create_character),
    ("/api/characters/{name}", ["GET"], services.character_info),
    ("/api/characters/{name}/samples", ["POST"], services.add_samples),
    ("/api/characters/{name}/samples/{index}", ["DELETE"], services.remove_sample),
    ("/api/characters/{name}/samples/{index}/caption", ["POST"], services.set_caption),
    ("/api/characters/{name}/preview", ["POST"], services.preview_character),
    ("/api/bible", ["POST"], services.generate_character_bible),
    ("/api/bible/{job_id}", ["GET"], services.bible_status),
    ("/api/panels", ["GET"], services.list_bible_panels),
    ("/api/panel", ["POST"], services.redraw_panel),
    ("/api/lora", ["POST"], services.train_character_lora),
    ("/api/lora/{job_id}", ["GET"], services.train_status),
    ("/api/mask", ["POST"], services.make_mask),
    ("/api/variant", ["POST"], services.generate_variant),
    ("/api/transparent", ["POST"], services.make_transparent),
    ("/api/pixelize", ["POST"], services.pixelize),
    ("/api/from-bible", ["POST"], services.generate_from_bible),
    ("/api/image", ["POST"], services.generate_image),
    ("/api/refine", ["POST"], services.refine_image),
    ("/api/characters/{name}/style", ["POST"], services.set_character_style),
    ("/api/styles", ["GET"], services.list_styles),
    ("/api/styles", ["POST"], services.create_style),
    ("/api/styles/{name}", ["GET"], services.style_info),
    ("/api/styles/{name}", ["DELETE"], services.delete_style),
    ("/api/styles/{name}/samples", ["POST"], services.add_style_samples),
    ("/api/styles/{name}/samples/{index}", ["DELETE"], services.remove_style_sample),
    ("/api/styles/{name}/samples/{index}/caption", ["POST"], services.set_style_caption),
    ("/api/styles/{name}/train", ["POST"], services.train_style_lora),
    ("/api/jobs", ["GET"], services.list_jobs),
    ("/api/jobs/{job_id}", ["GET"], services.status),
    ("/api/intents", ["POST"], services.interpret_comment),
    ("/api/intents/drafts", ["POST"], services.save_comment),
    ("/api/intents/{job_id}/interpret", ["POST"], services.interpret_saved_comment),
    ("/api/intents", ["GET"], services.list_comment_intents),
    ("/api/intents/{job_id}/confirm", ["POST"], services.confirm_comment_intent),
    ("/api/intents/{job_id}/observations", ["POST"], services.confirm_training_observations),
    ("/api/training/prepare", ["POST"], services.prepare_training),
):
    app.add_api_route(path, function, methods=methods)


@app.post("/api/upload")
async def rest_upload(files: list[UploadFile]) -> list[dict[str, str]]:
    """Bring pictures in from the browser; each is stored as PNG under .cache/uploads."""
    return [{"name": file.filename or "", "path": str(services.save_upload(await file.read(), file.filename))} for file in files]


@app.get("/api/file")
async def rest_file(path: str) -> FileResponse:
    """Serve a picture from the cache so the WebUI can show what it made."""
    target = Path(path)
    if not target.is_absolute():
        target = CACHE / target
    return FileResponse(target)


async def _event_stream(since: str | None = None) -> AsyncIterator[str]:
    """Emit persisted events first, then follow the append-only log."""
    cursor = since
    while True:
        for event in services.events.read_since(cursor):
            cursor = event["event_id"]
            encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            yield f"id: {cursor}\nevent: {event['kind']}\ndata: {encoded}\n\n"
        yield ": keep-alive\n\n"
        await asyncio.sleep(0.25)


@app.get("/api/events")
async def rest_events(since: str | None = None) -> StreamingResponse:
    return StreamingResponse(_event_stream(since), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/mcp", mcp_app)


class WebUIFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        # ESM files ship together without a bundler. Re-read them after a deployment,
        # rather than mixing old browser-cached modules with the new entry point.
        response.headers["Cache-Control"] = "no-store"
        return response


app.mount("/", WebUIFiles(directory=Path(__file__).resolve().parents[1] / "web", html=True), name="web")
