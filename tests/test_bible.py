from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image

from backend import bible
from backend.bible import PANELS, instruction, possessive_pronoun
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
    assert len(job["panels"]) == len(PANELS) == 23
    assert all((tmp_path / "generated" / "bible_ember_mage_panels" / f"{panel.key}.png").is_file() for panel in PANELS)
    assert (tmp_path / "generated" / "bible_ember_mage_master.png").is_file()
    assert Image.open(job["sheet_path"]).width == 2040
    html = open(job["html_path"], encoding="utf-8").read()
    assert "MASTER REFERENCE" in html and "ALTERNATE COSTUMES" in html and "data:image/jpeg;base64," in html
    assert asyncio.run(service.bible_status(job["job_id"]))["status"] == "completed"
    assert len(comfy.submitted) == 24
    master, first_panel = comfy.submitted[0], comfy.submitted[1]
    assert master["20"]["inputs"]["prompt"] == bible.MASTER_PROMPT
    assert master["22"]["inputs"] == {"width": 1280, "height": 1024, "batch_size": 1}
    assert first_panel["10"]["inputs"]["image"] == "sf_bible_master_ember_mage.png"
    assert first_panel["21"]["inputs"]["prompt"] == bible.NEG


def test_bible_prompt_uses_description_pronouns_not_fixed_her():
    back = next(panel for panel in PANELS if panel.key == "turn_back")
    prompt = instruction(back, possessive_pronoun("he/him cloud knight"))
    assert "with his back fully toward the viewer" in prompt and "her" not in prompt.split()
    assert bible.negative(back) == bible.NEG_BACK
    assert "close-up headshot" in instruction(next(p for p in PANELS if p.kind == "face"), "their")
    assert "no person, no body" in instruction(next(p for p in PANELS if p.kind == "item"), "their")
