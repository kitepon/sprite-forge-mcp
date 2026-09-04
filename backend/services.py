"""Use cases shared by the REST and MCP faces."""
from __future__ import annotations

import uuid
import asyncio
import struct
import zlib
from pathlib import Path
from typing import Any

from . import workflows
from .comfy import Comfy
from .events import EventStore


class Services:
    def __init__(self, comfy: Comfy | None = None, events: EventStore | None = None):
        self.comfy, self.events = comfy or Comfy(), events or EventStore()

    async def gpu_status(self) -> dict[str, Any]:
        return await self.comfy.stats()

    async def start_base(self, prompt: str, seed: int) -> dict[str, Any]:
        return await self._start("base", workflows.anima_base(prompt, seed), {"seed": seed})

    async def generate_sprite(self, prompt: str, count: int = 4, seed: int = 1,
                              lora_name: str | None = None, lora_trigger: str | None = None,
                              pose_image: str | None = None, turbo: bool = True) -> dict[str, Any]:
        """Generate RGBA candidates through Anima then ToonOut and cache them."""
        if not 1 <= count <= 8:
            raise ValueError("count must be between 1 and 8")
        job_id = str(uuid.uuid4())
        final_prompt = " ".join(part for part in (lora_trigger, prompt) if part)
        candidates: list[dict[str, Any]] = []
        for index in range(count):
            source_id = await self.comfy.submit(workflows.anima_txt2img(
                final_prompt, seed + index, turbo=turbo, lora_name=lora_name, pose_image=pose_image), job_id)
            source = await self._history_until_done(source_id)
            image = self._first_image(source)
            raw = await self._view(image)
            uploaded = await self.comfy.upload(raw, f"{job_id}-{index}-base.png")
            matte_id = await self.comfy.submit(workflows.toonout(uploaded), job_id)
            matte = await self._history_until_done(matte_id)
            result = await self._view(self._first_image(matte))
            path = self._generated_path(job_id, index)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(result)
            measurement = self._measure_rgba_png(result)
            candidates.append({"id": path.stem, "path": str(path), "seed": seed + index,
                               **measurement,
                               "prompt_id": matte_id})
        job = {"job_id": job_id, "kind": "sprite", "status": "completed", "candidates": candidates}
        self.events.save_job(job); self.events.append(job_id, "completed", {"count": count})
        return job

    async def list_loras(self) -> list[str]:
        response = await self.comfy.client.get(f"{self.comfy.base_url}/object_info")
        response.raise_for_status()
        required = response.json().get("LoraLoader", {}).get("input", {}).get("required", {})
        return list(required.get("lora_name", [[]])[0])

    async def _history_until_done(self, prompt_id: str) -> dict[str, Any]:
        for _ in range(90):
            history = await self.comfy.history(prompt_id)
            status = history.get("status", {})
            if status.get("completed"):
                return history
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI failed: {status.get('messages')}")
            await asyncio.sleep(1)
        raise TimeoutError(f"ComfyUI timed out: {prompt_id}")

    @staticmethod
    def _first_image(history: dict[str, Any]) -> dict[str, Any]:
        for output in history.get("outputs", {}).values():
            images = output.get("images", [])
            if images:
                return images[0]
        raise RuntimeError("ComfyUI history has no image output")

    async def _view(self, image: dict[str, Any]) -> bytes:
        response = await self.comfy.client.get(f"{self.comfy.base_url}/view", params=image)
        response.raise_for_status()
        return response.content

    @staticmethod
    def _generated_path(job_id: str, index: int) -> Path:
        from .config import CACHE
        return CACHE / "generated" / f"{job_id}-{index}.png"

    @staticmethod
    def _measure_rgba_png(content: bytes) -> dict[str, Any]:
        """Return canvas, corner alpha, and non-transparent bounding box for RGBA PNG."""
        if content[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("generated image is not PNG")
        pos, payload = 8, bytearray()
        width = height = depth = color = None
        while pos < len(content):
            size = struct.unpack(">I", content[pos:pos + 4])[0]
            kind, chunk = content[pos + 4:pos + 8], content[pos + 8:pos + 8 + size]
            pos += size + 12
            if kind == b"IHDR":
                width, height, depth, color, compression, filtering, interlace = struct.unpack(
                    ">IIBBBBB", chunk
                )
                if (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                    raise ValueError("generated PNG must be non-interlaced 8-bit RGBA")
            elif kind == b"IDAT":
                payload.extend(chunk)
            elif kind == b"IEND":
                break
        if width is None or height is None:
            raise ValueError("generated PNG has no IHDR")
        raw, stride = zlib.decompress(payload), width * 4
        rows: list[bytes] = []
        offset, previous = 0, bytearray(stride)
        for _ in range(height):
            mode, current = raw[offset], bytearray(raw[offset + 1:offset + 1 + stride])
            offset += stride + 1
            for index, value in enumerate(current):
                left = current[index - 4] if index >= 4 else 0
                up = previous[index]
                upper_left = previous[index - 4] if index >= 4 else 0
                if mode == 1:
                    current[index] = (value + left) & 255
                elif mode == 2:
                    current[index] = (value + up) & 255
                elif mode == 3:
                    current[index] = (value + ((left + up) // 2)) & 255
                elif mode == 4:
                    prediction = left + up - upper_left
                    pa, pb, pc = abs(prediction - left), abs(prediction - up), abs(prediction - upper_left)
                    nearest = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
                    current[index] = (value + nearest) & 255
                elif mode != 0:
                    raise ValueError(f"unsupported PNG filter: {mode}")
            rows.append(bytes(current))
            previous = current
        corners = [rows[0][3], rows[0][-1], rows[-1][3], rows[-1][-1]]
        left, top, right, bottom = width, height, -1, -1
        for y, row in enumerate(rows):
            for x in range(width):
                if row[x * 4 + 3]:
                    left, top = min(left, x), min(top, y)
                    right, bottom = max(right, x), max(bottom, y)
        bbox = None if right < 0 else {"left": left, "top": top, "right": right + 1, "bottom": bottom + 1}
        return {"canvas": {"width": width, "height": height}, "corners_alpha": corners, "bbox": bbox}

    async def start_edit(self, image: bytes, name: str, prompt: str, seed: int) -> dict[str, Any]:
        upload = await self.comfy.upload(image, name)
        return await self._start("edit", workflows.joy_edit(upload, prompt, seed), {"input": upload, "seed": seed})

    async def start_matte(self, image: bytes, name: str) -> dict[str, Any]:
        upload = await self.comfy.upload(image, name)
        return await self._start("matte", workflows.toonout(upload), {"input": upload})

    async def start_damage(self, image: bytes, name: str, prompt: str, seed: int) -> dict[str, Any]:
        upload = await self.comfy.upload(image, name)
        return await self._start("damage", workflows.damage(upload, prompt, seed), {"input": upload, "seed": seed})

    async def _start(self, kind: str, workflow: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        job = {"job_id": job_id, "kind": kind, "status": "queued", **payload}
        self.events.save_job(job); self.events.append(job_id, "queued", payload)
        prompt_id = await self.comfy.submit(workflow, job_id)
        job.update(status="submitted", prompt_id=prompt_id)
        self.events.save_job(job); self.events.append(job_id, "submitted", {"prompt_id": prompt_id})
        return job

    async def status(self, job_id: str) -> dict[str, Any]:
        job = self.events.load_job(job_id)
        if not job:
            return {"job_id": job_id, "status": "unknown"}
        if job.get("prompt_id"):
            history = await self.comfy.history(job["prompt_id"])
            state = history.get("status", {})
            if state.get("completed") and job.get("status") != state.get("status_str"):
                job["status"] = state.get("status_str", "completed")
                self.events.save_job(job); self.events.append(job_id, job["status"], {"prompt_id": job["prompt_id"]})
        return job
