"""Character bible (model sheet), LoRA edition.

The owner brings pictures of a character (usually made elsewhere). A LoRA is trained on them,
and every panel is drawn by Anima + that LoRA from content tags only (view, expression, outfit,
chibi, item). The LoRA carries the character and the look; the product never describes a style.
"""
from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageChops, ImageDraw, ImageFont


class Panel(NamedTuple):
    key: str
    section: str
    label: str
    kind: str      # full | face | item | chibi  (drives the canvas size)
    tags: str      # Danbooru-style content tags for Anima; no style words


PANELS: tuple[Panel, ...] = (
    Panel("turn_front", "TURNAROUND", "FRONT", "full", "full body, standing, front view, looking at viewer, arms at sides"),
    Panel("turn_34", "TURNAROUND", "3/4", "full", "full body, standing, three-quarter view, looking at viewer"),
    Panel("turn_side", "TURNAROUND", "SIDE", "full", "full body, standing, from side, profile, facing to the side"),
    Panel("turn_back", "TURNAROUND", "BACK", "full", "full body, standing, from behind, back view, facing away, back of head"),
    Panel("body_front", "BODY REFERENCE", "FRONT (leotard)", "full", "full body, standing, front view, plain white leotard, bodysuit, arms slightly out, bare legs, barefoot"),
    Panel("body_back", "BODY REFERENCE", "BACK (leotard)", "full", "full body, standing, from behind, plain white leotard, bodysuit, facing away, bare legs, barefoot"),
    Panel("ex_neutral", "EXPRESSIONS", "NEUTRAL", "face", "portrait, close-up, face, looking at viewer, expressionless, closed mouth"),
    Panel("ex_smile", "EXPRESSIONS", "SMILE", "face", "portrait, close-up, face, looking at viewer, smile, open mouth, happy, blush"),
    Panel("ex_angry", "EXPRESSIONS", "ANGRY", "face", "portrait, close-up, face, looking at viewer, angry, pout, anger vein, furrowed brow, puffed cheeks"),
    Panel("ex_sad", "EXPRESSIONS", "SAD", "face", "portrait, close-up, face, looking at viewer, sad, tears, crying, wavy mouth"),
    Panel("ex_surp", "EXPRESSIONS", "SURPRISE", "face", "portrait, close-up, face, looking at viewer, surprised, wide eyes, open mouth"),
    Panel("ex_shy", "EXPRESSIONS", "SHY", "face", "portrait, close-up, face, embarrassed, blush, looking away, nervous"),
    Panel("act_cast", "ACTION POSES", "CAST", "full", "full body, dynamic pose, casting spell, magic, outstretched arm, action"),
    Panel("act_run", "ACTION POSES", "RUN", "full", "full body, running, dynamic pose, motion"),
    Panel("act_jump", "ACTION POSES", "JUMP", "full", "full body, jumping, midair, dynamic pose"),
    Panel("cos_casual", "ALTERNATE COSTUMES", "CASUAL", "full", "full body, standing, front view, hoodie, denim shorts, sneakers, casual clothes"),
    Panel("cos_armor", "ALTERNATE COSTUMES", "ARMOR", "full", "full body, standing, front view, plate armor, knight, breastplate, pauldrons, gauntlets"),
    Panel("cos_dress", "ALTERNATE COSTUMES", "FORMAL", "full", "full body, standing, front view, ball gown, evening dress, long dress, elbow gloves"),
    Panel("chibi_big", "CHIBI / SD", "CHIBI", "chibi", "chibi, super deformed, full body, standing, looking at viewer, big head"),
    Panel("chibi_multi", "CHIBI / SD", "POSES", "chibi", "chibi, super deformed, full body, jumping, waving, happy"),
    Panel("item_head", "WARDROBE / ITEMS", "HEADWEAR", "item", "no humans, hair ornament, headwear, still life, object focus, close-up"),
    Panel("item_outfit", "WARDROBE / ITEMS", "OUTFIT", "item", "no humans, clothes, outfit, flat lay, still life, object focus"),
    Panel("item_shoes", "WARDROBE / ITEMS", "FOOTWEAR", "item", "no humans, shoes, boots, footwear, still life, object focus"),
)
COMMON = "simple background, white background"
NEGATIVE = "lowres, bad anatomy, bad hands, text, watermark, multiple views, reference sheet, collage"
SIZES = {"full": (832, 1216), "face": (1024, 1024), "item": (1024, 1024), "chibi": (1024, 1024)}

