"""比較実験の全画像・実条件・人による観察を一枚のHTMLへまとめる。"""
import argparse
import base64
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path

from PIL import Image


def build(root, cases):
    sections, metrics, baseline_pixels, normalized = [], [], [], []
    for case in cases:
        key = case["key"]
        source = root / f"p3-{key}-images"
        interpretation = json.loads((root / f"p3-{key}" / "interpretation.json").read_text())
        before = json.loads((source / "baseline.json").read_text())
        after = json.loads((source / "changed.json").read_text())
        scope = json.loads((source / "scope.json").read_text())
        graphs = list(source.glob("workflow-*.json"))
        assert len(graphs) == 6, (key, len(graphs))
        for graph in graphs:
            value = deepcopy(json.loads(graph.read_text()))
            for node in ("20", "21"):
                value[node]["inputs"].pop("text")
            value["23"]["inputs"].pop("seed")
            normalized.append(hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest())
        cards, pixel_hashes = [], []
        for result in (before, after):
            assert result["status"] == "completed"
            assert [p["seed"] for p in result["pictures"]] == [1, 2, 3]
        for i in range(3):
            for label, result in (("共通条件のみ", before), ("今回の注文を反映", after)):
                picture = result["pictures"][i]
                path = source / "generated" / Path(picture["path"]).name
                with Image.open(path) as im:
                    assert im.size == (832, 1216)
                    pixel_hash = hashlib.sha256(im.tobytes()).hexdigest()
                if result is before:
                    pixel_hashes.append(pixel_hash)
                url = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
                cards.append(f'<figure><figcaption>{label}・Seed {i + 1}・{picture["elapsed_s"]}秒</figcaption><img alt="{label} Seed {i + 1}" src="{url}"></figure>')
        baseline_pixels.append(pixel_hashes)
        unchanged = scope["before"] == scope["after"] == scope["next_run"]["intent_conditions"]
        assert unchanged, key
        metrics.append({"case": key, "interpreter_seconds": interpretation["interpreter"]["elapsed_seconds"],
                        "generation_seconds": [p["elapsed_s"] for r in (before, after) for p in r["pictures"]],
                        "common_conditions_unchanged": unchanged, "observation": case["observation"]})
        sections.append(f'<section id="{html.escape(key)}"><h2>{html.escape(case["title"])}</h2><p>{html.escape(case["observation"])}</p><blockquote>{html.escape(interpretation["original_comment"])}</blockquote><details><summary>新旧6枚と実際の指示を見る</summary><div class="grid">{"".join(cards)}</div><h3>肯定条件</h3><pre>{html.escape(after["prompt"])}</pre><h3>否定条件</h3><pre>{html.escape(after["negative"])}</pre></details></section>')
    assert len(set(normalized)) == 1
    assert all(pixels == baseline_pixels[0] for pixels in baseline_pixels)
    report = {"cases": metrics, "total_images": 6 * len(cases), "normalized_graphs_equal": True,
              "baseline_pixels_equal_across_cases": True}
    (root / "p3-expanded-metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    body = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>注文の反映・追加比較</title><style>body{max-width:1100px;margin:24px auto;padding:20px;background:#f4f3ee;color:#183c32;font:16px/1.65 system-ui}section{background:white;padding:24px;border-radius:20px;margin:20px 0}h1{font-size:28px}h2{font-size:22px}summary{cursor:pointer;color:#075f47;font-weight:600}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}img{width:100%;border-radius:14px}figcaption{padding:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f3ee;padding:16px;border-radius:12px}blockquote{border-left:3px solid #a8c9bb;padding-left:16px;margin-left:0}@media(max-width:500px){body{padding:10px}section{padding:16px}.grid{gap:8px}figcaption{font-size:12px}}</style><h1>注文の反映・追加比較</h1><p>4種類・新旧24枚の生成完了。服の変更は反映されたが、横向きの精度と髪の維持に不足が見つかった。</p><p>同じ既存LoRA・強度0.8・Anima Base・832×1216・28 steps・CFG 4。各条件でSeed 1〜3。再学習なし、本番の登録データ変更なし。「今回だけ」の条件は次の生成条件へ残っていない。</p>' + ''.join(sections) + '<p>画像の観察は開発担当によるもの。自動の採用判定ではありません。改善前の結果も全件表示しています。</p></html>'
    output = root / "p3-expanded-comparison.html"
    output.write_text(body, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    build(args.root, json.loads(args.observations.read_text()))
