"""教材確認の保存記録から、原案・訂正・学習用説明を閲覧するページを作る。"""
import argparse
import base64
import html
import json
from pathlib import Path


def main(args):
    job = json.loads(args.job.read_text())
    esc = html.escape
    cards = []
    for number, item in enumerate(job["materials"], 1):
        intent = json.loads((args.job.parent / f'{item["intent_job_id"]}.json').read_text())
        original = next(observation for observation in intent["proposal"]["observations"]
                        if observation["reference"] == item["reference"])
        image = base64.b64encode(Path(item["path"]).read_bytes()).decode()
        corrected = original["caption_en"] != item["caption_en"] or original["appearance_ja"] != item["appearance_ja"]
        cards.append(f'<section><h2>教材 {number}</h2><img alt="教材 {number}" src="data:image/png;base64,{image}">'
                     f'<p>{esc(item["appearance_ja"])}</p><p>{"画面で訂正して採用" if corrected else "解釈案のまま採用"}</p>'
                     f'<details><summary>実際に教材へ渡す説明</summary><p>{esc(item["caption"])}</p></details>'
                     f'<details><summary>モデルの原案</summary><p>{esc(original["appearance_ja"])}</p><p>{esc(original["caption_en"])}</p></details>'
                     f'<details><summary>注文原文（教材へ転記しません）</summary><p>{esc(intent["original_comment"])}</p></details></section>')
    mode = '模擬学習で開始・完了・再表示を検証。実際の再学習は未実施。' if job.get('fixture_training') else f'保存された学習状態: {esc(job["status"])}'
    body = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>学習教材の確認</title><style>body{max-width:960px;margin:24px auto;padding:16px;background:#f4f3ee;color:#183c32;font:16px/1.7 system-ui}section{background:white;padding:24px;border-radius:20px;margin:24px 0}img{display:block;max-width:100%;max-height:520px;margin:auto}p{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600}details{margin:18px 0}.notice{background:#e5ecd9;padding:20px;border-radius:16px}@media(max-width:600px){section{padding:16px}}</style><h1>希望と教材の説明を分ける</h1>'
    body += f'<p class="notice">{mode}</p><p>制作への希望と、実際に画像に写る内容の説明を分けます。モデルの原案と確認後の説明を、各教材で見比べられます。</p><p>{len(cards)} 枚の画像と説明を保存した時点の写しです。本番機能の配備や、学習後の画質確認が完了したという報告ではありません。</p>'
    args.output.write_text(body + ''.join(cards) + '</html>', encoding='utf-8')
    print(json.dumps({'materials': len(cards), 'fixture_training': job.get('fixture_training', False), 'page': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
