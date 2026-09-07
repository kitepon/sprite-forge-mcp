"""NG指摘から、元教材の採否と説明を見直す入力と差分。"""
from __future__ import annotations

from copy import deepcopy
from html import escape
import json
from pathlib import Path
from urllib.parse import quote

from .intent import Proposal, validate_proposal


def ng_pictures(pictures: list[dict]) -> list[dict]:
    """NGだけを残す。未判定とOKは教材にも解釈対象にもしない。"""
    selected = []
    for picture in pictures:
        review = picture.get("review") or picture
        if review.get("rating") != "ng":
            continue
        selected.append(picture)
    if not selected:
        raise ValueError("作り直しにはNGの画像が必要です。未判定の画像は使いません。")
    return selected


def representative_ng(pictures: list[dict]) -> list[dict]:
    """同じ指摘原文の重複は代表1枚だけ添付する。全件の原文はng_reviewsに残す。"""
    attached = []
    seen = set()
    for picture in ng_pictures(pictures):
        review = picture.get("review") or picture
        key = (review.get("comment") or "").strip() or picture.get("id")
        if key in seen:
            continue
        seen.add(key)
        attached.append(picture)
    return attached


def revision_packet(record: dict, pictures: list[dict], source_comments: dict[str, str] | None = None) -> dict:
    """解釈器へ渡す入力。referencesは元教材だけ。"""
    selected = ng_pictures(pictures)
    attached = representative_ng(pictures)
    references = [{"record_key": record["key"], "sample_index": sample["index"], "path": sample["path"]}
                  for sample in record["samples"]]
    attached_index = {item.get("id"): len(references) + offset for offset, item in enumerate(attached)}
    comments = source_comments or {}
    text = "\n\n".join(f"{label}: {comments[stage]}" for stage, label in
                       (("samples", "参考画像への希望"), ("training", "学習への補足")) if comments.get(stage, "").strip())
    return {
        "stage": "material_revision",
        "record_kind": "character",
        "record_description": record.get("char_desc", ""),
        "original_comment": text,
        "existing_settings": {"lora_name": record.get("lora_name", "")},
        "references": references,
        "image_comments": [sample.get("caption", "") for sample in record["samples"]],
        "base_conditions": deepcopy(record.get("intent_conditions") or {}),
        "training_captions": [sample.get("training_caption") for sample in record["samples"]],
        "training_selection": deepcopy(record.get("training_selection")),
        "ng_reviews": [{"id": picture.get("id"), "rating": "ng",
                        "comment": (picture.get("review") or picture).get("comment") or "",
                        "meaning": (picture.get("review") or picture).get("meaning"),
                        "attachment_index": attached_index.get(picture.get("id"))}
                       for picture in selected],
        "learning_request": True,
    }


def revision_images(record: dict, pictures: list[dict]) -> list[bytes]:
    paths = [Path(sample["path"]) for sample in record["samples"]] + [
        Path(picture["path"]) for picture in representative_ng(pictures)]
    return [path.read_bytes() for path in paths]


def validate_revision(proposal: Proposal, packet: dict) -> None:
    """学習提案の契約に加え、NG画像を教材参照へ混ぜないことを確認する。"""
    job = {**packet, "stage": "training"}
    validate_proposal(proposal, job)
    allowed = {item["path"] for item in packet["references"]}
    for item in proposal.training_samples or []:
        if item.reference.path not in allowed:
            raise ValueError("NG画像を学習教材へ追加しないでください。")
    for item in proposal.observations:
        if item.reference.path not in allowed:
            raise ValueError("NG画像の内容を元教材の観察へ転記しないでください。")
    if any(not item.get("id") for item in packet["ng_reviews"]):
        raise ValueError("NG画像の識別子がありません。")
    trained = {item.reference.sample_index for item in proposal.training_samples or [] if item.priority != "reference"}
    observed = {item.reference.sample_index for item in proposal.observations}
    if not trained <= observed:
        raise ValueError("教材にする画像すべての説明が必要です。")


