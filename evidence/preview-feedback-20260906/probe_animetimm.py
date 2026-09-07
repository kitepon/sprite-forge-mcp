"""選択済み20枚をComfyUIで一括解析し、髪型スコアを比較表示する。"""
import argparse
import asyncio
from html import escape
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.comfy import Comfy


def graph(names):
    workflow = {}
    previous = None
    for index, name in enumerate(names):
        current = str(index * 2 + 1)
        workflow[current] = {'class_type': 'LoadImage', 'inputs': {'image': name}}
        if previous is not None:
            merged = str(index * 2 + 2)
            workflow[merged] = {'class_type': 'ImageBatch', 'inputs': {'image1': [previous, 0], 'image2': [current, 0]}}
            previous = merged
        else:
            previous = current
    workflow['100'] = {'class_type': 'SpriteAnimeTimm', 'inputs': {'image': [previous, 0]}}
    workflow['101'] = {'class_type': 'PreviewAny', 'inputs': {'source': ['100', 0]}}
    return workflow


def comparisons(report):
    selection = report['selection']
    selected = set(selection['selected_ng_numbers'])
    special = {int(number) for number in selection['per_image_reasons']}
    groups = {'全体理由のNG': selected - special, '未選択・未判定': set(range(1, 21)) - selected}
    groups.update({f'候補{number}：{reason}': {int(number)} for number, reason in selection['per_image_reasons'].items()})
    scores = report['output']['scores']
    tags = [tag for tag in scores[0] if any(term in tag for term in ('hair', 'twintail', 'ponytail', 'braid', 'bob_cut'))]
    return {tag: {label: sum(scores[number - 1][tag] for number in numbers) / len(numbers)
                  for label, numbers in groups.items()} for tag in tags}


def save(root, report):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    body = ''
    if 'output' in report:
        comparison = comparisons(report)
        (root / 'comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2))
        ranked = sorted(comparison, key=lambda tag: max(comparison[tag].values()) - min(comparison[tag].values()), reverse=True)
        labels = list(next(iter(comparison.values())))
        body += '<h2>髪の属性の比較</h2><p>数値はモデルの属性スコアです。差はNG理由の因果的な証明ではありません。髪色・装飾も表示しますが、自動的に消去対象にはしません。</p><table><tr><th>属性</th>'
        body += ''.join(f'<th>{escape(label)}</th>' for label in labels) + '</tr>'
        for tag in ranked[:35]:
            body += f'<tr><td>{escape(tag)}</td>' + ''.join(f'<td>{comparison[tag][label]:.3f}</td>' for label in labels) + '</tr>'
        body += '</table><h2>全20枚</h2><div class="grid">'
        for number, scores in enumerate(report['output']['scores'], 1):
            selected = number in report['selection']['selected_ng_numbers']
            reason = report['selection']['per_image_reasons'].get(str(number), report['selection']['reason']) if selected else '未選択・未判定'
            items = sorted(((tag, scores[tag]) for tag in comparison), key=lambda item: item[1], reverse=True)[:12]
            body += f'<article><h3>候補{number}：{"NG" if selected else "未判定"}</h3><p>{escape(reason)}</p><img src="/api/file?path={report["batch"]}/generated/candidate-{number:02}.png"><pre>'
            body += escape('\n'.join(f'{tag}: {score:.3f}' for tag, score in items)) + '</pre></article>'
        body += '</div>'
    (root / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>AnimeTimmの髪型解析</title><style>body{font:16px/1.6 sans-serif;padding:20px;background:#f7f5f0}table{border-collapse:collapse}td,th{padding:6px;border:1px solid #bbb}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}article{background:white;padding:14px}img{width:100%;height:auto}pre{white-space:pre-wrap}</style>'
        '<h1>AnimeTimmの髪型解析</h1><p>Windowsローカルで全20枚を解析。未選択はOK教材にしません。学習は実行していません。</p>'
        f'<p><strong>{escape(report["status"])}</strong></p>' + body)


async def run(args):
    root = args.output
    report_file = root / 'report.json'
    report = json.loads(report_file.read_text()) if report_file.exists() else {
        'batch': args.batch.name, 'selection': json.loads((args.batch / 'selection.json').read_text()), 'status': '準備中'}
    comfy = Comfy()
    try:
        if 'output' in report:
            save(root, report)
            return
        if 'prompt_id' not in report:
            names = []
            for number in range(1, 21):
                picture = args.batch / f'generated/candidate-{number:02}.png'
                names.append(await comfy.upload(picture.read_bytes(), f'animetimm-{args.batch.name}-{number:02}.png'))
            report['workflow'] = graph(names)
            report['prompt_id'] = await comfy.submit(report['workflow'], 'sprite-animetimm')
        report['status'] = '20枚を解析中'
        save(root, report)
        while True:
            history = await comfy.history(report['prompt_id'])
            if history:
                if history['status']['status_str'] == 'error':
                    raise RuntimeError(json.dumps(history['status'], ensure_ascii=False))
                if history['status']['completed']:
                    report['output'] = json.loads(history['outputs']['101']['text'][0])
                    if len(report['output']['scores']) != 20:
                        raise ValueError('20枚の出力が揃っていません。')
                    report['status'] = '20枚の解析完了'
                    save(root, report)
                    return
            await asyncio.sleep(3)
    except Exception as error:
        report['status'] = f'解析失敗：{error}'
        save(root, report)
        raise
    finally:
        await comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
