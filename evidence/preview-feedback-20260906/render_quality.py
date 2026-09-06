"""比較記録を、全画像を見比べられるHTMLへ変換する。合否の自動判定はしない。"""
import argparse
import html
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('report', type=Path)
args = parser.parse_args()
data = json.loads(args.report.read_text())
names = {'before': '学習前', 'ok_only': 'OKのみ追加学習', 'preference': 'OKとNGの選好学習'}
escape = lambda value: html.escape(str(value), quote=True)
rows = []
for seed in data['evaluation_seeds']:
    cells = []
    for condition in data['conditions']:
        picture = next((p for p in condition.get('pictures', []) if p['seed'] == seed), None)
        if picture:
            path = escape(os.path.relpath(picture['path'], args.report.parent))
            cells.append(f'<td><a href="{path}"><img src="{path}" alt="{escape(names[condition["condition"]])} seed {seed}"></a></td>')
        else:
            cells.append('<td>未生成</td>')
    rows.append(f'<tr><th>{seed}</th>{"".join(cells)}</tr>')
metrics = []
for condition in data['conditions']:
    result = condition.get('training_result', {})
    metrics.append(f'<li>{names[condition["condition"]]}：状態 {escape(condition["status"])}、総時間 {escape(condition.get("elapsed_seconds", "未完了"))} 秒、学習時間 {escape(result.get("elapsed_seconds", "対象外"))} 秒、学習時最大VRAM {escape(result.get("peak_allocated_bytes", "対象外"))} bytes</li>')
document = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>LoRA修正の品質比較</title>
<style>body{{font-family:system-ui;margin:24px;background:#f5f6f0;color:#24362c}}table{{width:100%;border-collapse:collapse}}td{{width:32%;vertical-align:top}}th,td{{padding:8px;border:1px solid #ccd3c8}}img{{width:100%;height:auto}}.table{{overflow:auto}}p{{line-height:1.6}}</style>
<h1>LoRA修正の品質比較</h1><p>学習画像のseed：{escape(data['training_seeds'])}。比較用seed：{escape(data['evaluation_seeds'])}。追加学習：{data['steps']} step。</p>
<p>各条件10枚を同じ生成設定で比較します。修正対象の髪だけでなく、顔・衣装・画風も確認します。評価者と判定数は目視評価後に記録します。現在は{escape(data['status'])}。少数画像で改善の保証はしません。</p>
<p>{escape(data.get('error', ''))}</p><ul>{''.join(metrics)}</ul><div class="table"><table><thead><tr><th>seed</th>{''.join(f'<th>{names[c["condition"]]}</th>' for c in data['conditions'])}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></html>'''
output = args.report.with_suffix('.html')
output.write_text(document)
print(output)
