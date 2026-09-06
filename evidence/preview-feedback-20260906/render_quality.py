"""比較記録を、全画像を見比べられるHTMLへ変換する。合否の自動判定はしない。"""
import argparse
import html
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('report', type=Path)
parser.add_argument('--review', type=Path, help='目視評価の記録')
args = parser.parse_args()
data = json.loads(args.report.read_text())
review = json.loads(args.review.read_text()) if args.review else None
names = {'before': '学習前', 'ok_only': 'OKのみ追加学習', 'preference': 'OKとNGの選好学習'}
states = {'running': '実行中', 'completed': '完了', 'failed': '失敗', 'awaiting_visual_review': '生成完了・目視評価待ち'}
escape = lambda value: html.escape(str(value), quote=True)
rows = []
for seed in data['evaluation_seeds']:
    cells = []
    for condition in data['conditions']:
        picture = next((p for p in condition.get('pictures', []) if p['seed'] == seed), None)
        if picture:
            path = escape(f"generated/{Path(picture['path']).name}")
            cells.append(f'<td><a href="{path}"><img src="{path}" alt="{escape(names[condition["condition"]])} seed {seed}"></a></td>')
        else:
            cells.append('<td>未生成</td>')
    rows.append(f'<tr><th>{seed}</th>{"".join(cells)}</tr>')
metrics = []
for condition in data['conditions']:
    result = condition.get('training_result', {})
    seconds = lambda value: f'{value:.1f}秒' if isinstance(value, (int, float)) else '未記録'
    memory = f'{result["peak_allocated_bytes"] / 1024**3:.2f} GiB' if 'peak_allocated_bytes' in result else '対象外'
    metrics.append(f'<li>{names[condition["condition"]]}：{states[condition["status"]]}。今回の実行 {seconds(condition.get("elapsed_seconds"))}、学習 {seconds(result.get("elapsed_seconds"))}、学習時最大VRAM {memory}</li>')
assessment = '<p>目視評価は未記録です。</p>'
if review:
    lines = []
    for condition, values in review['conditions'].items():
        count = len(values['reviewed_seeds'])
        labels = {'twintails': 'ツインテール', 'violet_eyes': '紫の瞳', 'outfit_family': '衣装の基本特徴'}
        scores = '、'.join(f'{labels[key]} {len(values[key])}/{count}枚' for key in review['criteria'])
        lines.append(f'<li>{names[condition]}：{scores}<p>{escape(values["notes"])}</p></li>')
    assessment = f'<p>評価者：{escape(review["evaluator"])}。{escape(review["date"])}</p><ul>{"".join(lines)}</ul><details><summary>評価基準と中断の記録</summary><p>{escape(" ／ ".join(review["criteria"].values()))}</p><p>{escape(review.get("interruption", ""))}</p><p>今回の実行時間は再開前に中断した処理の時間を含みません。</p></details>'
document = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>LoRA修正の品質比較</title>
<style>body{{font-family:system-ui;margin:24px;background:#f5f6f0;color:#24362c}}table{{width:100%;border-collapse:collapse}}td{{width:32%;vertical-align:top}}th,td{{padding:8px;border:1px solid #ccd3c8}}img{{width:100%;height:auto}}.table{{overflow:auto}}p{{line-height:1.6}}</style>
<h1>LoRA修正の品質比較</h1><p>学習画像のseed：{escape(data['training_seeds'])}。比較用seed：{escape(data['evaluation_seeds'])}。追加学習：{data['steps']} step。</p>
<p>各条件10枚を同じ生成設定で比較します。現在は{states[data['status']]}。少数画像で改善の保証はしません。</p>{assessment}
<p>{escape(data.get('error', ''))}</p><ul>{''.join(metrics)}</ul><div class="table"><table><thead><tr><th>seed</th>{''.join(f'<th>{names[c["condition"]]}</th>' for c in data['conditions'])}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></html>'''
output = args.report.with_suffix('.html')
output.write_text(document)
print(output)
