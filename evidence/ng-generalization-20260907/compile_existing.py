"""既存製品と同じ解釈接続・設定で、NG特徴を共通の学習入力へ変換する。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from probe import ROOT, parse_meaning, save
from backend.intent_cli import MODEL, command, check_events


SCHEMA = {'type': 'object', 'additionalProperties': False, 'properties': {
    'observed_ng_ja': {'type': ['string', 'null']}, 'erase_concept_en': {'type': ['string', 'null']},
    'evidence_ja': {'type': 'string'}, 'preserve_ja': {'type': 'array', 'items': {'type': 'string'}},
    'question_ja': {'type': ['string', 'null']}},
    'required': ['observed_ng_ja', 'erase_concept_en', 'evidence_ja', 'preserve_ja', 'question_ja']}


def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = json.loads(args.source.read_text())
    report = {k: source[k] for k in ('cases', 'batch', 'instructions')}
    report.update(model=MODEL, results=[], status='準備中', training_performed=False,
                  connection='製品のintent_cli.commandと同じ設定。研究用の出力schemaと指示を使用。')
    if (root / 'report.json').exists():
        previous = json.loads((root / 'report.json').read_text())
        if any(previous[k] != report[k] for k in ('cases', 'batch', 'instructions', 'model')):
            raise ValueError('実験条件が変わっています。')
        report = previous
    if args.revise:
        report['revision_instruction'] = 'erase_concept_enは画像に存在する否定された状態を肯定形で命名してください。without、not、no等で存在しない物を付け足さず、現在の状態を表す名称にしてください。日本語の観察から単純に全文翻訳せず、消す対象の名称だけにします。'
        revised = set(args.revise)
        report.setdefault('previous_results', []).extend(x for x in report['results'] if x['id'] in revised)
        report['results'] = [x for x in report['results'] if x['id'] not in revised]
    env = os.environ.copy()
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL'):
        env.pop(key, None)
    try:
        for case in report['cases']:
            if any(x['id'] == case['id'] and 'meaning' in x for x in report['results']):
                continue
            report['status'] = case['id'] + 'の学習入力を作成中'
            save(root, report)
            with tempfile.TemporaryDirectory(prefix='sprite-ng-meaning-') as temp:
                work = Path(temp)
                (work / 'schema.json').write_text(json.dumps(SCHEMA))
                picture = args.images.resolve() / f'candidate-{case["number"]:02}.png'
                prompt = report['instructions'] + '\n入力：' + json.dumps({'comment': case['comment'], 'rating': 'NG'}, ensure_ascii=False)
                if args.revise:
                    prompt += '\n' + report['revision_instruction']
                started = time.monotonic()
                outcome = subprocess.run(command(work, [picture]), input=prompt, text=True, capture_output=True, cwd=work, env=env)
                suffix = '-revised' if args.revise else ''
                (root / (case['id'] + suffix + '-events.jsonl')).write_text(outcome.stdout)
                (root / (case['id'] + suffix + '-stderr.txt')).write_text(outcome.stderr)
                if outcome.returncode:
                    raise RuntimeError(f'{case["id"]}の解釈失敗。保存した実行ログを確認してください。')
                check_events(outcome.stdout)
                raw = (work / 'result.json').read_text()
                report['results'].append({'id': case['id'], 'raw': raw, 'meaning': parse_meaning(raw),
                                          'elapsed_s': round(time.monotonic() - started, 2)})
                save(root, report)
        report['status'] = '全16件の学習入力作成完了・内容評価前'
        save(root, report)
    except Exception as error:
        report.update(status='解釈失敗', error=str(error))
        save(root, report)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revise', nargs='+')
    main(parser.parse_args())
