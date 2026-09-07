"""OK教材を使わないESDの生成比較と記録を実行する。"""
import argparse
import asyncio
from html import escape
import json
from pathlib import Path
import sys
from urllib.parse import quote
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import box, workflows
from backend.config import BOX_LORAS
from backend.events import EventStore
from backend.services import Services


def save(root, report):
    (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    def picture(item):
        url = '/api/file?path=' + quote(str(Path(item['path']).relative_to(Path.cwd() / '.cache')))
        return f'<figure><a href="{url}"><img src="{url}"></a><figcaption>{escape(item["label"])}</figcaption></figure>'
    review = (root / 'review.txt').read_text() if (root / 'review.txt').exists() else '生成後に画像を確認します。'
    document = ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>NG髪型のESD学習</title><style>body{font:16px sans-serif;margin:24px;background:#faf8f5}'
                '.images{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}figure{margin:0}img{width:100%}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>NG髪型のESD学習</h1>'
                '<p>OK画像・合成・マスクを使わず、記録したNG特徴を抑えるようキャラクターLoRAを更新します。</p>'
                f'<p>状態：{escape(report["status"])}</p><pre>{escape(review)}</pre><div class="images">'
                + ''.join(picture(item) for item in report['pictures'] if not item['name'].startswith('probe-'))
                + '</div><details><summary>学習前のNG文章指定の確認</summary><div class="images">'
                + ''.join(picture(item) for item in report['pictures'] if item['name'].startswith('probe-'))
                + f'</div></details><details><summary>条件と処理記録</summary><pre>{escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre></details></html>')
    (root / 'report.html').write_text(document)


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'report.json').exists():
        report = json.loads((root / 'report.json').read_text())
        data = report['input']
    else:
        baseline = json.loads(args.baseline.read_text())['input']
        data = {key: baseline[key] for key in ('model', 'qwen3', 'lora', 'strength', 'prompt', 'negative', 'seed')}
        data.update(erase_concept='short bob haircut', steps=20, sampling_steps=8, sampling_cfg=4,
                    learning_rate=1e-5, negative_guidance=1, latent_shape=[1, 16, 76, 52])
        if getattr(args, 'concept_file', None):
            if getattr(args, 'weights', None):
                raise ValueError('単一文章と重み付きESDは同時指定できません。')
            data['erase_concept'] = args.concept_file.read_text().strip()
        if getattr(args, 'weights', None):
            data['feature_weights'] = json.loads(args.weights.read_text())
            data['erase_concept'] = ''
            data['steps'] = 2 * len(data['feature_weights']['images'])
            data['comparison_seeds'] = list(range(501, 521))
        report = {'status': '準備中', 'input': data, 'pictures': []}
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    async def command(arguments, logfile):
        with logfile.open('wb') as output:
            process = await asyncio.create_subprocess_exec(*arguments, stdout=output, stderr=asyncio.subprocess.STDOUT)
            if await process.wait():
                raise RuntimeError(f'処理失敗: {logfile}')
    async def generate(name, label, prompt, seed, lora):
        if any(item['name'] == name for item in report['pictures']):
            return
        report['status'] = label + 'を生成中'
        save(root, report)
        graph = workflows.anima_txt2img(prompt, seed, loras=[(lora, data['strength'])],
                                       negative=data['negative'], width=832, height=1216)
        content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
        path = service._write_generated(name + '.png', content)
        report['pictures'].append({'name': name, 'label': label, 'seed': seed, 'path': str(path), 'elapsed_s': elapsed})
        save(root, report)
    source_lora = Path(data['lora']).name
    if args.preflight_review:
        report['preflight_review'] = args.preflight_review
    if getattr(args, 'retry_failed', False):
        if report['status'] != '処理失敗' or 'training' in report:
            raise ValueError('未回収の失敗した学習だけを明示再実行できます。')
        attempts = report.setdefault('failed_attempts', [])
        previous_log = root / f'train-failed-{len(attempts) + 1}.log'
        (root / 'train.log').rename(previous_log)
        attempts.append({'error': report.pop('error'), 'log': str(previous_log)})
        report['training_started'] = False
    try:
        if args.phase == 'preflight':
            for seed in (106, 109):
                await generate(f'probe-base-{seed}', f'通常指定・{seed}', data['prompt'], seed, source_lora)
                await generate(f'probe-bob-{seed}', f'NG髪型を文章指定・{seed}', data['prompt'] + ', ' + data['erase_concept'], seed, source_lora)
            report['status'] = 'NG指定の比較生成完了'
        else:
            if 'preflight_review' not in report:
                raise ValueError('NG指定の画像を確認してから学習を開始してください。')
            remote = 'C:/sf/' + root.name
            lora = root.name + '.safetensors'
            output = BOX_LORAS.replace('\\', '/') + '/' + lora
            if 'training' not in report:
                if report.get('training_started'):
                    raise RuntimeError('既存学習の終了記録を回収してから再開してください。重複学習は行いません。')
                await command(['ssh', 'fox', 'pwsh.exe', '-NoProfile', '-Command', 'New-Item', '-ItemType', 'Directory', '-Force', '-Path', remote], root / 'prepare.log')
                config = root / 'input.json'
                config.write_text(json.dumps(data))
                for local, destination in [(Path('box/esd_train.py'), remote + '/esd_train.py'),
                                           (Path('box/esd_loss.py'), remote + '/esd_loss.py'), (config, remote + '/input.json')]:
                    code, message = await box.copy_to_box(local, destination)
                    if code:
                        raise RuntimeError(message)
                response = await service.comfy.client.post(service.comfy.base_url + '/free', json={'unload_models': True, 'free_memory': True})
                response.raise_for_status()
                report.update(status='NG髪型を抑える学習中', training_started=True)
                save(root, report)
                await command(['ssh', 'fox', 'C:/sf/venv/Scripts/python.exe', remote + '/esd_train.py',
                               '--sd-scripts', 'C:/sd-scripts', '--input', remote + '/input.json', '--output', output], root / 'train.log')
                code, message = await box.copy_from_box(output.replace('.safetensors', '.json'), root / 'training.json')
                if code:
                    raise RuntimeError(message)
                report['training'] = json.loads((root / 'training.json').read_text())
                save(root, report)
            for seed in data.get('comparison_seeds', (106, 109, *range(301, 311))):
                await generate(f'before-{seed}', f'学習前・{seed}', data['prompt'], seed, source_lora)
                await generate(f'after-{seed}', f'ESD学習後・{seed}', data['prompt'], seed, lora)
            report['status'] = '学習と比較生成完了'
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
    parser.add_argument('--phase', choices=('preflight', 'train'), required=True)
    parser.add_argument('--preflight-review')
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--weights', type=Path)
    parser.add_argument('--concept-file', type=Path)
    asyncio.run(main(parser.parse_args()))
