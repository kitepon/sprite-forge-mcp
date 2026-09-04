"""Use cases shared by the REST and MCP faces."""
from __future__ import annotations

import uuid
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
