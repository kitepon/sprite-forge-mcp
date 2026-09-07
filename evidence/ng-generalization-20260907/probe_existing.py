"""既存の製品コメント解釈を隔離した画像入力で比較する。台帳は更新しない。"""
import argparse
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.intent_cli import run


def main(args):
    source = json.loads(args.source.read_text())
    report = {'method': '既存製品のpreview_review解釈', 'cases': source['cases'][:5],
              'results': [], 'training_performed': False, 'status': '実行中'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        report = json.loads(args.output.read_text())
    for case in report['cases']:
        if any(x['id'] == case['id'] for x in report['results']):
            continue
        picture = args.images / f'candidate-{case["number"]:02}.png'
        packet = {'input': {'stage': 'preview_review', 'image_id': case['id'], 'rating': 'ng',
                            'comment': case['comment'], 'target': '', 'references': []},
                  'images': [base64.b64encode(picture.read_bytes()).decode('ascii')]}
        report['status'] = case['id'] + 'を解釈中'
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        result = run(packet)
        report['results'].append({'id': case['id'], **result})
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    report['status'] = '既存処理の5件が完了・評価前'
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
