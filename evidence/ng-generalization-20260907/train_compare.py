"""同一の概念除去計算を、異なるNG入力に適用する隔離比較。"""
import argparse
import asyncio
from html import escape
import json
from pathlib import Path, PureWindowsPath
import sys
from urllib.parse import quote
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evidence/ng-preservation-20260907'))
from backend import workflows
from backend.config import BOX_LORAS
from backend.events import EventStore
from backend.services import Services
from probe_preserve import command, copy_from, copy_to


def lora_filename(path):
    """foxの学習記録はWindowsのパスとして読む。"""
    return PureWindowsPath(path).name


def training_input(baseline, experiment, group, analysis):
    meanings = {r['id']: r['meaning'] for r in analysis['results']}
    concepts = []
    for key in group['case_ids']:
        item = meanings[key]
        if item['question_ja'] or not item['erase_concept_en']:
            raise ValueError(f'{key}の解釈が未確定です。')
        concepts.append(item['erase_concept_en'])
    data = {key: baseline[key] for key in ('model', 'qwen3', 'lora', 'strength', 'prompt', 'negative')}
    data.update(experiment['training'])
    data.update(erase_concept=concepts[0], erase_concepts=concepts)
    return data


def save(root, report):
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    sections = []
    for phase, title in [('preflight', '避ける特徴の指定確認'), ('comparison', '同じ乱数による学習前後')]:
        cards = []
        for item in report['pictures']:
            if item['phase'] != phase:
                continue
            url = '/api/file?path=' + quote(str(Path(item['path']).relative_to(Path.cwd() / '.cache')))
            cards.append(f'<figure><figcaption>{escape(item["label"])}</figcaption><a href="{url}"><img src="{url}" alt="{escape(item["label"])}"></a></figure>')
        sections.append(f'<h2>{title}</h2><div class="images">{"".join(cards)}</div>')
    review = (root / 'review.txt').read_text() if (root / 'review.txt').exists() else '生成画像の評価は未完了です。'
    (root / 'report.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>NG事例の再発抑制比較</title><style>body{font:16px/1.6 system-ui;margin:24px;background:#faf8f5}.images{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}'
        'img{width:100%;height:auto}figure{margin:0;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:700px){.images{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>'
        '<h1>同じ学習方法で、異なるNGを避けられるか</h1><p>本人の13件と研究用の指摘は別々に学習します。元LoRAと本番台帳は維持します。</p>'
        f'<p role="status">{escape(report["status"])}</p><pre>{escape(review)}</pre>{"".join(sections)}'
        f'<details><summary>入力・全条件・実行記録</summary><pre>{escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></html>')


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    analysis = json.loads(args.analysis.read_text())
    experiment = json.loads(args.experiment.read_text())
    baseline = json.loads(args.baseline.read_text())
    baseline = baseline.get('input', baseline)
    condition = {'analysis': analysis, 'experiment': experiment, 'baseline': baseline}
    if (root / 'report.json').exists():
        report = json.loads((root / 'report.json').read_text())
        if any(report[k] != v for k, v in condition.items()):
            raise ValueError('既存の実験と条件が異なります。')
    else:
        report = dict(condition, pictures=[], training={}, started=[], status='準備中')
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    async def generate(name, label, seed, lora, suffix='', phase='comparison'):
        if any(x['name'] == name for x in report['pictures']):
            return
        report['status'] = label + 'を生成中'
        save(root, report)
        graph = workflows.anima_txt2img(baseline['prompt'] + (', ' + suffix if suffix else ''), seed,
            loras=[(lora_filename(lora), baseline['strength'])], negative=baseline['negative'], width=832, height=1216)
        content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
        path = service._write_generated(name + '.png', content)
        report['pictures'].append(dict(name=name, label=label, seed=seed, phase=phase, path=str(path), elapsed_s=elapsed, workflow=graph))
        save(root, report)
    try:
        if args.phase == 'preflight':
            meanings = {r['id']: r['meaning'] for r in analysis['results']}
            for seed in experiment['probe_seeds']:
                await generate(f'probe-base-{seed}', f'通常指定 {seed}', seed, baseline['lora'], phase='preflight')
                for key in experiment['probe_cases']:
                    await generate(f'probe-{key}-{seed}', f'{key}のNG指定 {seed}', seed, baseline['lora'], meanings[key]['erase_concept_en'], 'preflight')
            report['status'] = '指定確認10枚の生成完了・目視評価前'
        else:
            if not args.review:
                raise ValueError('指定確認の実測評価を記録してから学習してください。')
            report['preflight_review'] = args.review
            for group in experiment['groups']:
                key = group['id']
                if key in report['training']:
                    continue
                if key in report['started']:
                    raise RuntimeError('既存の学習結果を回収してください。重複学習は行いません。')
                data = training_input(baseline, experiment, group, analysis)
                config = root / (key + '-input.json')
                config.write_text(json.dumps(data, ensure_ascii=False, indent=2))
                remote = 'C:/sf/' + root.name + '-' + key
                output = BOX_LORAS.replace('\\', '/') + '/' + root.name + '-' + key + '.safetensors'
                await command(['ssh', 'fox', 'pwsh.exe', '-NoProfile', '-Command', 'New-Item', '-ItemType', 'Directory', '-Force', '-Path', remote], root / (key + '-prepare.log'))
                for path, dest in [(ROOT / 'box/esd_train.py', 'esd_train.py'), (ROOT / 'box/esd_loss.py', 'esd_loss.py'), (config, 'input.json')]:
                    await copy_to(path, remote + '/' + dest)
                response = await service.comfy.client.post(service.comfy.base_url + '/free', json={'unload_models': True, 'free_memory': True})
                response.raise_for_status()
                report['started'].append(key)
                report['status'] = group['label'] + 'を隔離学習中'
                save(root, report)
                await command(['ssh', 'fox', 'C:/sf/venv/Scripts/python.exe', remote + '/esd_train.py', '--sd-scripts', 'C:/sd-scripts', '--input', remote + '/input.json', '--output', output], root / (key + '-train.log'))
                receipt = root / (key + '-training.json')
                await copy_from(output.replace('.safetensors', '.json'), receipt)
                report['training'][key] = json.loads(receipt.read_text())
                save(root, report)
            for seed in experiment['comparison_seeds']:
                await generate(f'before-{seed}', f'学習前 {seed}', seed, baseline['lora'])
                for group in experiment['groups']:
                    await generate(f'{group["id"]}-{seed}', f'{group["label"]}・学習後 {seed}', seed, report['training'][group['id']]['output'])
            report['status'] = '3条件の学習と40枚の比較生成完了・目視評価前'
        save(root, report)
    except Exception as error:
        report.update(status='処理失敗', error=str(error))
        save(root, report)
        raise
    finally:
        await service.comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('analysis', 'experiment', 'baseline', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--phase', choices=['preflight', 'train'], required=True)
    parser.add_argument('--review')
    asyncio.run(main(parser.parse_args()))
