"""画像別採用の実記録と生成結果を、同じ公開面で確認できるようにする。"""
import html
import json
from pathlib import Path
from urllib.parse import urlencode
import httpx

root = Path(__file__).parent / "private/feature-refs-production"
with httpx.Client(base_url="http://192.168.1.2:8766", timeout=30) as client:
    def get(path):
        response = client.get(path)
        response.raise_for_status()
        return response.json()
    intent = get("/api/jobs/7b9d1ba7-3354-4d6d-a9f3-ac67418ef14b")
    generation = get("/api/jobs/b139f3b1-5577-4601-915d-7d97373b455e")
    assert intent["status"] == "confirmed"
    assert generation["status"] == "completed"
    for feature, index in [("face", 1), ("subject", 3), ("outfit", 3)]:
        assert generation["intent_conditions"][feature]["reference"] == intent["references"][index]
    (root / "verified.json").write_text(json.dumps({"intent": intent, "generation": generation}, ensure_ascii=False, indent=2))

def figure(label, path):
    url = "/api/file?" + urlencode({"path": path})
    return f'<figure><figcaption>{html.escape(label)}</figcaption><img src="{html.escape(url)}" alt="{html.escape(label)}"></figure>'

sources = figure("顔立ちの参照：画像2", intent["references"][1]["path"]) + figure("体格・頭身と衣装の参照：画像4", intent["references"][3]["path"])
results = "".join(figure(f"生成結果 {i+1}・seed {p['seed']}", p["path"]) for i, p in enumerate(generation["pictures"]))
report = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>画像別の採用指定 — Sprite Forge</title><style>body{max-width:1100px;margin:auto;padding:24px;font:16px/1.8 system-ui;background:#16202d;color:#edf4ff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}figure{margin:0}img{width:100%;border-radius:12px}a{color:#a7e5d1}h1{line-height:1.4}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>
<h1>画像ごとに、採用したい特徴を指定</h1><p>2026年9月6日。本番WebUIで確認案を採用し、次のプレビュー工程から2枚を生成しました。元のベルの台帳・教材・LoRAは変更していません。</p>
<h2>指定した内容</h2><p>画像2のコメント「この画像の顔立ちを強く採用してほしい」。画像4のコメント「この画像の体格・頭身と服装を強く採用してほしい」。全体コメントは空欄です。</p><div class="grid">''' + sources + '''</div>
<h2>生成結果</h2><p>Anima Base、832×1216、seed 1・2、既存キャラクターLoRAの強度0.8、追加画風なし。再学習はしていません。</p><div class="grid">''' + results + '''</div>
<h2>確認できたことと限界</h2><p>顔＝画像2、体格と衣装＝画像4という参照先が、今後も使う条件として保存され、別工程の実生成へ引き継がれました。下記は実際の生成記録です。画像別の学習回数やLoRAの特徴別重みを変える機能ではありません。</p>
<p>生成結果では上下に分かれた衣装と露出した腹部を確認できました。顔の似方や年齢感の十分な再現までは保証できず、研究中の機能です。今回の2枚だけでは汎用的な画質改善や修正前との因果比較を実証したことにはなりません。</p>
<details><summary>実際に生成へ渡った条件</summary><pre>''' + html.escape(json.dumps({"conditions": generation["intent_conditions"], "prompt": generation["prompt"], "loras": generation["loras"]}, ensure_ascii=False, indent=2)) + '''</pre></details><p><a href="/#/flow/sheet">制作画面へ</a></p></html>'''
(root / "feature-references-20260906.html").write_text(report)
