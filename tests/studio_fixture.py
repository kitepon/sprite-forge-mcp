"""Local browser fixture, never uses the GPU or a persistent user cache.

Run: uv run python -m tests.studio_fixture [directory-of-reference-pngs]
The optional directory is read-only. All changes go into a new temporary directory.
"""
import asyncio
from pathlib import Path
import shutil
import sys
import tempfile

import uvicorn
from backend import app as module, bible, box
from backend.events import EventStore
from backend.services import Services

root = Path(tempfile.mkdtemp(prefix="sprite-studio-fixture-"))
art = sorted(Path(sys.argv[1]).glob("*.png")) if len(sys.argv) > 1 else [Path(".github/example-output.png").resolve()]


class Comfy:
    base_url = "http://fixture.invalid"
    client = None

    async def stats(self):
        return {"devices": [{"name": "Fixture GPU"}]}

    async def post(self, *_args, **_kwargs):
        return None

    async def submit(self, graph, job_id):
        if "fixture-fail" in str(graph):
            raise RuntimeError("Fixture: GPU execution failed")
        await asyncio.sleep(1.2)
        return "fixture-prompt"

    async def history(self, _prompt_id):
        return {"status": {"completed": True}, "outputs": {"1": {"images": [{"filename": "fixture.png"}]}}}

    async def upload(self, _content, name):
        return name


comfy = Comfy()
comfy.client = comfy
module.services.__dict__.update(Services(comfy=comfy, events=EventStore(root / "events.ndjson", root / "jobs"),
    generated_root=root / "generated", uploads_root=root / "uploads", characters_root=root / "characters", styles_root=root / "styles").__dict__)
service = module.services


async def view(_image):
    return bible.on_white(art[0].read_bytes())


async def copy(*_args, **_kwargs):
    return 0, ""


async def training(*args, **kwargs):
    for step in range(1, 4):
        await asyncio.sleep(3)
        yield f"steps: {step}/3 [00:03<00:00]"


service._view = view
box.copy_tree_to_box = copy
box.copy_to_box = copy
box.stream_training = training


async def setup():
    await service.create_character("Bell", "she/her, idol", lora_name="fixture.safetensors")
    await service.create_character("ベル", "she/her, silver twin-tail idol")
    await service.create_style("淡い水彩", "やわらかい線と透明な色")
    for name in ["Bell", "ベル"]:
        for path in art[:4]:
            await service.add_samples(name, str(path), "white and gold outfit, portrait")
    for path in art[:2]:
        await service.add_style_samples("淡い水彩", str(path), "portrait, soft light")
    record = service._load_style("淡い水彩"); record["lora_name"] = "fixture-style.safetensors"; service._save_style(record)
    service.generated_root.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(art):
        destination = service.generated_root / f"fixture-{index}.png"
        shutil.copyfile(path, destination)
        service.events.save_job({"job_id": f"fixture-{index}", "kind": "from_bible", "name": "Bell", "status": "completed", "path": str(destination), "prompt": "waving, white outfit", "seed": index})
    print(f"Fixture data: {root}", flush=True)


if __name__ == "__main__":
    asyncio.run(setup())
    uvicorn.run(module.app, host="127.0.0.1", port=18766, log_level="warning")
