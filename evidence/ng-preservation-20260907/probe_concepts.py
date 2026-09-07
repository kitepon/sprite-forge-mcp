"""NG指定の生成比較。学習前に全指摘との対応を画像で確認する。"""
import argparse
import asyncio
from html import escape
import json
from pathlib import Path
import sys
from urllib.parse import quote
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import workflows
from backend.events import EventStore
from backend.services import Services


def save(root, report):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    def url(path):
        return '/api/file?path=' + quote(str(Path(path).relative_to(Path.cwd() / '.cache')))
    rows = []
    for item in report['expected']:
        actual = next((p for p in report['pictures'] if p['name'] == item['name']), None)
        image = (f'<a href="{url(actual["path"])}" target="_blank"><img src="{url(actual["path"])}" alt="{escape(item["label"])}"></a>'
                 if actual else '<p>生成待ち</p>')
        rows.append(f'<figure><figcaption>{escape(item["label"])}・seed {item["seed"]}</figcaption>{image}</figure>')
    sources = []
    for concept in report['config']['concepts']:
        cards = []
        for number in concept['source_numbers']:
            image_path = Path.cwd() / '.cache' / report['config']['source_batch'] / 'generated' / f'candidate-{number:02}.png'
            cards.append(f'<figure><figcaption>元NG {number}</figcaption><a href="{url(image_path)}"><img src="{url(image_path)}" alt="元NG {number}"></a></figure>')
        sources.append(f'<h3>{escape(concept["label"])}</h3><p>本人の指摘：{escape(concept["reason"])}</p>'
                       f'<p>画像の観察：{escape(concept["observation"])}</p><div class="sources">{"".join(cards)}</div>')
    review = (root / 'review.txt').read_text(encoding='utf-8') if (root / 'review.txt').exists() else '画像の確認は未完了です。'
    (root / 'report.html').write_text(
        '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>NG指定と特徴保持の実験</title><style>body{font:16px system-ui;margin:24px;background:#faf8f5;color:#222}'
        '.images{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.sources{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}'
        'figure{margin:0;background:white;padding:8px}img{width:100%;height:auto}figcaption{font-weight:bold}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        '@media(max-width:700px){.images,.sources{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>'
        '<h1>NG指定と特徴保持の実験</h1><p>元LoRAを維持し、本人のNG指摘から除去する特徴を確認します。未選択の画像は未判定のままです。</p>'
        f'<p role="status">状態：{escape(report["status"])} — {len(report["pictures"])} / {len(report["expected"])} 枚</p>'
        f'<pre>{escape(review)}</pre><div class="images">{"".join(rows)}</div>'
        '<details><summary>元のNG画像・本人の指摘と今回の解釈</summary>' + ''.join(sources) + '</details>'
        f'<details><summary>全条件と実行記録</summary><pre>{escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></html>',
        encoding='utf-8')


def expected_pictures(config):
    return [
        {'name': f'{condition["id"]}-{seed}', 'seed': seed, 'label': condition['label'], 'suffix': condition['text']}
        for seed in config['preflight_seeds']
        for condition in [{'id': 'base', 'label': '元の通常指定', 'text': ''}, *config['concepts']]
    ]


async def main(args):
    root = args.output.resolve()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    data = baseline.get('input', baseline)
    if (root / 'report.json').exists():
        report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
        if report['config'] != config or report['input'] != data:
            raise ValueError('既存実験と入力が異なります。新しい保存先を指定してください。')
        if report.get('inflight'):
            raise RuntimeError('実行中の画像を既存ジョブから回収してください。再投入は行いません。')
    else:
        report = {'status': '準備中', 'config': config, 'input': data,
                  'expected': expected_pictures(config), 'pictures': []}
    save(root, report)
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    try:
        for item in report['expected']:
            if any(p['name'] == item['name'] for p in report['pictures']):
                continue
            prompt = data['prompt'] + (', ' + item['suffix'] if item['suffix'] else '')
            graph = workflows.anima_txt2img(prompt, item['seed'], loras=[(Path(data['lora']).name, data['strength'])],
                                           negative=data['negative'], **config['generation'])
            job_id = str(uuid.uuid4())
            report.update(status=item['label'] + 'を生成中', inflight={'name': item['name'], 'job_id': job_id})
            save(root, report)
            content, elapsed = await service._run_edit(job_id, graph)
            path = service._write_generated(item['name'] + '.png', content)
            report['pictures'].append({**item, 'path': str(path), 'prompt': prompt, 'elapsed_s': elapsed, 'workflow': graph})
            report.pop('inflight')
            save(root, report)
        report['status'] = '指定確認の全画像を生成済み・目視評価前'
        save(root, report)
    except Exception as error:
        report.update(status='処理失敗', error=str(error))
        save(root, report)
        raise
    finally:
        await service.comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    asyncio.run(main(parser.parse_args()))

