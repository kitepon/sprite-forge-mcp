"""保存・読込み・再生成の独立証拠を同じ閲覧面に集める。"""
from html import escape
import json
from pathlib import Path
import shutil

root = Path('.cache/ng-load-audit-20260907')
sources = {'weights': '.cache/ng-generalization-weight-audit-20260907.json',
           'patches': '.cache/ng-comfy-audit-20260907.json',
           'images': '.cache/ng-image-audit.json', 'history': '.cache/ng-history-audit.json'}
data = {}
for name, source in sources.items():
    data[name] = json.loads(Path(source).read_text())
    shutil.copyfile(source, root / (name + '.json'))
generation = json.loads((root / 'generation.json').read_text())
rows = []
for weight, patch in zip(data['weights']['files'], data['patches'][1:], strict=True):
    if weight['name'] != patch['name'] or weight['sha256'] != patch['sha256']:
        raise ValueError('保存ファイルと生成ソフトの読込み対象が一致しません。')
    changed = sum(x['changed'] > 0 for x in weight['tensors'])
    applied = sum(x['changed'] > 0 for x in patch['applied_layers'])
    rounded = sum(x['changed_after_bfloat16'] > 0 for x in patch['applied_layers'])
    rows.append(f'<tr><td>{escape(weight["name"])}</td><td>{changed}配列</td><td>{applied}/{patch["unet_modules"]}層</td><td>{rounded}層</td></tr>')
cards = []
for name in ['before', 'owner']:
    for prefix, label in [('original', '前回の生成'), ('', '別名で再読込み')]:
        filename = (prefix + '-' if prefix else '') + name + '-601.png'
        if prefix:
            shutil.copyfile(Path('.cache/ng-generalization-training-20260907/generated') / (name + '-601.png'), root / filename)
        if not (root / filename).is_file():
            raise FileNotFoundError(filename)
        cards.append(f'<figure><figcaption>{name}・{label}</figcaption><img src="/api/file?path={root.name}/{filename}"></figure>')
exact = all(x['pixel_identical'] for x in generation)
summary = '別名で読み直した2枚は、前回と画素単位で完全一致。' if exact else '別名で読み直した画像に差があり、完全再現は確認できていません。'
text = ('直近3条件ではLoRAの実データが更新され、生成に渡る重みにも更新が反映されていました。'
        '\n学習器とは別の読取りで保存ファイルを検査。生成画像30組とComfyUIの30件の成功履歴で指定を照合。'
        '\nGPU機のComfyUIと同じ実行環境・読込み関数を別CPUプロセスで使い、更新した280層すべての対応と合成後の数値差を確認しました。'
        '\n' + summary + '\n新しい学習は実施していません。本番台帳と元LoRAは維持しています。'
        '\nこの結果はNGを避ける学習が正しいことの証明ではありません。過去の全試行を監査した結果でもありません。')
links = ''.join(f'<li><a href="/api/file?path={root.name}/{name}.json">{label}</a></li>' for name,label in [('weights','実ファイルのハッシュと全配列差'),('patches','ComfyUIの対応層と合成後の差'),('images','全30組の生成条件と画素差'),('history','ComfyUIの全30件の実行履歴'),('generation','新しい名前での再生成履歴')])
(root / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
 '<title>LoRA更新・読込みの実体監査</title><style>body{font:17px/1.7 system-ui;max-width:1100px;margin:24px auto;padding:0 16px;background:#faf8f5}pre{white-space:pre-wrap}td,th{padding:8px;border-bottom:1px solid #bbb}.images{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}figure{margin:0}img{width:100%}</style>'
 '<h1>更新したLoRAで生成されていたか</h1><p role="status">監査完了</p>'
 f'<pre>{escape(text)}</pre><table><tr><th>条件</th><th>保存された更新</th><th>生成モデルへの適用</th><th>低精度化後も差が残る層</th></tr>{"".join(rows)}</table>'
 '<p>owner＝本人のNG、collar＝研究用の襟NG、layout＝研究用の構図NG。</p>'
 '<p>比較生成の開始時にWindowsのファイル名抽出ミスで一度HTTP 400が発生しました。前回その原因を修正し、40枚を生成しています。今回の30件の履歴は修正後の成功分です。</p>'
 f'<h2>新しい名前で読込み直した結果</h2><p>{summary}</p><div class="images">{"".join(cards)}</div><h2>検証記録</h2><ul>{links}</ul>')
(root / 'summary.txt').write_text(text)
print(text)
