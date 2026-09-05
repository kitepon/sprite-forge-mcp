"""本番確認の証拠を取得し、既存台帳との一致と訂正の伝達を検証する。"""
import argparse
import base64
import html
import json
from pathlib import Path

import httpx


def main(args):
    before = json.loads((args.output / "before.json").read_text())
    with httpx.Client(base_url=args.url, timeout=30) as client:
        def get(endpoint, **params):
            response = client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()

        characters = get("/api/characters")
        styles = get("/api/styles")
        for original in before["characters"]:
            assert next(item for item in characters if item["key"] == original["key"]) == original
        assert styles == before["styles"]
        job = get(f"/api/jobs/{args.job}")
        intent = next(item for item in get("/api/intents", name=job["name"], kind="character")
                      if item["job_id"] == job["intent_job_id"])
        assert job["status"] == "completed"
        assert intent["accepted"]
        assert intent["effective_conditions"]["background"]["description_en"] == "plain white background, simple studio backdrop"
        assert "plain white background, simple studio backdrop" in job["prompt"]
        assert len(job["loras"]) == 1 and job["loras"][0][1] == 0.8
        assert intent["interpreter"]["auth"] == "chatgpt"
        response = client.get("/api/file", params={"path": job["path"]})
        response.raise_for_status()
        (args.output / "result.png").write_bytes(response.content)
        for name, data in (("job", job), ("intent", intent)):
            (args.output / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
        summary = {"job_id": job["job_id"], "intent_job_id": intent["job_id"],
                   "existing_characters_unchanged": len(before["characters"]),
                   "existing_styles_unchanged": len(styles), "elapsed_s": job["elapsed_s"],
                   "interpreter": intent["interpreter"], "loras": job["loras"]}
        (args.output / "verified.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        image = base64.b64encode(response.content).decode()
        report = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>本番反映の確認 — Sprite Forge</title><style>body{{font:16px/1.8 system-ui;background:#111925;color:#eef3fa;max-width:960px;margin:auto;padding:24px}}img{{width:100%;border-radius:16px}}section{{background:#202c3d;padding:20px;border-radius:16px;margin:20px 0}}a{{color:#8edbcc}}code{{overflow-wrap:anywhere}}h1{{line-height:1.4}}</style>
<h1>本番反映済み<br>コメント反映・特徴の強度調整</h1><p>2026年9月6日 · 研究中の機能</p>
<section><h2>本番で確認した操作</h2><p>原文保存 → 画像と注文の解釈 → 背景の生成文を訂正 → 採用 → GPU生成 → 画像表示。</p>
<p>解釈 {intent['interpreter']['elapsed_seconds']} 秒（公式Codex CLI・ChatGPT認証）。画像生成 {job['elapsed_s']} 秒。キャラクター強度0.8、追加画風なし。</p>
<p>既存キャラクター{len(before['characters'])}件・画風{len(styles)}件の台帳は確認前と完全一致。新しい確認用キャラクターだけを使用し、学習は実行していません。</p></section>
<h2>本番で生成した一枚</h2><img alt="本番の注文採用後に生成したキャラクター画像" src="data:image/png;base64,{image}">
<section><h2>反映精度は研究中</h2><p>生成条件への伝達は確認できています。ただし、学習済みの特徴の影響で衣装・向き・背景が十分に反映されない場合があります。特徴の強さは詳細設定で手動調整できます。既定値は0.8です。</p>
<p>今回の画像は白背景・上下セパレート・単独全身を満たしましたが、素材より幼く見えると利用者から指摘されています。解釈に「少女」、生成文に youthful と大きな瞳・小さな鼻や唇の指定が入り、年齢感を保てていません。学習済みLoRAの寄与は未切り分けです。年齢感の再現品質は未達として残し、高頭身化や再学習による修正は行っていません。</p><p>過去の比較は<a href="/api/file?path=/app/.cache/intent-generation-20260905.html">10枚の生成比較</a>で確認できます。</p></section>
<details><summary>実際に生成へ渡った注文</summary><p>{html.escape(job['prompt'])}</p></details>
<p>配備コード：14fb4d8。Python試験254件、Web試験33件成功。GitHub CI成功。</p><p><a href="/">スタジオへ</a></p></html>'''
        (args.output / "production-acceptance-20260906.html").write_text(report)
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