SECTIONS = (
    ("TURNAROUND", ("turn_front", "turn_34", "turn_side", "turn_back"), 440, True, (40, 2000)),
    ("BODY REFERENCE  (proportions / silhouette)", ("body_front", "body_back"), 440, True, (510, 1530)),
    ("EXPRESSIONS", ("ex_neutral", "ex_smile", "ex_angry", "ex_sad", "ex_surp", "ex_shy"), 210, False, (40, 2000)),
    ("ACTION POSES", ("act_cast", "act_run", "act_jump"), 400, True, (40, 2000)),
    ("ALTERNATE COSTUMES", ("cos_casual", "cos_armor", "cos_dress"), 440, True, (40, 2000)),
    ("CHIBI / SD", ("chibi_big", "chibi_multi"), 300, False, (40, 2000)),
    ("WARDROBE / ITEMS", ("item_head", "item_outfit", "item_shoes"), 280, False, (40, 2000)),
)
LABELS = {panel.key: panel.label for panel in PANELS}


def safe_name(value: str) -> str:
    """Make a deterministic path component without changing the displayed name."""
    result = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    if not result:
        raise ValueError("name must include a filesystem-safe character")
    return result[:80]


def subject_tag(char_desc: str) -> str:
    """The count/subject tag Anima expects; taken from the owner's description, never assumed."""
    description = f" {re.sub(r'[^a-z]+', ' ', char_desc.lower())} "
    if any(token in description for token in (" she ", " her ", "female", "woman", "girl")):
        return "1girl"
    if any(token in description for token in (" he ", " him ", "male", "man", "boy")):
        return "1boy"
    return "1other"


def panel_prompt(panel: Panel, trigger: str, char_desc: str) -> str:
    """trigger + subject + the panel's content tags. Item panels carry no subject."""
    subject = "" if panel.kind == "item" else subject_tag(char_desc)
    return ", ".join(part for part in (trigger, subject, panel.tags, COMMON) if part)


def size(panel: Panel) -> tuple[int, int]:
    return SIZES[panel.kind]


def copy_style(first: int, last: int) -> str:
    """For JoyAI edits that borrow a look from reference pictures (generate_variant / generate_image)."""
    span = f"image {first}" if first == last else f"images {first}-{last}"
    return (f" Render it in exactly the drawing style of {span}: copy only their shading, line work, "
            "lighting, eye rendering and level of detail; do NOT copy their backgrounds, poses, camera angle or composition")


NEG_IMAGE = "text, watermark, lowres, collage, grid, reference sheet, multiple views"


def image_prompt(prompt: str, style_count: int) -> str:
    body = (f"Draw a completely new picture: {prompt}. Do not copy the subjects, characters, poses "
            "or composition of the reference images")
    return body + copy_style(1, style_count) + "."


def _load(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content))


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def on_white(content: bytes) -> bytes:
    """Flatten any alpha onto white so the edit model sees the sprite, not a checkerboard."""
    image = _load(content).convert("RGBA")
    board = Image.new("RGBA", image.size, (255, 255, 255, 255))
    board.alpha_composite(image)
    return _png(board.convert("RGB"))


