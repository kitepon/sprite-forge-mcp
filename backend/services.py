"""Use cases shared by the REST and MCP faces."""
from __future__ import annotations

import uuid
import asyncio
import shutil
import struct
import zlib
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from . import bible
from . import workflows
from . import box
from .config import BOX_LORAS, BOX_SSH
from .comfy import Comfy
from .config import CACHE
from .events import EventStore


class Services:
    def __init__(self, comfy: Comfy | None = None, events: EventStore | None = None,
                 generated_root: Path | None = None):
        self.comfy, self.events = comfy or Comfy(), events or EventStore()
        self.generated_root = generated_root or CACHE / "generated"

    async def gpu_status(self) -> dict[str, Any]:
        self._record_call("gpu_status")
        return await self.comfy.stats()

    async def start_base(self, prompt: str, seed: int) -> dict[str, Any]:
        return await self._start("base", workflows.anima_base(prompt, seed), {"seed": seed}, "generate_base")

    async def generate_sprite(self, prompt: str, count: int = 4, seed: int = 1,
                              lora_name: str | None = None, lora_trigger: str | None = None,
                              pose_image: str | None = None, turbo: bool = True) -> dict[str, Any]:
        """Generate RGBA candidates through Anima then ToonOut and cache them."""
        if not 1 <= count <= 8:
            raise ValueError("count must be between 1 and 8")
        job_id = str(uuid.uuid4())
        final_prompt = " ".join(part for part in (lora_trigger, prompt) if part)
        self.events.save_job({"job_id": job_id, "kind": "sprite", "status": "running"})
        self._record_call("generate_sprite", job_id, {"count": count, "seed": seed,
                                                        "lora_name": lora_name, "turbo": turbo})
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
            path = self.generated_root / f"{job_id}-{index}.png"
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
        self._record_call("list_loras")
        response = await self.comfy.client.get(f"{self.comfy.base_url}/object_info")
        response.raise_for_status()
        required = response.json().get("LoraLoader", {}).get("input", {}).get("required", {})
        return list(required.get("lora_name", [[]])[0])

    async def generate_character_bible(self, source: str, name: str, char_desc: str,
                                       attr: str = "", seed: int = 1) -> dict[str, Any]:
        """Master-sheet-anchored bible: one packed master edit, then one high-res panel per spec,
        each referencing the whole master sheet (see backend/bible.py)."""
        source_path = self._source_path(source)
        job_id = str(uuid.uuid4())
        key = bible.safe_name(name)
        panel_root = self.generated_root / f"bible_{key}_panels"
        job = {"job_id": job_id, "kind": "character_bible", "status": "queued", "name": name,
               "source": str(source_path), "panels_dir": str(panel_root)}
        self.events.save_job(job)
        self._record_call("generate_character_bible", job_id, {"name": name, "seed": seed})
        self.events.append(job_id, "queued", {"name": name, "source": str(source_path)})
        try:
            possessive = bible.possessive_pronoun(char_desc)
            if panel_root.exists():
                shutil.rmtree(panel_root)  # the panel set is also LoRA material: no stale panels from an earlier run
            source_upload = await self.comfy.upload(bible.on_white(source_path.read_bytes()), f"sf_bible_src_{key}.png")
            job.update(status="generating master sheet")
            self.events.save_job(job)
            master = bible.on_white(await self._run_edit(job_id, workflows.joy_edit(
                source_upload, bible.MASTER_PROMPT, seed, negative=bible.NEG_MASTER, size=bible.MASTER_SIZE)))
            master_path = self._write_generated(f"bible_{key}_master.png", master)
            master_upload = await self.comfy.upload(master, f"sf_bible_master_{key}.png")
            job["master_path"] = str(master_path)
            self.events.append(job_id, "master_completed", {"path": str(master_path)})
            panels: list[tuple[str, Path]] = []
            front_upload = master_upload  # item panels reference the single front figure once it exists
            for index, panel in enumerate(bible.PANELS):
                job.update(status="generating panels", panel=panel.key, completed_panels=index)
                self.events.save_job(job)
                reference = front_upload if panel.kind == "item" else master_upload
                content = await self._run_edit(job_id, workflows.joy_edit(
                    reference, bible.instruction(panel, possessive), seed + 100 + index,
                    negative=bible.negative(panel), size=bible.size(panel)))
                panel_path = panel_root / f"{panel.key}.png"
                panel_path.parent.mkdir(parents=True, exist_ok=True)
                cropped = bible.crop_nonwhite(content)
                panel_path.write_bytes(cropped)
                if panel.key == "turn_front":
                    front_upload = await self.comfy.upload(cropped, f"sf_bible_front_{key}.png")
                panels.append((panel.key, panel_path))
                self.events.append(job_id, "panel_completed", {"panel": panel.key, "path": str(panel_path)})
            sheet = bible.compose_model_sheet(name, attr, panels, master_path, self.generated_root / f"bible_{key}.png")
            html = bible.write_html(name, attr, panels, master_path, self.generated_root / f"bible_{key}.html")
            job.update(status="completed", completed_panels=len(panels),
                       panels=[str(path) for _, path in panels], sheet_path=str(sheet), html_path=str(html))
            self.events.save_job(job)
            self.events.append(job_id, "completed", {"sheet_path": str(sheet), "html_path": str(html)})
            return job
        except Exception as error:
            job.update(status="failed", error=str(error))
            self.events.save_job(job)
            self.events.append(job_id, "failed", {"error": str(error)})
            raise

    async def _run_edit(self, job_id: str, graph: dict[str, Any]) -> bytes:
        prompt_id = await self.comfy.submit(graph, job_id)
        return await self._view(self._first_image(await self._history_until_done(prompt_id)))

    async def bible_status(self, job_id: str) -> dict[str, Any]:
        return await self._status(job_id, "bible_status")

    async def train_character_lora(self, bible_name: str, trigger: str = "sprite_subject", steps: int = 12) -> dict[str, Any]:
        if not 1 <= steps <= 200:
            raise ValueError("steps must be between 1 and 200")
        panels = self.generated_root / f"bible_{bible.safe_name(bible_name)}_panels"
        if not panels.is_dir():
            raise FileNotFoundError(f"bible panels not found: {panels}")
        job_id, stem = str(uuid.uuid4()), f"{bible.safe_name(bible_name)}_{uuid.uuid4().hex[:8]}"
        remote_root = r"C:\sf"
        job = {"job_id": job_id, "kind": "lora_train", "status": "queued", "bible_name": bible_name,
               "trigger": trigger, "steps": steps, "progress": {"step": 0, "total": steps}, "lora_name": f"{stem}.safetensors"}
        self.events.save_job(job); self._record_call("train_character_lora", job_id, {"bible_name": bible_name, "steps": steps})
        self.events.append(job_id, "queued", {"bible_name": bible_name, "steps": steps})
        for image in panels.glob("*.png"):
            image.with_suffix(".txt").write_text(f"{trigger}, character reference panel", encoding="utf-8")
        code, output = await box.copy_tree_to_box(panels, remote_root, ssh=BOX_SSH)
        if code: raise RuntimeError(output)
        toml = self.generated_root / f"{job_id}-dataset.toml"
        toml_path = f"{remote_root.replace(chr(92), '/')}/{panels.name}"
        toml.write_text(f'[[datasets]]\nresolution = 1024\nbatch_size = 1\nenable_bucket = true\n[[datasets.subsets]]\nimage_dir = "{toml_path}"\ncaption_extension = ".txt"\nnum_repeats = 1\n', encoding="utf-8")
        code, output = await box.copy_to_box(toml, rf"{remote_root}\{job_id}-dataset.toml", ssh=BOX_SSH)
        if code: raise RuntimeError(output)
        await self.comfy.client.post(f"{self.comfy.base_url}/free", json={})
        job.update(status="running"); self.events.save_job(job); self.events.append(job_id, "running", {})
        async for line in box.stream_training(rf"{remote_root}\{job_id}-dataset.toml", stem,
                                              r"C:\Users\kite_\ComfyUI\ComfyUI\models\diffusion_models\anima-base-v1.0.safetensors",
                                              r"C:\Users\kite_\ComfyUI\ComfyUI\models\text_encoders\qwen_3_06b_base.safetensors",
                                              r"C:\Users\kite_\ComfyUI\ComfyUI\models\vae\qwen_image_vae.safetensors", steps, BOX_LORAS, ssh=BOX_SSH):
            match = re.search(r"(?:step|Step)\s*(\d+)\s*/\s*(\d+)", line)
            if match:
                job["progress"] = {"step": int(match.group(1)), "total": int(match.group(2))}
                self.events.save_job(job); self.events.append(job_id, "progress", job["progress"])
        job.update(status="completed", progress={"step": steps, "total": steps})
        self.events.save_job(job); self.events.append(job_id, "completed", {"lora_name": job["lora_name"]})
        return job

    async def train_status(self, job_id: str) -> dict[str, Any]:
        return await self._status(job_id, "train_status")

    async def list_jobs(self) -> list[dict[str, Any]]:
        return self.events.list_jobs()

    async def make_mask(self, image_id: str, prompt: str = "character", points: str | None = None) -> dict[str, Any]:
        """Produce a SAM 3.1 mask artifact for a cached image."""
        source, job_id = self._source_path(image_id), str(uuid.uuid4())
        self._record_call("make_mask", job_id, {"prompt": prompt})
        uploaded = await self.comfy.upload(source.read_bytes(), source.name)
        prompt_id = await self.comfy.submit(workflows.sam3_mask(uploaded, prompt, points), job_id)
        content = self._as_rgba_png(await self._view(self._first_image(await self._history_until_done(prompt_id))))
        path = self._write_generated(f"{job_id}-mask.png", content)
        job = {"job_id": job_id, "kind": "mask", "status": "completed", "source": str(source),
               "path": str(path), "prompt_id": prompt_id, **self._measure_rgba_png(content)}
        self.events.save_job(job); self.events.append(job_id, "completed", {"path": str(path)})
        return job

    async def generate_variant(self, base_id: str, prompt: str, mask_id: str | None = None,
                               seed: int = 1) -> dict[str, Any]:
        """Edit with JoyAI and restore base pixels outside an optional SAM mask."""
        base, job_id = self._source_path(base_id), str(uuid.uuid4())
        self._record_call("generate_variant", job_id, {"mask_id": mask_id, "seed": seed})
        uploaded = await self.comfy.upload(base.read_bytes(), base.name)
        prompt_id = await self.comfy.submit(workflows.joy_edit(uploaded, prompt, seed), job_id)
        edited = self._as_rgba_png(await self._view(self._first_image(await self._history_until_done(prompt_id))))
        if mask_id:
            edited = self._restore_outside_mask(base.read_bytes(), edited, self._source_path(mask_id).read_bytes())
        path = self._write_generated(f"{job_id}-variant.png", edited)
        base_measure, variant_measure = self._measure_rgba_png(base.read_bytes()), self._measure_rgba_png(edited)
        job = {"job_id": job_id, "kind": "variant", "status": "completed", "base": str(base),
               "path": str(path), "mask": mask_id, "prompt_id": prompt_id,
               **variant_measure, "bbox_center_delta": self._bbox_center_delta(base_measure["bbox"], variant_measure["bbox"])}
        self.events.save_job(job); self.events.append(job_id, "completed", {"path": str(path)})
        return job

    async def make_transparent(self, image_id: str) -> dict[str, Any]:
        source, job_id = self._source_path(image_id), str(uuid.uuid4())
        self._record_call("make_transparent", job_id)
        uploaded = await self.comfy.upload(source.read_bytes(), source.name)
        prompt_id = await self.comfy.submit(workflows.toonout(uploaded), job_id)
        content = self._as_rgba_png(await self._view(self._first_image(await self._history_until_done(prompt_id))))
        path = self._write_generated(f"{job_id}-transparent.png", content)
        job = {"job_id": job_id, "kind": "transparent", "status": "completed", "source": str(source),
               "path": str(path), "prompt_id": prompt_id, **self._measure_rgba_png(content)}
        self.events.save_job(job); self.events.append(job_id, "completed", {"path": str(path)})
        return job

    async def pixelize(self, image_id: str, block: int = 8, posterize: int = 0) -> dict[str, Any]:
        if not 1 <= block <= 128 or not 0 <= posterize <= 8:
            raise ValueError("block must be 1..128 and posterize must be 0..8")
        source, job_id = self._source_path(image_id), str(uuid.uuid4())
        self._record_call("pixelize", job_id, {"block": block, "posterize": posterize})
        content = self._pixelize_png(source.read_bytes(), block, posterize)
        path = self._write_generated(f"{job_id}-pixel.png", content)
        job = {"job_id": job_id, "kind": "pixelize", "status": "completed", "source": str(source),
               "path": str(path), "block": block, "posterize": posterize, **self._measure_rgba_png(content)}
        self.events.save_job(job); self.events.append(job_id, "completed", {"path": str(path)})
        return job

    def _source_path(self, source: str) -> Path:
        candidate = Path(source)
        if candidate.is_file():
            return candidate
        direct = self.generated_root / f"{source}.png"
        if direct.is_file():
            return direct
        matches = sorted(self.generated_root.glob(f"{source}*.png"))
        if len(matches) == 1:
            return matches[0]
        raise FileNotFoundError(f"character-bible source not found: {source}")

    def _write_generated(self, name: str, content: bytes) -> Path:
        path = self.generated_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    @staticmethod
    def _as_rgba_png(content: bytes) -> bytes:
        image = Image.open(BytesIO(content)).convert("RGBA")
        output = BytesIO(); image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _bbox_center_delta(before: dict[str, int] | None, after: dict[str, int] | None) -> dict[str, float] | None:
        if not before or not after:
            return None
        center = lambda box: ((box["left"] + box["right"]) / 2, (box["top"] + box["bottom"]) / 2)
        bx, by = center(before); ax, ay = center(after)
        return {"x": ax - bx, "y": ay - by}

    @staticmethod
    def _restore_outside_mask(base: bytes, edited: bytes, mask: bytes) -> bytes:
        base_image = Image.open(BytesIO(base)).convert("RGBA")
        edit_image = Image.open(BytesIO(edited)).convert("RGBA").resize(base_image.size)
        mask_image = Image.open(BytesIO(mask)).convert("L").resize(base_image.size)
        output = BytesIO(); Image.composite(edit_image, base_image, mask_image).save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _pixelize_png(content: bytes, block: int, posterize: int) -> bytes:
        image = Image.open(BytesIO(content)).convert("RGBA")
        small = image.resize((max(1, image.width // block), max(1, image.height // block)), Image.Resampling.NEAREST)
        output = small.resize(image.size, Image.Resampling.NEAREST)
        if posterize:
            alpha = output.getchannel("A")
            output = ImageOps.posterize(output.convert("RGB"), posterize).convert("RGBA")
            output.putalpha(alpha)
        encoded = BytesIO(); output.save(encoded, format="PNG")
        return encoded.getvalue()

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
        return await self._start("edit", workflows.joy_edit(upload, prompt, seed), {"input": upload, "seed": seed}, "start_edit")

    async def start_matte(self, image: bytes, name: str) -> dict[str, Any]:
        upload = await self.comfy.upload(image, name)
        return await self._start("matte", workflows.toonout(upload), {"input": upload}, "start_matte")

    async def start_damage(self, image: bytes, name: str, prompt: str, seed: int) -> dict[str, Any]:
        upload = await self.comfy.upload(image, name)
        return await self._start("damage", workflows.damage(upload, prompt, seed), {"input": upload, "seed": seed}, "start_damage")

    async def _start(self, kind: str, workflow: dict[str, Any], payload: dict[str, Any], tool: str) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        job = {"job_id": job_id, "kind": kind, "status": "queued", **payload}
        self.events.save_job(job); self._record_call(tool, job_id, payload); self.events.append(job_id, "queued", payload)
        prompt_id = await self.comfy.submit(workflow, job_id)
        job.update(status="submitted", prompt_id=prompt_id)
        self.events.save_job(job); self.events.append(job_id, "submitted", {"prompt_id": prompt_id})
        return job

    async def status(self, job_id: str) -> dict[str, Any]:
        return await self._status(job_id, "job_status")

    async def _status(self, job_id: str, tool: str) -> dict[str, Any]:
        self._record_call(tool, job_id)
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

    def _record_call(self, tool: str, job_id: str | None = None, payload: dict[str, Any] | None = None) -> str:
        """Record a public Services invocation before it performs work."""
        invocation_id = job_id or str(uuid.uuid4())
        self.events.append(invocation_id, "tool_called", {"tool": tool, **(payload or {})})
        return invocation_id
