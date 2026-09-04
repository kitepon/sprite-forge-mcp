"""Character bible (model sheet): master-sheet-anchored design, JoyAI edition.

Design (validated 2026-06-18 with Qwen-Image-Edit, carried over to JoyAI-Image-Edit-Plus):
  1. Draw ONE packed master sheet from the source in a single edit. All views are drawn together,
     so the sheet itself is the consistency anchor (the back view comes out right because a
     coordinated turnaround orients it).
  2. Feed that whole master sheet as the reference for every panel and ask for a SINGLE high-res
     figure of "the character in this reference sheet" with a kind-specific instruction
     (full body / back / leotard body / face close-up / item only / free).
  3. Compose the labelled bible from the panels (master included) plus a self-contained HTML.
     The panels double as LoRA training material.
"""
from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageChops, ImageDraw, ImageFont


MASTER_PROMPT = (
    "Create a comprehensive character reference model sheet of the exact character in image 1 on one white "
    "sheet: full-body front view, three-quarter view, side view and back view in a row; a row of "
    "facial expressions (neutral, smile, angry, sad, surprised); two action poses; same character "
    "throughout, consistent design, plain white background, model sheet layout")


def master_prompt(image_count: int = 1) -> str:
    return MASTER_PROMPT + style_clause(image_count) + "."
MASTER_SIZE = (1280, 1024)
NEG_MASTER = "extra different characters, text, watermark, lowres"


class Panel(NamedTuple):
    key: str
    section: str
    label: str
    kind: str      # full | back | body | face | item | free | chibi
    suffix: str    # may contain {p} for the possessive pronoun


PANELS: tuple[Panel, ...] = (
    Panel("turn_front", "TURNAROUND", "FRONT", "full", "standing straight facing forward, front view"),
    Panel("turn_34", "TURNAROUND", "3/4", "full", "three-quarter front view, standing"),
    Panel("turn_side", "TURNAROUND", "SIDE", "full", "exact side profile view, standing"),
    Panel("turn_back", "TURNAROUND", "BACK", "back", "turned with {p} back fully toward the viewer, rear view, only the back of {p} body and head visible, face hidden"),
    Panel("body_front", "BODY REFERENCE", "FRONT (leotard)", "body", "wearing only a plain sport leotard bodysuit, front view, neutral A-pose, exact body proportions"),
    Panel("body_back", "BODY REFERENCE", "BACK (leotard)", "body", "wearing only a plain sport leotard bodysuit, rear view from behind, face hidden, exact body proportions"),
    Panel("ex_neutral", "EXPRESSIONS", "NEUTRAL", "face", "a calm neutral anime expression, soft gentle eyes, relaxed closed mouth"),
    Panel("ex_smile", "EXPRESSIONS", "SMILE", "face", "a bright cheerful anime smile, happy sparkling eyes, soft blush, warm open smile"),
    Panel("ex_angry", "EXPRESSIONS", "ANGRY", "face", "a comedic anime angry expression, puffed-up cheeks, pouting, an anime anger-vein mark on the forehead, furrowed brows"),
    Panel("ex_sad", "EXPRESSIONS", "SAD", "face", "a teary anime sad expression, big watery welling eyes, glistening tears, downturned trembling mouth"),
    Panel("ex_surp", "EXPRESSIONS", "SURPRISE", "face", "a surprised anime expression, huge round sparkling wide eyes, small open mouth, shocked"),
    Panel("ex_shy", "EXPRESSIONS", "SHY", "face", "a shy embarrassed anime expression, heavy blush across the cheeks, eyes glancing away, bashful nervous look"),
    Panel("act_cast", "ACTION POSES", "CAST", "full", "dynamic action pose casting a powerful spell, dramatic angle"),
    Panel("act_run", "ACTION POSES", "RUN", "full", "running fast, dynamic"),
    Panel("act_jump", "ACTION POSES", "JUMP", "full", "jumping in the air, dynamic pose"),
    Panel("cos_casual", "ALTERNATE COSTUMES", "CASUAL", "full", "wearing a completely different outfit: an oversized casual hoodie with denim shorts and sneakers, everyday street clothes instead of {p} usual costume, standing"),
    Panel("cos_armor", "ALTERNATE COSTUMES", "ARMOR", "full", "wearing a completely different outfit: full ornate knight plate armor with metal breastplate, pauldrons, gauntlets and greaves instead of {p} usual costume, standing"),
    Panel("cos_dress", "ALTERNATE COSTUMES", "FORMAL", "full", "wearing a completely different outfit: a floor-length elegant evening ball gown with long skirt and gloves, a formal party dress instead of {p} usual costume, standing"),
    Panel("chibi_big", "CHIBI / SD", "CHIBI", "chibi", "exactly ONE chibi super-deformed version of that character: two heads tall, huge oversized head, tiny stubby body and limbs, big sparkling eyes, cute mascot proportions, a single figure alone"),
    Panel("chibi_multi", "CHIBI / SD", "POSES", "chibi", "a row of three chibi super-deformed versions of that character in different cute poses (waving, jumping, sitting), each two heads tall with a huge head and tiny body"),
    Panel("item_head", "WARDROBE / ITEMS", "HEADWEAR", "item", "the hair accessories and headwear (hair clips, ribbons, tiara or hat) worn by the character, drawn close-up as small isolated objects floating on white, no head, no hair"),
    Panel("item_outfit", "WARDROBE / ITEMS", "OUTFIT", "item", "the outfit garments worn by the character, laid out flat like a clothing catalog (empty top, skirt, sleeves, gloves), flat lay of empty clothes"),
    Panel("item_shoes", "WARDROBE / ITEMS", "FOOTWEAR", "item", "the footwear worn by the character, drawn as an isolated pair of shoes"),
)

