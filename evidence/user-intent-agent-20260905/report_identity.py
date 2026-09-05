"""素材と変更前後を、同条件の比較として閲覧できる形にする。"""
import base64
import html
import json
from pathlib import Path

root = Path(__file__).parent / "private"
result = json.loads((root / "identity-v1/result.json").read_text())
panels = []
for title, path in [("素材", root / "identity-v1/reference-0.png"),
                    ("変更前", root / "deploy-v1/result.png"),
                    ("人物・顔の解釈を変更", root / "identity-v1/after.png")]:
    data = base64.b64encode(path.read_bytes()).decode()
    panels.append(f'<figure><figcaption>{title}</figcaption><img alt="{title}" src="data:image/png;base64,{data}"></figure>')
report = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>素材の年齢感・比率の引き継ぎ — Sprite Forge</title><style>body{font:16px/1.8 system-ui;margin:auto;padding:24px;max-width:1400px;background:#16202d;color:#f0f5ff}h1{line-height:1.4}.images{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}figure{margin:0}img{width:100%;border-radius:12px}a{color:#a7e5d1}pre{white-space:pre-wrap}</style>
<h1>素材の年齢感と身体比率を引き継ぐ</h1><p>2026年9月6日 · 改善途中・研究中</p>
<p>同じ素材、seed 1、キャラクターLoRA強度0.8、追加画風なし、1024角で比較。衣装・髪・背景と除外文は維持し、人物・顔の生成文だけを新しい実CLI解釈へ差し替えました。再学習はしていません。</p>
<div class="images">''' + "".join(panels) + '''</div>
<h2>確認できたこと</h2><p>旧解釈の「少女」「幼い顔立ち」から、新解釈は画像を見て「若い成人に見える年齢感」と顔・身体の比率を記述しました。成人の固定指定や頭身の数値指定は入力していません。</p>
<p>開発担当の目視では、変更後の輪郭と身体つきは前回より素材に近づきました。ただし、幼い印象はなお残り、十分な年齢感の再現を達成したとは判定していません。表情も変化しています。一組の比較で、すべての人物への有効性やLoRA学習の改善を証明したものではありません。</p>
<h2>実装の変更</h2><p>確認済みの教材説明を生成時の解釈へ渡す欠落を修理しました。観察・学習用説明・生成案に年齢感と身体比率を残すようにし、年齢感と頭身を同一視しません。説明の採用と学習は引き続き明示操作です。以前に学習したLoRAや採用済みの条件は自動で書き換えません。</p>
<details><summary>新しい実解釈</summary><pre>''' + html.escape(json.dumps(result, ensure_ascii=False, indent=2)) + '''</pre></details><p><a href="/">スタジオへ</a></p></html>'''
(root / "identity-v1/identity-comparison-20260906.html").write_text(report)
