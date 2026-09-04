from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image

from backend.bible import PANEL_SPECS, panel_prompt
from backend.events import EventStore
from backend.services import Services


def png(color: str = "#44aaff") -> bytes:
    image = Image.new("RGBA", (24, 32), color)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


class ComfyFixture:
    def __init__(self):
        self.submitted: list[dict] = []

    async def upload(self, content, name):
        assert content.startswith(b"\x89PNG")
        return name

    async def submit(self, workflow, client_id):
        self.submitted.append(workflow)
        return f"prompt-{len(self.submitted)}"

    async def history(self, prompt_id):
        return {"status": {"completed": True, "status_str": "success"},
                "outputs": {"25": {"images": [{"filename": f"{prompt_id}.png"}]}}}


async def view_image(_image):
    return png()


def test_bible_generates_all_panels_model_sheet_and_embedded_html(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(png("#ff8844"))
    comfy = ComfyFixture()
    service = Services(comfy=comfy, events=EventStore(tmp_path / "events.ndjson", tmp_path / "jobs"),
                       generated_root=tmp_path / "generated")
    service._view = view_image

    job = asyncio.run(service.generate_character_bible(str(source), "ember mage", "they/them fire mage", "red coat"))

    assert job["status"] == "completed"
    assert len(job["panels"]) == len(PANEL_SPECS) == 18
    assert all((tmp_path / "generated" / "bible_ember_mage_panels" / f"{label}.png").is_file()
               for label, _ in PANEL_SPECS)
    assert Image.open(job["sheet_path"]).size == (1024, 1430)
    assert "data:image/png;base64," in open(job["html_path"], encoding="utf-8").read()
    assert asyncio.run(service.bible_status(job["job_id"]))["status"] == "completed"
    assert len(comfy.submitted) == 18


def test_bible_prompt_uses_description_pronouns_not_fixed_her():
    prompt = panel_prompt("Rin", "he/him cloud knight", "silver armor", "front view")
    assert "his identity" in prompt
    assert "her identity" not in prompt
