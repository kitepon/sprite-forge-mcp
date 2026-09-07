"""NG学習の目標と最終LoRAの一致を、計測した全条件で表示する。"""
from html import escape
import json
from pathlib import Path
import shutil
import statistics

root = Path('.cache/ng-objective-audit-20260907')
root.mkdir(exist_ok=True)
paths = [Path('.cache/ng-objective-audit-20260907.json'), Path('.cache/ng-objective-audit-20260907-905.json')]
records = [json.loads(p.read_text()) for p in paths]
for p, r in zip(paths, records, strict=True):
    shutil.copyfile(p, root / f'seed-{r["seed"]}.json')
    if r['same_weights_branch_max_error'] != 0:
        raise ValueError('元重み同士の比較が一致しません。')
all_rows = [dict(x,seed=r['seed']) for r in records for x in r['rows']]
labels = {'owner':'本人のNG', 'collar':'研究用：襟のNG', 'layout':'研究用：構図のNG'}
table = []
for group in labels:
    for t in [1,.75,.5,.25]:
        rows = [r for r in all_rows if r['group']==group and r['timestep']==t]
        ratio = statistics.mean(r['error_ratio'] for r in rows)
        cosine = statistics.mean(r['cosine'] for r in rows)
        table.append(f'<tr><td>{labels[group]}</td><td>{t}</td><td class="{"bad" if ratio>1 else "good"}">{ratio:.3f}倍</td><td>{sum(r["error_ratio"]<1 for r in rows)}/{len(rows)}</td><td>{cosine:.3f}</td></tr>')
training = []
for g in labels:
    r = json.loads(Path(f'.cache/ng-generalization-training-20260907/{g}-training.json').read_text())
    rows = r['steps']
    training.append({'group':g,'closer':sum(x['loss']<x['concept_delta_mse'] for x in rows),'farther':sum(x['loss']>x['concept_delta_mse'] for x in rows),'total':len(rows)})
(root / 'training-comparison.json').write_text(json.dumps(training,ensure_ascii=False,indent=2))
(root / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
 '<title>LoRAは狙った方向に更新されたか</title><style>body{font:17px/1.7 system-ui;max-width:1100px;margin:24px auto;padding:0 16px;background:#faf8f5}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #bbb}.bad{color:#ae2424}.good{color:#176148}pre{white-space:pre-wrap}.scroll{overflow:auto}</style>'
 '<h1>LoRAは狙った方向に更新されたか</h1><p role="status">保存済みLoRAの診断完了・再学習なし</p>'
 '<p><strong>数値は更新されていましたが、学習目標へ一貫して近づく更新にはなっていませんでした。</strong>目標へ近づく条件と遠ざかる条件が混在しています。NG発生率の改善がないという前回の観測と合わせ、現状の更新方法を有効と判定できません。</p>'
 '<h2>何を更新していたか</h2><p>NG画像と指摘 → 短い特徴文 → 元モデルの予測から除去用の目標を作成 → 画像生成モデルのLoRAを更新。</p>'
 '<p>変更したのはrank 16のLoRAの280層・560配列です。文章の追記だけではありません。一方、NG画像の画素・その画像の潜在表現は、この学習器に入りません。本人の13件は13個の特徴文に変換し、各2回、合計26回更新していました。画像ごとの形をどれだけ保持できたかは未検証です。</p>'
 '<h2>同じ入力で更新前後を比較</h2><p>学習に使っていない乱数904・905の2本。元モデルで8段階の生成途中状態を作り、4時点で元LoRAと保存済み最終LoRAを比較しました。文章・途中状態・時刻は同一。元重みを両方の経路で使った場合の予測差は0でした。</p>'
 '<p>誤差比が1未満なら元LoRAより学習目標に近く、1超なら遠い。方向の一致度は1で同方向、0で直交、負なら逆方向です。これは学習器自身の数値目標との一致であり、実画像のNG判定ではありません。</p>'
 f'<div class="scroll"><table><tr><th>条件</th><th>時刻（1から0へ生成）</th><th>誤差比の平均</th><th>目標に近づいた数</th><th>方向の一致度の平均</th></tr>{"".join(table)}</table></div>'
 '<p>本人NGの13個には同じ特徴文が複数含まれます。表の件数を独立した統計標本数や成功率とは扱いません。2本の生成経路・4時点だけの診断です。</p>'
 '<h2>学習記録の読み直し</h2><p>本人NGは26回中19回、各更新直前の重みが、その回の目標から元LoRAより遠い状態でした。毎回、文章・ノイズ・時刻が変わるため、最初と最後のlossだけを比べても学習改善の証拠になりません。最終LoRAの固定入力評価は上表です。</p>'
 '<h2>確認できた点と残る原因</h2><p>除去目標の引き算は著者のESD実装と同形で、Animaの時刻入力0〜1も学習器の実装に一致します。符号や時刻単位の取り違えは見つかりませんでした。一方、短い文章が個別NGを表すか、異なるNGを同じ条件へ交互に学習して相殺するか、更新回数や学習率が適切かは原因未確定です。ここを確定せずに更新量だけ増やしても解決とはいえません。</p>'
 '<p>新しいモデル学習・本番台帳変更は行っていません。</p>'
 '<h2>全測定値と一次資料</h2><ul><li><a href="/api/file?path=ng-objective-audit-20260907/seed-904.json">乱数904の全測定値</a></li><li><a href="/api/file?path=ng-objective-audit-20260907/seed-905.json">乱数905の全測定値</a></li>'
 '<li><a href="/api/file?path=ng-load-audit-20260907/report.html">前回の保存・読込み監査</a></li>'
 '<li><a href="https://github.com/rohitgandikota/erasing/blob/main/utils/esd_trainer.py">ESD著者の実装</a></li>'
 '<li><a href="https://github.com/kohya-ss/sd-scripts/blob/37a1cbbc5725ed2a3575506e7bd2001c9908ac92/anima_train_network.py">Anima学習器の実装</a></li></ul>')
print(json.dumps(training,ensure_ascii=False))
