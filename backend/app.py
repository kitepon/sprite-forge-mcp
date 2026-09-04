"""Two thin HTTP faces over exactly one ``Services`` instance."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans

from .services import Services

services = Services()
mcp = FastMCP("sprite-forge")


for name, function in (
    ("gpu_status", services.gpu_status),
    ("generate_base", services.start_base),
    ("generate_sprite", services.generate_sprite),
    ("list_loras", services.list_loras),
    ("generate_character_bible", services.generate_character_bible),
    ("bible_status", services.bible_status),
    ("train_character_lora", services.train_character_lora),
    ("train_status", services.train_status),
    ("make_mask", services.make_mask),
    ("generate_variant", services.generate_variant),
    ("make_transparent", services.make_transparent),
    ("pixelize", services.pixelize),
    ("job_status", services.status),
    ("list_jobs", services.list_jobs),
):
    mcp.tool(function, name=name)


mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def app_lifespan(_app):
    yield


app = FastAPI(title="sprite-forge", lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))


for path, methods, function in (
    ("/api/gpu", ["GET"], services.gpu_status),
    ("/api/base", ["POST"], services.start_base),
    ("/api/generate", ["POST"], services.generate_sprite),
    ("/api/loras", ["GET"], services.list_loras),
    ("/api/bible", ["POST"], services.generate_character_bible),
    ("/api/bible/{job_id}", ["GET"], services.bible_status),
    ("/api/lora", ["POST"], services.train_character_lora),
    ("/api/lora/{job_id}", ["GET"], services.train_status),
    ("/api/mask", ["POST"], services.make_mask),
    ("/api/variant", ["POST"], services.generate_variant),
    ("/api/transparent", ["POST"], services.make_transparent),
    ("/api/pixelize", ["POST"], services.pixelize),
    ("/api/jobs", ["GET"], services.list_jobs),
    ("/api/jobs/{job_id}", ["GET"], services.status),
):
    app.add_api_route(path, function, methods=methods)


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
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "web", html=True), name="web")
