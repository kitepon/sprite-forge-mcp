"""汎用性の実測を、元素材をcommitせず閲覧用HTMLへまとめる。"""
import base64
from html import escape
import json
from pathlib import Path

root = Path(__file__).resolve().parent
cases = json.loads((root / "generic-cases.json").read_text())
names = {"human": "男性・2枚目の衣装", "orc": "体格の大きいオーク", "dragon": "四足のドラゴン", "slime": "手足のないスライム"}
scope_names = {"persistent": "今後も共通", "this_run": "今回だけ", "panel": "このパネルに残す"}
html = ['''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>異なるキャラクターでの検証</title><style>body{max-width:1050px;margin:24px auto;padding:16px;background:#f4f3ee;color:#183c32;font:16px/1.75 system-ui}section{background:#fff;padding:24px;border-radius:20px;margin:24px 0}p,code{overflow-wrap:anywhere}.notice{background:#f5e8cf;padding:20px;border-radius:16px}.refs{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0;max-width:260px}img{width:100%;height:230px;object-fit:contain}dt{font-weight:600;margin-top:16px}dd{margin:4px 0}summary{cursor:pointer}small{color:#58665e}</style>
<h1>ベル以外でも、注文を扱えるか</h1><p class="notice">汎用性はまだ受入未達。4種類の実解釈を行い、3件は生成文まで照合、1件は固定パネルと両立せず質問で停止しました。実画像の生成・再学習・機能本体の本番配備は行っていません。</p>
<p>2026年9月5日。既存の画像素材と同じ解釈モデルを使用。人物名や衣装の分岐は製品へ追加していません。</p>
<section><h2>確認できた問題</h2><ul><li>今回だけの衣装変更が、維持するはずの鎧・体形確認パネルまで上書きする。</li><li>今後の基本衣装に含むブーツの具体的な条件が、靴単品では今回だけとなり、解釈指定を外すと失われる。</li><li>手足や衣装のないキャラクターは、固定の衣装・靴パネルと両立しない。</li></ul><p>男性の2枚目指定と、ドラゴンの四足・翼膜だけの色変更は解釈できました。生成画像の品質まで合格したという意味ではありません。</p></section>''']
for case in cases:
    directory = root / "private" / f"generic-{case['id']}"
    native = json.loads((directory / "interpretation.json").read_text())
    resolved = json.loads((directory / "resolved.json").read_text())
    html.append(f'<section><h2>{escape(names[case["id"]])}</h2><p>{escape(case["comment"])}</p><p><small>{escape(native["interpreter"]["model"])}・既存ChatGPTログイン・{native["interpreter"]["elapsed_seconds"]}秒</small></p><div class="refs">')
    for index, ref in enumerate(native["references"], 1):
        encoded = base64.b64encode(Path(ref["path"]).read_bytes()).decode("ascii")
        html.append(f'<figure><img src="data:image/png;base64,{encoded}" alt="参考画像{index}"><figcaption>参考画像{index}</figcaption></figure>')
    html.append('</div><h3>解釈案</h3><dl>')
    for c in native["proposal"]["changes"]:
        reference = f'画像{c["reference"]["sample_index"] + 1}' if c["reference"] else "画像指定なし"
        html.append(f'<dt>{escape(c["feature"])}・{escape(scope_names[c["scope"]])}・{escape(c["panel_key"] or "全体")}・{reference}</dt><dd>{escape(c["reason_ja"])}</dd><dd><code>{escape(c["description_en"])}</code></dd><dd>除外: {escape(c["avoid_ja"] or "なし")}</dd>')
    html.append('</dl>')
    if native["proposal"]["questions"]:
        html.append('<h3>未採用・確認が必要</h3>')
        html.extend(f'<p>{escape(q)}</p>' for q in native["proposal"]["questions"])
    else:
        html.append('<h3>パネルへ解決した文（GPU未実行）</h3>')
        for r in resolved["requests"]:
            html.append(f'<details><summary>{escape(r["section"])} · {escape(r["label"])}</summary><p><code>{escape(r["prompt"])}</code></p><p>除外: <code>{escape(r["negative"])}</code></p></details>')
        for r in resolved.get("without_order", []):
            if r["panel"] == "item_shoes":
                html.append(f'<h3>解釈指定を外した靴単品</h3><p><code>{escape(r["prompt"])}</code></p><p>採用済みの全体衣装は残りますが、この単品用の具体的な形・色の指定は残っていません。</p>')
    html.append('</section>')
html.append('<p>素材はプロジェクトの既存画像を隔離コピーして使用。画像はこの閲覧成果物へだけ含め、gitには含めていません。追加課金・リセット・Sonnet・再学習は使用していません。</p></html>')
output = root / "private" / "generic-probe.html"
output.write_text("\n".join(html), encoding="utf-8")
print(output)
