"""構成案の実解釈を、成功・修正前を含めて一つの閲覧面へまとめる。"""
import argparse
from html import escape
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--result", type=Path, action="append", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
parts = ['<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>構成を言葉で選ぶ・実解釈の記録</title><style>body{font:16px/1.8 system-ui;background:#f5f3ed;color:#24483b;max-width:1080px;margin:24px auto;padding:20px}article{background:white;border-radius:18px;padding:24px;margin:24px 0}pre{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}h2{font-size:22px}</style><h1>構成を言葉で選ぶ</h1><p>既存の契約ログインによる実解釈です。構成案は未採用で、画像生成と学習は行っていません。衣装変更と、人型に限定しない構成を別々に確認しました。</p><p>衣装案の初回は新しい項目名が英語になりました。既存名を維持する指示との区別を明確にした再実測では、日本語の名前を返しました。修正前も含めて下に掲載します。</p>']
for index, path in enumerate(args.result, 1):
    job = json.loads(path.read_text())
    result = job["interpreter"]
    parts.append(f'<article><h2>実測 {index} · {len(job["proposal"]["panels"])}項目</h2><p>{escape(job["original_comment"])}</p><p>{escape(job["record_description"])}</p><p>{escape(result["model"])} ／ {result["elapsed_seconds"]}秒 ／ ChatGPT契約ログイン</p><p>{escape(job["proposal"]["summary_ja"])}</p>')
    parts.append('<h3>提案された項目</h3><ol>')
    for panel in job["proposal"]["panels"]:
        parts.append(f'<li><strong>{escape(panel["label"])}</strong>：{escape(panel["description_ja"])}</li>')
    parts.append('</ol><details><summary>生成条件を含む全応答</summary><pre>' + escape(json.dumps(job["proposal"], ensure_ascii=False, indent=2)) + '</pre></details>')
    parts.append('<details><summary>解釈時の元の構成</summary><pre>' + escape(json.dumps(job["sheet_layout"], ensure_ascii=False, indent=2)) + '</pre></details></article>')
parts.append('<p>構成の編集・保存・描画への接続は隔離した画面で試験しています。本番機能配備と実画像品質の確認は未完了です。</p></html>')
args.output.write_text(''.join(parts))
