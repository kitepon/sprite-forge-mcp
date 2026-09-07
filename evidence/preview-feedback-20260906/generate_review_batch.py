"""元LoRAから番号付き候補を生成する。選別・学習は行わない。"""
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
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    cards = []
    for number in range(1, 21):
        item = next((item for item in report['pictures'] if item['number'] == number), None)
        if item:
            url = '/api/file?path=' + quote(str(Path(item['path']).relative_to(Path.cwd() / '.cache')))
            content = f'<a href="{url}" target="_blank"><img src="{url}" alt="候補{number:02}"></a>'
        else:
            content = '<p>生成待ち</p>'
        cards.append(f'<article><h2>候補 {number:02}</h2>{content}</article>')
    (root / 'report.html').write_text(
        '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>NGを選ぶ20枚</title><style>body{font:16px sans-serif;margin:20px;background:#faf8f5}'
        '.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}'
        'article{background:white;border:1px solid #ccc;padding:8px}h2{font-size:20px;margin:4px}img{width:100%;height:auto}'
        '@media(max-width:1000px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>NGを選ぶ20枚</h1>'
        '<p>元のキャラクターLoRAから新規生成。画像を押すと拡大できます。NGの候補番号と理由をチャットで伝えてください。</p>'
        '<p>未選択の画像をOK判定にはしません。追加学習はまだ行いません。</p>'
        f'<p>{escape(report["status"])}</p><div class="grid">{"".join(cards)}</div>'
        f'<details><summary>生成条件と記録</summary><pre>{escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></html>')


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'report.json').exists():
        report = json.loads((root / 'report.json').read_text())
    else:
        source = json.loads(args.baseline.read_text())['input']
        data = {key: source[key] for key in ('model', 'lora', 'strength', 'prompt', 'negative')}
        report = {'input': data, 'first_seed': 501, 'pictures': [], 'status': '生成開始', 'training_started': False}
    data = report['input']
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    try:
        for number in range(1, 21):
            if any(item['number'] == number for item in report['pictures']):
                continue
            report['status'] = f'{number} / 20 枚目を生成中'
            save(root, report)
            seed = report['first_seed'] + number - 1
            graph = workflows.anima_txt2img(data['prompt'], seed, loras=[(Path(data['lora']).name, data['strength'])],
                                           negative=data['negative'], width=832, height=1216)
            content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
            path = service._write_generated(f'candidate-{number:02}.png', content)
            report['pictures'].append({'number': number, 'seed': seed, 'path': str(path), 'elapsed_s': elapsed})
            save(root, report)
        report['status'] = '20枚の生成完了。NGの指定を待っています。'
        save(root, report)
    except Exception as error:
        report.update(status='生成失敗', error=str(error))
        save(root, report)
        raise
    finally:
        await service.comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
