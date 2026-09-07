"""画像とNG指摘の共通解釈を、本人事例と研究用対照で観測する。"""
import argparse
import asyncio
from html import escape
import json
from pathlib import Path
import sys
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evidence/preview-feedback-20260906'))
from backend.comfy import Comfy
from probe_local_vlm import graph


def cases(selection):
    actual = [{'id': f'owner-{n:02}', 'origin': '本人のNG', 'number': n,
               'comment': selection['per_image_reasons'].get(str(n), selection['reason'])}
              for n in selection['selected_ng_numbers']]
    controls = [
        {'id': 'research-collar', 'origin': '研究用の指摘・本人の採否ではない', 'number': 17,
         'comment': '襟についている毛皮がNG。髪型は変えないで。'},
        {'id': 'research-layout', 'origin': '研究用の指摘・本人の採否ではない', 'number': 10,
         'comment': '同じ画面に複数の人物や別カットが並んでいるのがNG。衣装は変えないで。'},
        {'id': 'research-ambiguous', 'origin': '研究用の指摘・本人の採否ではない', 'number': 17,
         'comment': '衣装は合っている。'}]
    return [actual[0], actual[-1], *controls, *actual[1:-1]]


def parse_meaning(raw):
    text = raw.strip()
    if text.startswith('```json\n') and text.endswith('```'):
        text = text[8:-3].strip()
    value = json.loads(text)
    if set(value) != {'observed_ng_ja', 'erase_concept_en', 'evidence_ja', 'preserve_ja', 'question_ja'}:
        raise ValueError('解釈結果の項目が仕様と異なります。')
    for key in ('observed_ng_ja', 'erase_concept_en', 'question_ja'):
        if value[key] is not None and not isinstance(value[key], str):
            raise ValueError('解釈結果の文字列型が不正です。')
    if not isinstance(value['evidence_ja'], str) or not isinstance(value['preserve_ja'], list) or not all(isinstance(x, str) for x in value['preserve_ja']):
        raise ValueError('観察または保持項目の型が不正です。')
    if value['question_ja']:
        if value['erase_concept_en'] is not None or value['observed_ng_ja'] is not None:
            raise ValueError('解釈が未確定なのに消去対象が指定されています。')
    elif not value['erase_concept_en'] or not value['observed_ng_ja']:
        raise ValueError('確定した解釈に消去対象がありません。')
    return value


def save(root, report):
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    cards = []
    for case in report['cases']:
        result = next((r for r in report['results'] if r['id'] == case['id']), {})
        url = '/api/file?path=' + quote(report['batch'] + f'/generated/candidate-{case["number"]:02}.png')
        meaning = result.get('meaning')
        if meaning:
            body = (f'<p><b>避ける状態：</b>{escape(meaning["observed_ng_ja"] or "未確定")}</p>'
                    f'<p><b>理由：</b>{escape(meaning["evidence_ja"])}</p>'
                    f'<p><b>残すという指摘：</b>{escape("、".join(meaning["preserve_ja"]) or "明示なし")}</p>'
                    f'<p><b>質問：</b>{escape(meaning["question_ja"] or "なし")}</p>'
                    f'<details><summary>生成モデルへ渡す指定</summary><p>{escape(meaning["erase_concept_en"] or "未確定")}</p></details>')
        else:
            body = '<p>解釈は未確定です。</p>'
            if result.get('raw'):
                body += f'<details><summary>受け取った応答</summary><pre>{escape(result["raw"])}</pre></details>'
        cards.append(f'<article><h2>元画像{case["number"]} — {escape(case["origin"])}</h2>'
                     f'<img src="{url}" alt="入力画像 {case["number"]}"><p><b>指摘：</b>{escape(case["comment"])}</p>'
                     + body + '</article>')
    review = (root / 'review.txt').read_text() if (root / 'review.txt').exists() else '解釈の目視評価は未完了。学習は未実行。'
    (root / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>NG事例の共通解釈実験</title><style>body{font:16px/1.6 system-ui;margin:24px;background:#faf8f5}article{background:white;padding:16px;margin:16px 0;display:flow-root}'
        'img{width:200px;max-width:40%;float:left;margin-right:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{font-size:18px}</style>'
        '<h1>画像と指摘から避ける特徴を取り出す実験</h1><p>全事例に同じ処理・同じ指示を適用。本人のNGと研究用の指摘を区別し、未選択画像をOKに変更しません。</p>'
        f'<p role="status">{escape(report["status"])}</p><pre>{escape(review)}</pre>{"".join(cards)}'
        f'<details><summary>実行条件・生の応答・失敗記録</summary><pre>{escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></html>')


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    selection = json.loads(args.selection.read_text())
    instructions = Path(__file__).with_name('instructions.txt').read_text()
    current = {'cases': cases(selection), 'instructions': instructions, 'model': args.model, 'batch': selection['batch']}
    if (root / 'report.json').exists():
        report = json.loads((root / 'report.json').read_text())
        if any(report[k] != v for k, v in current.items()):
            raise ValueError('実験の入力が変わっています。')
    else:
        report = dict(current, results=[], status='準備中', training_performed=False)
    comfy = Comfy()
    try:
        for case in report['cases']:
            item = next((r for r in report['results'] if r['id'] == case['id']), None)
            if item and 'meaning' in item:
                continue
            report['status'] = f'{case["id"]}を解析中'
            save(root, report)
            if item is None:
                path = Path('.cache') / report['batch'] / 'generated' / f'candidate-{case["number"]:02}.png'
                uploaded = await comfy.upload(path.read_bytes(), f'general-ng-{case["id"]}.png')
                workflow = graph(args.model, instructions + '\n入力：' + json.dumps({'comment': case['comment'], 'rating': 'NG'}, ensure_ascii=False), uploaded)
                workflow['2']['inputs']['max_tokens'] = 1400
                item = {'id': case['id'], 'workflow': workflow, 'started': time.time()}
                report['results'].append(item)
                save(root, report)
                item['prompt_id'] = await comfy.submit(workflow, 'sprite-generic-ng')
                save(root, report)
            if 'prompt_id' not in item:
                raise RuntimeError('投入状態が不明です。キューを確認してください。')
            while True:
                history = await comfy.history(item['prompt_id'])
                if history:
                    if history['status']['status_str'] == 'error':
                        item['history'] = history
                        raise RuntimeError(str(history['status']))
                    if history['status']['completed']:
                        item['raw'] = '\n'.join(history['outputs']['3']['text'])
                        item['elapsed_s'] = round(time.time() - item['started'], 2)
                        save(root, report)
                        item['meaning'] = parse_meaning(item['raw'])
                        save(root, report)
                        break
                await asyncio.sleep(3)
        report['status'] = '全16件の解釈完了・内容の評価前'
        save(root, report)
    except Exception as error:
        report.update(status='解析失敗', error=str(error))
        save(root, report)
        raise
    finally:
        await comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--model', default='Qwen3-VL-8B-Instruct')
    asyncio.run(main(parser.parse_args()))
