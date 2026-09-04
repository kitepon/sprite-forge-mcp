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

    stale = tmp_path / "generated" / "bible_ember_mage_panels" / "expression_happy.png"
    stale.parent.mkdir(parents=True); stale.write_bytes(png())
    style_a, style_b = tmp_path / "style_a.png", tmp_path / "style_b.png"
    style_a.write_bytes(png("#112233")); style_b.write_bytes(png("#445566"))
    job = asyncio.run(service.generate_character_bible(str(source), "ember mage", "they/them fire mage", "red coat",
                                                       style_refs=f"{style_a}, {style_b}"))
    assert not stale.exists()
    assert job["style_refs"] == [str(style_a), str(style_b)]

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
    assert master["20"]["inputs"]["prompt"] == bible.MASTER_PROMPT + bible.style_clause(2) + "."
    assert "images 2-3" in master["20"]["inputs"]["prompt"]
    assert master["20"]["inputs"]["images.image1"] == ["11", 0] and master["20"]["inputs"]["images.image2"] == ["12", 0]
    assert first_panel["11"]["inputs"]["image"] == "sf_bible_style_ember_mage_0.png"
    assert master["22"]["inputs"] == {"width": 1280, "height": 1024, "batch_size": 1}
    assert first_panel["10"]["inputs"]["image"] == "sf_bible_master_ember_mage.png"
    assert first_panel["21"]["inputs"]["prompt"] == bible.NEG
    item_index = next(i for i, panel in enumerate(PANELS) if panel.kind == "item")
    assert comfy.submitted[1 + item_index]["10"]["inputs"]["image"] == "sf_bible_front_ember_mage.png"


def test_bible_prompt_uses_description_pronouns_not_fixed_her():
    back = next(panel for panel in PANELS if panel.key == "turn_back")
    prompt = instruction(back, possessive_pronoun("he/him cloud knight"))
    assert "with his back fully toward the viewer" in prompt and "her" not in prompt.split()
    assert bible.negative(back) == bible.NEG_BACK
    assert "close-up headshot" in instruction(next(p for p in PANELS if p.kind == "face"), "their")
    item = next(p for p in PANELS if p.kind == "item")
    assert "no person, no body" in instruction(item, "their") and bible.negative(item) == bible.NEG_ITEM
    chibi = next(p for p in PANELS if p.key == "chibi_big")
    assert "two heads tall" in instruction(chibi, "their") and bible.negative(chibi) == bible.NEG_CHIBI
    for key in ("cos_casual", "cos_armor", "cos_dress"):
        panel = next(p for p in PANELS if p.key == key)
        assert "{p}" not in instruction(panel, "their") and bible.negative(panel) == bible.NEG_COSTUME


def test_style_comes_only_from_references_never_from_the_product():
    face = next(p for p in PANELS if p.kind == "face")
    bare = instruction(face, "their")
    for word in ("cel", "anime style", "high detail", "painterly", "glossy"):
        assert word not in bare
    assert bible.style_clause(0) == "" and bare.endswith("plain white background.")
    assert "drawing style of image 2:" in instruction(face, "their", 1)
    assert "images 2-6" in bible.master_prompt(5)