# Panels reference the master SHEET, so always forbid reproducing the sheet layout.
NEG = "reference sheet, multiple views, grid, collage, multiple characters, extra people, text, watermark, lowres"
NEG_BACK = NEG + ", face, facing viewer, front view, eyes, looking at viewer, frontal"
NEG_ITEM = NEG + ", girl, person, character, body, face, head, hair, legs, arms, wearing, mannequin"
NEG_CHIBI = "reference sheet, grid, collage, extra people, realistic proportions, tall, full-size body, text, watermark, lowres"
NEG_COSTUME = NEG + ", idol costume, stage costume, original outfit, same outfit, frills, crop top"
SIZES = {"full": (832, 1216), "back": (832, 1216), "body": (832, 1216),
         "face": (1024, 1024), "item": (1024, 1024), "free": (1024, 1024), "chibi": (1024, 1024)}

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


def possessive_pronoun(char_desc: str) -> str:
    """Use the description when it supplies pronouns; never hard-code ``her``."""
    description = f" {re.sub(r'[^a-z]+', ' ', char_desc.lower())} "
    if any(token in description for token in (" she ", " her ", "female", "woman", "girl")):
        return "her"
    if any(token in description for token in (" he ", " him ", "male", "man", "boy")):
        return "his"
    return "their"


def _span(first: int, last: int) -> str:
    return f"image {first}" if first == last else f"images {first}-{last}"


def copy_style(first: int, last: int) -> str:
    """The rendering style is never written into the product: it is copied from reference
    pictures. This names which JoyAI reference images carry the look."""
    if first < 1 or last < first:
        raise ValueError("a style clause needs at least one reference image")
    return (f" Render it in exactly the drawing style of {_span(first, last)}: copy their shading, "
            "line work, lighting, eye rendering and level of detail")


def master_prompt(style_count: int = 0) -> str:
    """References: image 1 = the owner's source picture, images 2.. = extra style pictures.
    Without extras the source's own look is the style (usage 1); with extras the design comes
    from image 1 and the look from the extras (usage 2)."""
    if style_count:
        return MASTER_PROMPT + " Take the character design only from image 1." + copy_style(2, 1 + style_count) + "."
    return MASTER_PROMPT + copy_style(1, 1) + "."


NEG_IMAGE = "text, watermark, lowres, collage, grid, reference sheet, multiple views"


def from_bible_prompt(prompt: str, style_count: int = 0) -> str:
    """References: image 1 = master sheet, image 2 = source picture, images 3.. = extra style."""
    body = (f"Draw the exact character shown in images 1-2 (the character reference sheet and the "
            f"original picture): {prompt}. Keep that character's face, hair, outfit and colors")
    style = copy_style(3, 2 + style_count) if style_count else copy_style(1, 2)
    return body + style + "."


def image_prompt(prompt: str, style_count: int) -> str:
    """References: only style pictures. A brand-new picture that borrows nothing but the look."""
    body = (f"Draw a completely new picture: {prompt}. Do not copy the subjects, characters, poses "
            "or composition of the reference images")
    return body + copy_style(1, style_count) + "."


def instruction(panel: Panel, possessive: str, style_count: int = 0) -> str:
    """References: image 1 = master sheet (or the front figure for items), image 2 = the owner's
    source picture, images 3.. = extra style pictures. The character comes from images 1-2; the
    look from the extras when present, otherwise from images 1-2 themselves."""
    head = "Using the exact character shown in the character reference sheet in image 1 (the same person as image 2),"
    suffix = panel.suffix.format(p=possessive)
    style = copy_style(3, 2 + style_count) if style_count else copy_style(1, 2)
    if panel.kind == "face":
        body = (f"{head} draw a close-up headshot of ONLY that character's face with {suffix}, "
                "single face, head and shoulders, plain white background")
    elif panel.kind == "item":
        body = (f"Product illustration of ONLY {suffix} in image 1: no person, no body, no face, "
                "no character, objects only, centered on plain white background")
    elif panel.kind == "chibi":
        body = f"{head} draw {suffix}, keep {possessive} exact colors and outfit, plain white background"
    elif panel.kind == "free":
        body = f"{head} draw {suffix} of that character, keep {possessive} exact colors, plain white background"
    else:
        body = (f"{head} redraw ONLY that character as a SINGLE full-body figure {suffix}, "
                f"one character only, isolated, centered, keep {possessive} exact face hair outfit and colors, "
                "plain white background")
    return body + style + "."


def negative(panel: Panel) -> str:
    if panel.kind == "back" or "rear" in panel.suffix:
        return NEG_BACK
    if panel.kind == "item":
        return NEG_ITEM
    if panel.kind == "chibi":
        return NEG_CHIBI
    if panel.section == "ALTERNATE COSTUMES":
        return NEG_COSTUME
    return NEG


def size(panel: Panel) -> tuple[int, int]:
    return SIZES[panel.kind]


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


def compose_model_sheet(name: str, attr: str, panels: list[tuple[str, Path]], master: Path,
                        destination: Path) -> Path:
    """Compose the sectioned bible PNG: master reference, then every section, then the palette."""
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
    y = sec("MASTER REFERENCE (one-shot anchor)", 120)
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
             f"<h2>MASTER REFERENCE</h2><div class='row master'><div class=cell><img src='{_b64(Image.open(master), 1400)}'></div></div>"]
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
