"""保存済みグラフの比較条件を照合し、全画像と観察を掲載する。GPUは呼ばない。"""
import argparse
import base64
import hashlib
from html import escape
import json
from pathlib import Path

from scripts.probe_sheet_causes import perturb


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    for name in ("source", "observations", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("probe", "cases"):
        parser.add_argument("--" + name, type=Path, action="append", required=True)
    parser.add_argument("--interpretation", type=Path, action="append", default=[])
    args = parser.parse_args()
    cases = [case for path in args.cases for case in read(path)]
    results = [result for root in args.probe for result in read(root / "results.json")]
    roots = {result["key"]: root for root in args.probe for result in read(root / "results.json")}
    notes = read(args.observations)
    needs_baseline = any(item["source"] == "baseline" for group in notes["groups"] for item in group["cases"])
    job = read(args.source / "changed.json") if needs_baseline else None
    assert [r["key"] for r in results] == [c["key"] for c in cases], "実行結果と比較条件の対応が不一致"
    verified = []
    for case, result in zip(cases, results, strict=True):
        source = args.source / case["graph"]
        root = roots[case["key"]]
        actual = root / (case["key"] + "-workflow.json")
        assert read(actual) == perturb(read(source), case), case["key"]
        assert result["seed"] == read(actual)["23"]["inputs"]["seed"], case["key"]
        assert all(result[k] == v for k, v in case.items()), case["key"]
        verified.append({"key": case["key"], "seed": result["seed"], "elapsed_s": result["elapsed_s"],
                         "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                         "workflow_sha256": hashlib.sha256(actual.read_bytes()).hexdigest(),
                         "image_sha256": hashlib.sha256((root / result["image"]).read_bytes()).hexdigest()})
    shown = []
    image_count = 0
    sections = []
    for group in notes["groups"]:
        cards = []
        for item in group["cases"]:
            if item["source"] == "baseline":
                request = next(p for p in job["panel_requests"] if p["panel"] == group["panel"])
                remote = next(Path(p) for p in job["panels"] if Path(p).stem == group["panel"])
                path = args.source / remote.relative_to("/results/run1")
                condition = f"seed {request['seed']}・前回の画像を再利用"
            elif item["source"] == "file":
                path = args.source / item["image"]
                condition = item["condition"]
            else:
                result = next(r for r in results if r["key"] == item["key"])
                path = roots[item["key"]] / result["image"]
                condition = f"seed {result['seed']}・{result['elapsed_s']}秒"
                shown.append(item["key"])
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            image_count += 1
            cards.append(f'<article><h3>{escape(item["label"])}</h3><p class="meta">{escape(condition)}</p>'
                         f'<img alt="{escape(group["label"] + item["label"])}" src="data:image/png;base64,{data}">'
                         f'<p>{escape(item["observation"])}</p></article>')
        sections.append(f'<section><h2>{escape(group["label"])}</h2><div class="cards">' + ''.join(cards) + '</div></section>')
    assert sorted(shown) == sorted(r["key"] for r in results), "未掲載または重複掲載の実験画像があります"
    document = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>人間キャラクターの構図比較</title><style>
*{box-sizing:border-box}body{margin:0;background:#f1f3f8;color:#222a40;font:16px/1.75 system-ui,sans-serif}main{max-width:1240px;margin:auto;padding:28px}h1{font-size:clamp(25px,4vw,38px);margin:0}h2{margin:32px 0 12px}h3{font-size:17px;margin:0}aside{background:#fff3d8;border-left:4px solid #b87c23;padding:16px 22px;margin-top:22px;border-radius:8px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr));gap:18px}article{background:white;border:1px solid #d8deea;border-radius:15px;padding:18px}img{width:100%;height:460px;object-fit:contain;background:white}p{margin:8px 0}.meta{font-size:14px;color:#586478}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}details{margin:24px 0}a{color:inherit}@media(max-width:600px){main{padding:18px}img{height:420px}}
</style><main><p class="meta">Sprite Forge / 2026-09-05 / 診断結果・本番設定は未変更</p><h1>人間の品質を保って、構図を直せるか</h1>'''
    document += '<aside><p>' + escape(notes["summary"]) + '</p></aside><p>' + escape(notes["limits"]) + '</p>'
    document += '<p>人間の顔・髪・衣装・画風の維持を主な受入条件とし、人外の事例は追加の検証に使う。LoRAを外す比較は原因調査に限定する。</p>'
    document += ''.join(sections)
    if notes.get("native_observations"):
        document += '<section><h2>構成エージェントの確認</h2><ul>' + ''.join('<li>' + escape(note) + '</li>' for note in notes["native_observations"]) + '</ul></section>'
    document += f'<details><summary>変更条件と実グラフの照合結果（全{len(verified)}件一致）</summary><pre>' + escape(json.dumps({"cases": cases, "verified": verified}, ensure_ascii=False, indent=2)) + '</pre></details>'
    for path in args.interpretation:
        document += '<details><summary>構成エージェントの実応答：' + escape(path.parent.name) + '</summary><pre>' + escape(json.dumps(read(path), ensure_ascii=False, indent=2)) + '</pre></details>'
    document += '</main></html>'
    args.output.write_text(document, encoding="utf-8")
    args.output.with_suffix(".verification.json").write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"実グラフ{len(verified)}件一致、全{image_count}画像を掲載: {args.output}")


if __name__ == "__main__":
    main()
