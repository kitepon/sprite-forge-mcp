"""実画像と実CLIで、NGの理由と維持する特徴の区別を記録する。"""
import argparse
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from backend.intent_cli import run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--generated', type=Path, required=True)
parser.add_argument('--sample', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
images = [base64.b64encode(path.read_bytes()).decode() for path in (args.generated, args.sample)]
cases = [('ng', '衣装は合っている'), ('ng', '髪型が違う。衣装は合っている'),
         ('ok', '髪型が違うので直したい'), ('ng', '「衣装が違う」という指摘は間違い。衣装はこのまま。髪型だけ直して')]
with args.output.open('w', encoding='utf-8') as output:
    for rating, comment in cases:
        payload = {'stage': 'preview_review', 'rating': rating, 'comment': comment, 'focus': [],
                   'references': [{'kind': 'generated', 'id': 'ng-image'}, {'kind': 'sample', 'index': 0}]}
        result = run({'input': payload, 'images': images})
        output.write(json.dumps({'input': payload, 'result': result}, ensure_ascii=False) + '\n')
        output.flush()
        print(comment, result['proposal'], flush=True)
