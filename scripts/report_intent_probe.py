"""肯定文の一要因比較を、元画像と実験画像を並べて表示する。"""
import argparse
import base64
from copy import deepcopy
import html
import json
from pathlib import Path


def main(args):
    results = json.loads((args.probe / "results.json").read_text())
    observations = json.loads(args.observations.read_text())
    cards = []
    for key, observation in observations.items():
        pairs = []
        rows = [row for row in results if row["case"] == key]
        assert len(rows) == 3 and {row["seed"] for row in rows} == {1, 2, 3}
        for row in rows:
            source_graph = args.root / row["source_graph"]
            original = json.loads(source_graph.read_text())
            changed = json.loads((args.probe / f"{key}-{row['seed']}-workflow.json").read_text())
            restored = deepcopy(changed)
            restored["20"]["inputs"]["text"] = original["20"]["inputs"]["text"]
            assert original == restored
            assert changed["20"]["inputs"]["text"] == original["20"]["inputs"]["text"].replace(row["old"], row["new"], 1)
            previous = json.loads((source_graph.parent / "changed.json").read_text())
            picture = next(p for p in previous["pictures"] if p["seed"] == row["seed"])
            for label, path in (("前回の解釈", source_graph.parent / "generated" / Path(picture["path"]).name),
                                ("対象句だけ具体化", args.probe / row["image"])):
                image = base64.b64encode(path.read_bytes()).decode()
                pairs.append(f'<figure><figcaption>{label} · Seed {row["seed"]}</figcaption><img src="data:image/png;base64,{image}"></figure>')
        cards.append(f'<section><h2>{html.escape(observation["title"])}</h2><p>{html.escape(observation["result"])}</p>'
                     f'<p>元の句：<code>{html.escape(rows[0]["old"])}</code></p><p>今回の句：<code>{html.escape(rows[0]["new"])}</code></p>'
                     '<details><summary>同じSeedの新旧6枚を見る</summary><div class="grid">' + ''.join(pairs) + '</div></details></section>')
    assert len(results) == 3 * len(observations)
    body = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>丈と向きの切り分け</title><style>body{max-width:1100px;margin:24px auto;padding:20px;background:#f4f3ee;color:#183c32;font:16px/1.65 system-ui}section{background:white;padding:24px;border-radius:20px;margin:20px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}img{width:100%;border-radius:14px}code{overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600}@media(max-width:500px){body{padding:10px}section{padding:16px}.grid{gap:8px}}</style><h1>丈と向きの切り分け</h1><p>新規6枚と保存済み6枚。同じAnima Base・既存LoRA強度0.8・Seed 1〜3。肯定文の対象句以外は実グラフが一致。再学習なし。</p><p>開発担当が原因を調べるために英語を具体化した比較です。エージェントが自動で出した成果とは扱いません。</p>' + ''.join(cards) + '</html>'
    args.output.write_text(body, encoding="utf-8")
    print(json.dumps({"new_images": len(results), "retained_images": len(results), "only_positive_changed": True, "page": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
