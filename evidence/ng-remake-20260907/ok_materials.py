"""本人がOKとした生成6枚を、見直し済み元教材に足して学習する。NG画素は入れない。"""
from pathlib import Path
import shutil


USER_OK = (
    ("before", 602),
    ("after", 602),
    ("before", 604),
    ("after", 604),
    ("before", 608),
    ("after", 608),
)

OK_CAPTION = (
    "full body standing front view of a slim young adult woman with high silver twin-tails "
    "separately tied on the left and right, fading to pink at the ends, gold star hair ornaments, "
    "and violet eyes. She wears a white cropped top with a fluffy fur collar, gold trim and star "
    "ornaments, a layered white ruffled mini skirt, and white fur-trimmed knee-high boots against "
    "a simple white background"
)


def ok_source(root: Path, role: str, seed: int) -> Path:
    return root / "generated" / f"compare-{role}-{seed}.png"


def add_ok_materials(record: dict, panels: Path, root: Path) -> list[dict]:
    """OK生成を primary に足す。元教材の写しは変えず、NG画像は使わない。"""
    directory = panels / "primary"
    directory.mkdir(parents=True, exist_ok=True)
    trigger = record["trigger"]
    materials = []
    for role, seed in USER_OK:
        source = ok_source(root, role, seed)
        if not source.is_file():
            raise FileNotFoundError(f"本人OKの画像がありません: {source}")
        target = directory / f"ok-{seed:03d}-{role}.png"
        shutil.copyfile(source, target)
        caption = f"{trigger}, {OK_CAPTION}"
        target.with_suffix(".txt").write_text(caption, encoding="utf-8")
        materials.append({
            "reference": {"record_key": record["key"], "sample_index": None, "path": str(source)},
            "path": str(target), "caption": caption, "original_comment": "本人OK",
            "caption_en": OK_CAPTION, "appearance_ja": "正面全身。左右に分けて結んだツインテール。",
            "training_policy": {
                "reference": {"record_key": record["key"], "sample_index": None, "path": str(source)},
                "priority": "primary", "features": ["hair", "outfit", "subject"],
                "reason_ja": f"本人がOKとした seed {seed} の{role}",
            },
            "origin": "user_ok", "seed": seed, "role": role,
        })
    return materials
