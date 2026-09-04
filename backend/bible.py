"""Character-bible panel prompts and Pillow composition helpers."""
from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw


PANEL_SPECS = (
    ("turn_front", "front view"), ("turn_back", "back view"),
    ("turn_left", "left profile"), ("turn_right", "right profile"),
    ("turn_front_left", "front-left three-quarter view"),
    ("turn_front_right", "front-right three-quarter view"),
    ("turn_back_left", "back-left three-quarter view"),
    ("turn_back_right", "back-right three-quarter view"),
    ("expression_neutral", "neutral expression"), ("expression_happy", "happy expression"),
    ("expression_angry", "angry expression"), ("expression_sad", "sad expression"),
    ("expression_surprised", "surprised expression"), ("expression_determined", "determined expression"),
    ("outfit_default", "default outfit"), ("outfit_travel", "travel outfit"),
    ("outfit_formal", "formal outfit"), ("chibi", "chibi full-body version"),
)


def safe_name(value: str) -> str:
    """Make a deterministic path component without changing the displayed name."""
    result = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    if not result:
        raise ValueError("name must include a filesystem-safe character")
    return result[:80]


def possessive_pronoun(char_desc: str) -> str:
    """Use the description when it supplies pronouns; never hard-code ``her``."""
    description = re.sub(r"[^a-z]+", " ", char_desc.lower())
    if any(token in description for token in (" she ", " her ", "female", "woman", "girl")):
        return "her"
    if any(token in description for token in (" he ", " him ", "male", "man", "boy")):
        return "his"
    return "their"


def panel_prompt(name: str, char_desc: str, attr: str, detail: str) -> str:
    possessive = possessive_pronoun(f" {char_desc} ")
    return (
        f"Create a clean character-design reference for {name}: {detail}. "
        f"Character description: {char_desc}. Attributes: {attr}. "
        f"Keep {possessive} identity, costume details, and proportions consistent with the reference image. "
        "Single character, full body where applicable, plain light background, no text or labels."
    )


def compose_model_sheet(panels: list[tuple[str, Path]], destination: Path) -> Path:
    """Compose labelled thumbnails into a single PNG model sheet."""
    thumb_size, label_height, columns = 256, 30, 4
    rows = (len(panels) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * thumb_size, rows * (thumb_size + label_height)), "#f7f4ee")
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(panels):
        image = Image.open(path).convert("RGBA")
        image.thumbnail((thumb_size - 12, thumb_size - 12))
        x = (index % columns) * thumb_size + (thumb_size - image.width) // 2
        y = (index // columns) * (thumb_size + label_height) + (thumb_size - image.height) // 2
        sheet.alpha_composite(image, (x, y))
        draw.text(((index % columns) * thumb_size + 8, (index // columns) * (thumb_size + label_height) + thumb_size + 7),
                  label.replace("_", " "), fill="#222222")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, "PNG")
    return destination


def write_html(name: str, panels: list[tuple[str, Path]], destination: Path) -> Path:
    """Write a self-contained visual index so a bible can be reviewed offline."""
    cards = []
    for label, path in panels:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        cards.append(
            f'<figure><img alt="{label}" src="data:image/png;base64,{encoded}"><figcaption>{label}</figcaption></figure>'
        )
    destination.write_text(
        "<!doctype html><meta charset=utf-8><title>" + name + " character bible</title>"
        "<style>body{font-family:system-ui;background:#f7f4ee;color:#222;margin:2rem}"
        "main{display:grid;grid-template-columns:repeat(4,minmax(12rem,1fr));gap:1rem}"
        "figure{margin:0;background:white;padding:.5rem;box-shadow:0 1px 4px #aaa}img{width:100%;height:auto}"
        "figcaption{text-transform:capitalize;padding:.4rem}</style>"
        f"<h1>{name} character bible</h1><main>{''.join(cards)}</main>",
        encoding="utf-8",
    )
    return destination