def _ink_mask(rgb: Image.Image, thr: int = 243) -> Image.Image:
    """White where any channel is darker than ``thr`` (= drawn pixels on a white sheet)."""
    channels = [band.point(lambda v: 255 if v < thr else 0) for band in rgb.convert("RGB").split()]
    return ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])


def crop_nonwhite(content: bytes, pad: int = 10) -> bytes:
    rgb = _load(content).convert("RGB")
    box = _ink_mask(rgb).getbbox()
    if box is None:
        return _png(rgb)
    left, top, right, bottom = box
    return _png(rgb.crop((max(left - pad, 0), max(top - pad, 0), min(right + pad, rgb.width), min(bottom + pad, rgb.height))))


def palette(rgb: Image.Image, k: int = 7) -> list[tuple[int, int, int]]:
    mask = _ink_mask(rgb).get_flattened_data()
    pixels = [px for px, keep in zip(rgb.convert("RGB").get_flattened_data(), mask) if keep]
    if not pixels:
        return [(200, 200, 200)] * k
    strip = Image.new("RGB", (len(pixels), 1))
    strip.putdata(pixels)
    pal = strip.quantize(colors=k).getpalette()
    colors = [tuple(pal[i * 3:i * 3 + 3]) for i in range(min(k, len(pal) // 3))]
    return colors + [colors[-1]] * (k - len(colors))


def _font(size_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size_px)


def contact_strip(paths: list[Path], height: int = 520, gap: int = 24) -> Image.Image:
    """The pictures the LoRA was trained on, side by side (the sheet's anchor row)."""
    tiles = []
    for path in paths:
        im = Image.open(path).convert("RGB")
        sc = height / im.height
        tiles.append(im.resize((max(1, int(im.width * sc)), height), Image.LANCZOS))
    strip = Image.new("RGB", (sum(t.width for t in tiles) + gap * (len(tiles) - 1), height), (255, 255, 255))
    x = 0
    for tile in tiles:
        strip.paste(tile, (x, 0)); x += tile.width + gap
    return strip


def compose_model_sheet(name: str, attr: str, panels: list[tuple[str, Path]], master: Path,
                        destination: Path) -> Path:
    """Compose the sectioned bible PNG: the training pictures, then every section, then the palette."""
    imgs = {key: Image.open(path).convert("RGB") for key, path in panels}
    W, BG, INK, MUT, LINE = 2040, (250, 250, 248), (38, 40, 46), (96, 100, 110), (210, 210, 212)
    sheet = Image.new("RGB", (W, 4400), BG)
    d = ImageDraw.Draw(sheet)
    fT, fSub, fSec, fLab = _font(46), _font(20), _font(26), _font(17)

    def row(keys, y, h, baseline, area, gap=16):
        x0, x1 = area
        cw = (x1 - x0) // len(keys)
        for i, key in enumerate(keys):
            if key not in imgs:
                continue
            im = imgs[key].copy()
            sc = min((cw - gap) / im.width, h / im.height)
            im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
            cx = x0 + cw * i + cw // 2
            py = (y + h - im.height) if baseline else (y + (h - im.height) // 2)
            sheet.paste(im, (cx - im.width // 2, py))
            tw = d.textlength(LABELS[key], font=fLab)
            d.text((cx - tw / 2, y + h + 6), LABELS[key], font=fLab, fill=MUT)
        return y + h + 30

    def sec(title, y):
        d.line([(40, y + 14), (W - 40, y + 14)], fill=LINE, width=2)
        d.rectangle([40, y + 2, 46, y + 26], fill=(70, 130, 200))
        d.text((58, y), title, font=fSec, fill=INK)
        return y + 44

    d.rectangle([0, 0, W, 96], fill=(28, 31, 38))
    d.text((40, 22), "CHARACTER BIBLE", font=fT, fill=(242, 242, 245))
    d.text((44, 72), f"{name}  ·  {attr}  ·  sprite-forge model sheet", font=fSub, fill=(165, 176, 192))
    y = sec("TRAINING PICTURES (LoRA material)", 120)
    m = Image.open(master).convert("RGB")
    sc = min((W - 80) / m.width, 520 / m.height)
    m = m.resize((int(m.width * sc), int(m.height * sc)), Image.LANCZOS)
    sheet.paste(m, (40 + (W - 80 - m.width) // 2, y))
    y += m.height + 24
    for title, keys, h, baseline, area in SECTIONS:
        y = sec(title, y)
        y = row(keys, y, h, baseline, area)
    y = sec("COLOR PALETTE", y)
    base = imgs.get("turn_front") or next(iter(imgs.values()))
    for i, col in enumerate(palette(base)):
        x = 40 + i * 150
        d.rectangle([x, y + 6, x + 130, y + 70], fill=col, outline=(120, 120, 120))
        d.text((x, y + 74), "#%02X%02X%02X" % col, font=_font(14), fill=MUT)
    y += 110
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.crop((0, 0, W, y)).save(destination, "PNG")
    return destination


def _b64(image: Image.Image, maxpx: int = 560) -> str:
    im = image.convert("RGB").copy()
    im.thumbnail((maxpx, maxpx), Image.LANCZOS)
    buf = BytesIO()
    im.save(buf, "JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def write_html(name: str, attr: str, panels: list[tuple[str, Path]], master: Path, destination: Path) -> Path:
    """Self-contained (base64) HTML bible with the same sections as the PNG."""
    imgs = {key: Image.open(path) for key, path in panels}
    css = ("body{margin:0;background:#15171c;color:#e7e9ee;font:15px/1.5 -apple-system,system-ui,sans-serif}"
           "header{background:#1f242b;padding:20px 28px;border-bottom:1px solid #333}"
           "h1{margin:0;font-size:26px}h2{font-size:15px;letter-spacing:.08em;color:#9aa3b2;margin:26px 28px 8px;"
           "border-left:4px solid #4682dc;padding-left:10px}.wrap{padding:0 20px 40px}"
           ".row{display:flex;flex-wrap:wrap;gap:14px;padding:0 8px}.cell{background:#1d2026;border:1px solid #333;"
           "border-radius:10px;padding:8px;text-align:center}.cell img{max-height:300px;max-width:240px;display:block;border-radius:6px;background:#fff}"
           ".cell span{font-size:12px;color:#9aa3b2;display:block;margin-top:6px}.master img{max-width:96%;border-radius:10px;background:#fff}"
           ".pal{display:flex;gap:10px;padding:0 16px;flex-wrap:wrap}.sw{width:88px}.sw div{height:48px;border-radius:6px;border:1px solid #555}"
           ".sw code{font-size:11px;color:#9aa3b2}")
    parts = [f"<!doctype html><meta charset=utf-8><title>{name} — character bible</title><style>{css}</style>",
             f"<header><h1>{name}</h1><div style='color:#9aa3b2'>{attr or 'character bible'} · sprite-forge</div></header><div class=wrap>",
             f"<h2>TRAINING PICTURES</h2><div class='row master'><div class=cell><img src='{_b64(Image.open(master), 1400)}'></div></div>"]
    for title, keys, *_ in SECTIONS:
        parts.append(f"<h2>{title}</h2><div class=row>")
        for key in keys:
            if key in imgs:
                parts.append(f"<div class=cell><img src='{_b64(imgs[key])}'><span>{LABELS[key]}</span></div>")
        parts.append("</div>")
    parts.append("<h2>COLOR PALETTE</h2><div class=pal>")
    base = imgs.get("turn_front") or next(iter(imgs.values()))
    for col in palette(base.convert("RGB")):
        hexc = "#%02X%02X%02X" % col
        parts.append(f"<div class=sw><div style='background:{hexc}'></div><code>{hexc}</code></div>")
    parts.append("</div></div>")
    destination.write_text("".join(parts), encoding="utf-8")
    return destination
