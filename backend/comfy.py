"""The only ComfyUI transport: HTTP request/response, no polling or sockets."""
from __future__ import annotations

from typing import Any
import httpx

from .config import COMFY_URL


class Comfy:
    def __init__(self, base_url: str = COMFY_URL, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=60)
        self._owned = client is None

    async def close(self) -> None:
        if self._owned:
            await self.client.aclose()

    async def stats(self) -> dict[str, Any]:
        response = await self.client.get(f"{self.base_url}/system_stats")
        response.raise_for_status()
        return response.json()

    async def submit(self, workflow: dict[str, Any], client_id: str) -> str:
        response = await self.client.post(f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": client_id})
        response.raise_for_status()
        payload = response.json()
        if payload.get("node_errors"):
            raise RuntimeError(f"ComfyUI node errors: {payload['node_errors']}")
        return payload["prompt_id"]

    async def history(self, prompt_id: str) -> dict[str, Any]:
        response = await self.client.get(f"{self.base_url}/history/{prompt_id}")
        response.raise_for_status()
        return response.json().get(prompt_id, {})

    async def queue(self) -> dict[str, Any]:
        response = await self.client.get(f"{self.base_url}/queue")
        response.raise_for_status()
        return response.json()

    async def upload(self, content: bytes, name: str) -> str:
        response = await self.client.post(f"{self.base_url}/upload/image", files={"image": (name, content, "image/png")}, data={"overwrite": "true"})
        response.raise_for_status()
        return response.json()["name"]
