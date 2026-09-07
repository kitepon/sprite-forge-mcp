"""共通NG実験の全工程を、既存のファイル配信面にまとめて表示する。"""
from html import escape
import json
from pathlib import Path


def main():
    root = Path('.cache/ng-generalization-overview-20260907')
    root.mkdir(parents=True, exist_ok=True)
    entries = [
        ('ng-generalization-20260907', '画像と指摘を一度に解釈', '本人の13件と研究用の3件。消す対象が逆になる誤りを確認。'),
        ('ng-generalization-two-stage-20260907', '画像観察と指摘の解釈を分離', '共通の5件で比較。不要な質問や対象の拡大が残った。'),
        ('ng-generalization-compiled-20260907', '製品と同じ解釈設定で学習入力を作成', '同じ16件を処理。2件は一般的な補足指示で再解釈し、前の応答も保存。'),
        ('ng-generalization-training-20260907', '同じ学習計算で3種類のNGを比較', '本人のNG、研究用の衣装NG、研究用の構図NGを独立に学習。')]
    sections = []
    for directory, title, text in entries:
        path = Path('.cache') / directory
        report = json.loads((path / 'report.json').read_text())
        if not (path / 'report.html').is_file():
            raise FileNotFoundError(f'表示用HTMLがありません: {directory}')
        sections.append(f'<article><h2><a href="/api/file?path={directory}/report.html">{title}</a></h2>'
                        f'<p>{text}</p><p>{escape(report["status"])}</p></article>')
    existing = json.loads(Path('.cache/ng-generalization-existing-20260907/report.json').read_text())
    rows = []
    for case in existing['cases']:
        result = next(x for x in existing['results'] if x['id'] == case['id'])
        rows.append(f'<tr><td>{escape(case["origin"])}<br>{escape(case["comment"])}</td><td><pre>{escape(json.dumps(result["proposal"], ensure_ascii=False, indent=2))}</pre></td></tr>')
    review = (root / 'review.txt').read_text() if (root / 'review.txt').exists() else '学習結果はまだ評価していません。'
    assessment_path = Path('.cache/ng-generalization-training-20260907/assessment.json')
    metrics = ''
    if assessment_path.exists():
        assessment = json.loads(assessment_path.read_text())
        results = assessment['rows']
        cells = []
        for key, label in [('owner', '本人のNG'), ('collar', '研究用：襟の毛皮'), ('layout', '研究用：複数カット')]:
            before = sum(row[key + '_ng_before'] for row in results)
            after = sum(row[key + '_ng_after'] for row in results)
            cells.append(f'<tr><td>{label}</td><td>{before}/{len(results)}</td><td>{after}/{len(results)}</td></tr>')
        metrics = ('<table><thead><tr><th>避けたいもの</th><th>学習前の再発</th><th>学習後の再発</th></tr></thead><tbody>'
                   + ''.join(cells) + '</tbody></table><p>実験担当AIによる目視分類。本人の採否ではありません。'
                   '<a href="/api/file?path=ng-generalization-training-20260907/assessment.json">全10組の目視記録</a></p>')
    (root / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>NG事例を出にくくする共通方法の実験</title><style>body{font:17px/1.6 system-ui;max-width:1000px;margin:24px auto;padding:0 16px;background:#faf8f5}'
        'article{padding:12px 20px;background:white;margin:12px 0}h1{font-size:26px}h2{font-size:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}td{border-bottom:1px solid #bbb;padding:10px;vertical-align:top}</style>'
        '<h1>NGとした事例を、次から出にくくできるか</h1><p>髪型はサンプルの一つ。同じ処理を衣装と構図にも適用し、指摘に応じて避ける対象が変わるかを確かめます。</p>'
        '<p>研究用の指摘は本人の採否と分け、元のモデルと本番の制作データを維持しています。</p>'
        f'<pre>{escape(review)}</pre>{metrics}{"".join(sections)}<details><summary>製品の既存コメント解釈でも同じ5件を確認</summary><table>{"".join(rows)}</table></details></html>')


if __name__ == '__main__':
    main()
