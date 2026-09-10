"""The only ComfyUI transport: HTTP request/response, no polling or sockets."""
from __future__ import annotations

from typing import Any
import httpx

from .config import COMFY_URL


def execution_failure(status: dict[str, Any]) -> str:
    """ComfyUI history status から、node と例外本文だけを取る。current_inputs のテンソルは捨てる。"""
    messages = status.get("messages") or []
    for item in messages:
        if not (isinstance(item, (list, tuple)) and len(item) >= 2):
            continue
        kind, payload = item[0], item[1]
        if kind != "execution_error" or not isinstance(payload, dict):
            continue
        node = payload.get("node_type") or payload.get("node_id") or "node"
        typ = payload.get("exception_type") or "Error"
        message = str(payload.get("exception_message") or "").strip()
        if message:
            return f"ComfyUI {node} {typ}: {message}"
        return f"ComfyUI {node} {typ}"
    return f"ComfyUI failed: {messages}"


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

    async def view(self, image: dict[str, Any]) -> bytes:
        response = await self.client.get(f"{self.base_url}/view", params=image)
        response.raise_for_status()
        return response.content

    async def free(self) -> None:
        response = await self.client.post(f"{self.base_url}/free", json={"unload_models": True, "free_memory": True})
        response.raise_for_status()