def freeze_revised_materials(record: dict, proposal: Proposal, panels: Path) -> list[dict]:
    """確認した採否と説明で教材の写しを作る。元ファイルは書き換えない。"""
    policies = {item.reference.sample_index: item for item in proposal.training_samples or []}
    observations = {item.reference.sample_index: item for item in proposal.observations}
    materials = []
    for sample in record["samples"]:
        policy = policies.get(sample["index"])
        if policy is None or policy.priority == "reference":
            continue
        observed = observations[sample["index"]]
        directory = panels / policy.priority
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{sample['index']:03d}.png"
        target.write_bytes(Path(sample["path"]).read_bytes())
        caption = ", ".join(part for part in (record["trigger"], observed.caption_en) if part)
        target.with_suffix(".txt").write_text(caption, encoding="utf-8")
        materials.append({
            "reference": {"record_key": record["key"], "sample_index": sample["index"], "path": sample["path"]},
            "path": str(target), "caption": caption, "original_comment": sample.get("caption", ""),
            "caption_en": observed.caption_en, "appearance_ja": observed.appearance_ja,
            "training_policy": policy.model_dump(),
        })
    if not materials:
        raise ValueError("学習する画像がありません。教材にする画像を希望へ指定してください。")
    return materials


def selection_rows(selection: dict | None) -> list[dict]:
    if not selection:
        return []
    return selection.get("samples") or []


def revision_html(report: dict, cache: Path | None = None) -> str:
    """教材の変更を画像と理由で見る面。数値の合否はここに書かない。"""
    def url(path: str) -> str:
        target = Path(path)
        if cache is not None:
            try:
                return "/api/file?path=" + quote(str(target.resolve().relative_to(cache.resolve())))
            except ValueError:
                pass
        return "/api/file?path=" + quote(path)

    def card(title: str, path: str, body: str) -> str:
        image = f'<a href="{url(path)}" target="_blank"><img src="{url(path)}" alt=""></a>' if path else ""
        return f"<article><h3>{escape(title)}</h3>{image}{body}</article>"

    samples = []
    for sample in report["samples"]:
        policy = sample.get("before_policy") or {}
        revised = sample.get("after_policy") or {}
        samples.append(card(
            f"元教材 {sample['index']}",
            sample["path"],
            "<p>元の希望：" + escape(sample.get("caption") or "（なし）") + "</p>"
            "<p>これまでの採否：" + escape(str(policy.get("priority") or "未設定"))
            + " / " + escape("、".join(policy.get("features") or [])) + "</p>"
            "<p>見直し後：" + escape(str(revised.get("priority") or ""))
            + " / " + escape("、".join(revised.get("features") or [])) + "</p>"
            "<p>" + escape(revised.get("reason_ja") or "") + "</p>"
            "<p>" + escape(sample.get("after_caption") or "") + "</p>",
        ))
    rejected = []
    for picture in report["ng"]:
        review = picture.get("review") or {}
        rejected.append(card(
            f"NG {picture.get('id')}",
            picture["path"],
            "<p>原文：" + escape(review.get("comment") or "") + "</p>"
            "<pre>" + escape(json.dumps(review.get("meaning"), ensure_ascii=False, indent=2) or "") + "</pre>",
        ))
    questions = "".join(f"<li>{escape(item)}</li>" for item in report.get("questions") or [])
    changes = "<pre>" + escape(json.dumps(report.get("changes") or [], ensure_ascii=False, indent=2)) + "</pre>"
    return (
        '<!doctype html><html lang="ja"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>NG指摘による教材の見直し</title>"
        "<style>body{font:17px/1.5 system-ui;margin:20px;background:#faf8f5}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}"
        "article{background:#fff;border:1px solid #ccc;padding:8px}img{width:100%;height:auto}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>"
        "<h1>NG指摘による教材の見直し</h1>"
        "<p>元の参考画像の採否と説明を見直します。NG画像は教材へ足しません。未判定は使いません。"
        "比較生成では、作り直し前と同じ生成文を使います。</p>"
        f"<p>{escape(report.get('status') or '')}</p>"
        + (f"<h2>確認事項</h2><ul>{questions}</ul>" if questions else "")
        + "<h2>元の教材</h2><div class=\"grid\">" + "".join(samples) + "</div>"
        + "<h2>本人のNG</h2><div class=\"grid\">" + "".join(rejected) + "</div>"
        + "<h2>追加する生成条件案</h2><p>学習の比較では使いません。次の通常生成向けです。</p>" + changes
        + "</html>"
    )
