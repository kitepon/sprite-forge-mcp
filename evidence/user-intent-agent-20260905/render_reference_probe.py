"""画像付きの全解釈と、現在の共通処理で組み立てた文を閲覧する。採用・生成はしない。"""
import argparse
import base64
from copy import deepcopy
from html import escape
import json
from pathlib import Path

from backend import bible
from backend.intent import Change, PREVIEW_TAGS, drawing_content, effective_conditions, generation_negative, preview_content
from backend.panel_intent import resolve_panel
from backend.sheet_layout import panel_from


def resolve_candidate(job):
    """確認した場合の共通条件と今回条件で文を組む。台帳は変更しない。"""
    if job["stage"] == "layout" or job["proposal"]["questions"]:
        return []
    common = deepcopy(job["base_conditions"])
    changes = job["proposal"]["changes"]
    if job["stage"] in ("preview", "drawing"):
        conditions = effective_conditions(common, [Change.model_validate(change) for change in changes])
        if job["stage"] == "preview":
            subject = "" if "subject" in conditions else bible.subject_tag(job["record_description"])
            background = "" if "background" in conditions else bible.COMMON
            parts = ("reference_probe", subject, preview_content(PREVIEW_TAGS, conditions), background)
        else:
            parts = ("reference_probe", drawing_content("", conditions, job["job_id"]))
        return [{"key": job["stage"], "label": "プレビュー" if job["stage"] == "preview" else "一枚生成",
                 "prompt": ", ".join(part for part in parts if part),
                 "negative": generation_negative(conditions), "conditions": conditions}]
    for change in changes:
        if change["scope"] == "persistent":
            common[change["feature"]] = deepcopy(change)
    return [{"key": p["key"], "label": p["label"], **resolve_panel(
        panel_from(p), "reference_probe", job["record_description"], common, changes,
        job["existing_settings"].get("panel_overrides", {}).get(p["key"], {}))}
        for p in job["sheet_layout"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.manifest.parent
    manifest = json.loads(args.manifest.read_text())
    html = ['''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>人間の衣装と画像付き構成の確認</title><style>body{max-width:1060px;margin:24px auto;padding:18px;background:#f5f3ed;color:#224537;font:16px/1.8 system-ui}article{background:white;border-radius:18px;padding:24px;margin:24px 0}.notice{padding:20px;background:#f9e9cf;border-radius:16px}.refs{display:flex;flex-wrap:wrap;gap:18px}figure{margin:0;width:230px}img{width:100%;height:230px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer}</style>
<h1>人間の衣装を基準に、注文の反映を確認する</h1>''']
    html.append(f'<p class="notice">{escape(manifest["summary"])}</p>')
    for case in manifest["cases"]:
        job = json.loads((root / case["result"]).read_text())
        requests = resolve_candidate(job)
        html.append(f'<article><h2>{escape(case["title"])}</h2><p>{escape(case["finding"])}</p><p>{escape(job["original_comment"])}</p><p>{escape(job["interpreter"]["model"])}・ChatGPT契約ログイン・{job["interpreter"]["elapsed_seconds"]}秒</p><div class="refs">')
        for i, reference in enumerate(job["references"], 1):
            encoded = base64.b64encode(Path(reference["path"]).read_bytes()).decode("ascii")
            html.append(f'<figure><img src="data:image/png;base64,{encoded}" alt="参考画像{i}"><figcaption>参考画像{i}</figcaption></figure>')
        html.append('</div>')
        if job["stage"] == "layout":
            html.append('<h3>提案された構成</h3><ol>')
            for panel in job["proposal"]["panels"]:
                html.append(f'<li>{escape(panel["label"])}：{escape(panel["description_ja"])}</li>')
            html.append('</ol>')
        else:
            html.append('<h3>変更する内容と範囲</h3><ul>')
            for change in job["proposal"]["changes"]:
                scope = {"persistent": "今後も共通", "panel": "項目に残す", "this_run": "今回だけ"}[change["scope"]]
                html.append(f'<li>{escape(scope)}：{escape(change["reason_ja"])}</li>')
            html.append('</ul><h3>現在の処理で組み立てた生成文（GPU未実行）</h3>')
            for request in requests:
                html.append(f'<details><summary>{escape(request["label"])}</summary><pre>{escape(json.dumps(request, ensure_ascii=False, indent=2))}</pre></details>')
        html.append('<details><summary>画像参照・全解釈・元構成</summary><pre>' + escape(json.dumps(job, ensure_ascii=False, indent=2)) + '</pre></details></article>')
    html.append('<p>すべて隔離台帳による試験です。構成を実験へ入力した操作以外は未採用で、画像生成・学習・本番機能配備は行っていません。解釈案だけの成功を、生成画像の成功には数えません。</p></html>')
    args.output.write_text(''.join(html))


if __name__ == "__main__":
    main()
