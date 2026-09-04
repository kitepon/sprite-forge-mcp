"""Two thin HTTP faces over exactly one ``Services`` instance."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans

from .services import Services

services = Services()
mcp = FastMCP("sprite-forge")


@mcp.tool
async def gpu_status() -> dict:
    return await services.gpu_status()


@mcp.tool
async def generate_base(prompt: str, seed: int = 1) -> dict:
    return await services.start_base(prompt, seed)


@mcp.tool
async def job_status(job_id: str) -> dict:
    return await services.status(job_id)


mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def app_lifespan(_app):
    yield


app = FastAPI(title="sprite-forge", lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))


@app.get("/api/gpu")
async def rest_gpu() -> dict:
    return await services.gpu_status()


@app.post("/api/base")
async def rest_base(prompt: str, seed: int = 1) -> dict:
    return await services.start_base(prompt, seed)


@app.get("/api/jobs/{job_id}")
async def rest_status(job_id: str) -> dict:
    return await services.status(job_id)


app.mount("/mcp", mcp_app)
