"""ESDの空間定位確認と、保持項だけを変えた学習比較を実行する。"""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import box, workflows
from backend.config import BOX_LORAS
from backend.events import EventStore
from backend.services import Services
from probe_concepts import save


async def command(arguments, logfile):
    with logfile.open('wb') as output:
        process = await asyncio.create_subprocess_exec(*arguments, stdout=output, stderr=asyncio.subprocess.STDOUT)
        if await process.wait():
            raise RuntimeError(f'処理失敗: {logfile}')


async def copy_from(remote, local):
    code, message = await box.copy_from_box(remote, local)
    if code:
        raise RuntimeError(message)


async def copy_to(local, remote):
    code, message = await box.copy_to_box(local, remote)
    if code:
        raise RuntimeError(message)


def training_input(baseline, config, weight):
    result = {key: baseline[key] for key in ('model', 'qwen3', 'lora', 'strength', 'prompt', 'negative')}
    result.update(config['training'])
    result['erase_concepts'] = [item['text'] for item in config['concepts']]
    result['erase_concept'] = result['erase_concepts'][0]
    result['locality'] = {'phrase': 'hair', 'weight': weight, 'mask_timestep': '最後のEuler更新直前'}
    return result


async def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text(encoding='utf-8'))
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    baseline = baseline.get('input', baseline)
    reportfile = root / 'report.json'
    if reportfile.exists():
        report = json.loads(reportfile.read_text(encoding='utf-8'))
        if report['config'] != config or report['input'] != baseline or report['phase'] != args.phase:
            raise ValueError('既存実験と設定が異なります。')
        if args.retry_localization:
            if args.phase != 'localize' or report['status'] != '処理失敗' or report['training']:
                raise ValueError('未完了の定位診断だけを明示再実行できます。')
            number = len(report.get('failed_attempts', [])) + 1
            previous = root / f'localize-failed-{number}.log'
            (root / 'localize-train.log').rename(previous)
            report.setdefault('failed_attempts', []).append({'error': report.pop('error'), 'log': str(previous)})
            report['started'].remove('localize')
    else:
        report = {'status': '準備中', 'config': config, 'input': baseline, 'phase': args.phase,
                  'pictures': [], 'expected': [], 'training': {}, 'started': []}
        if args.phase == 'localize':
            report['expected'] = [
                {'name': f'{kind}-{step:03}', 'seed': config['training']['seed'],
                 'label': f'教師生成 {step}・' + label}
                for step in range(1, len(config['concepts']) + 1)
                for kind, label in [('sample', '元画像'), ('mask', '髪の空間重み'), ('overlay', '赤色が変更を許す範囲')]
            ]
        else:
            report['expected'] = [
                {'name': f'{kind}-{seed}', 'seed': seed, 'label': label}
                for seed in config['comparison_seeds']
                for kind, label in [('before', '学習前'), ('esd', 'ESD・保持項なし'), ('preserve', 'ESD・保持項あり')]
            ]
    save(root, report)
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    remote = 'C:/sf/' + root.name
    try:
        modes = [('localize', 1)] if args.phase == 'localize' else [('esd', 0), ('preserve', 1)]
        for mode, weight in modes:
            if mode in report['training']:
                continue
            if mode in report['started']:
                raise RuntimeError('既存処理の終了記録を回収してください。重複学習は行いません。')
            if args.phase != 'localize' and not args.localization_review:
                raise ValueError('髪の定位結果を確認してから比較学習を開始してください。')
            report.update(status=mode + 'の準備中', localization_review=args.localization_review)
            save(root, report)
            prepare = f"New-Item -ItemType Directory -Force -Path '{remote}/box','{remote}/tests','{remote}/diagnostics-{mode}'"
            await command(['ssh', 'fox', 'pwsh.exe', '-NoProfile', '-Command', prepare], root / f'{mode}-prepare.log')
            for name in ('esd_train.py', 'esd_loss.py', 'esd_locality.py'):
                await copy_to(Path('box') / name, remote + '/box/' + name)
            await copy_to(Path('tests/test_esd_locality.py'), remote + '/tests/test_esd_locality.py')
            await command(['ssh', 'fox', 'C:/sf/venv/Scripts/python.exe', '-m', 'pytest',
                           remote + '/tests/test_esd_locality.py', '-q'], root / f'{mode}-tests.log')
            data = training_input(baseline, config, weight)
            inputfile = root / f'{mode}-input.json'
            inputfile.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            await copy_to(inputfile, remote + '/' + mode + '-input.json')
            output = (remote + '/localize.safetensors' if mode == 'localize'
                      else BOX_LORAS.replace('\\', '/') + '/' + root.name + '-' + mode + '.safetensors')
            response = await service.comfy.client.post(service.comfy.base_url + '/free', json={'unload_models': True, 'free_memory': True})
            response.raise_for_status()
            report['started'].append(mode)
            report['status'] = '重みを更新せず髪の位置を確認中' if mode == 'localize' else mode + 'を学習中'
            save(root, report)
            arguments = ['ssh', 'fox', 'C:/sf/venv/Scripts/python.exe', remote + '/box/esd_train.py',
                         '--sd-scripts', 'C:/sd-scripts', '--input', remote + '/' + mode + '-input.json',
                         '--output', output, '--diagnostics', remote + '/diagnostics-' + mode]
            if mode == 'localize':
                arguments.append('--localize-only')
            await command(arguments, root / f'{mode}-train.log')
            receipt = root / f'{mode}-training.json'
            await copy_from(output.replace('.safetensors', '.json'), receipt)
            report['training'][mode] = json.loads(receipt.read_text(encoding='utf-8'))
            report['training'][mode]['output'] = output
            save(root, report)
        if args.phase == 'localize':
            from PIL import Image
            for step in range(1, len(config['concepts']) + 1):
                remote_stem = remote + f'/diagnostics-localize/step-{step:03}'
                latent = root / f'step-{step:03}.latent'
                mask = root / f'step-{step:03}.png'
                await copy_from(remote_stem + '.latent', latent)
                await copy_from(remote_stem + '.png', mask)
                await copy_from(remote_stem + '.safetensors', root / f'step-{step:03}.safetensors')
                name = root.name + f'-{step:03}.latent'
                await copy_to(latent, str(Path(baseline['lora']).parents[2] / 'input' / name))
                graph = {'1': {'class_type': 'LoadLatent', 'inputs': {'latent': name}},
                         '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'qwen_image_vae.safetensors'}},
                         '24': {'class_type': 'VAEDecode', 'inputs': {'samples': ['1', 0], 'vae': ['3', 0]}},
                         '25': {'class_type': 'SaveImage', 'inputs': {'images': ['24', 0], 'filename_prefix': 'sprite-forge/locality'}}}
                content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
                sample = service._write_generated(f'sample-{step:03}.png', content)
                with Image.open(sample) as original, Image.open(mask) as mask_image:
                    resized = mask_image.resize(original.size, Image.Resampling.BILINEAR)
                    mask_path = root / 'generated' / f'mask-{step:03}.png'
                    resized.save(mask_path)
                    overlay_path = root / 'generated' / f'overlay-{step:03}.png'
                    Image.composite(Image.new('RGB', original.size, 'red'), original.convert('RGB'),
                                    resized.point(lambda x: round(x * .45))).save(overlay_path)
                for kind, path in [('sample', sample), ('mask', mask_path), ('overlay', overlay_path)]:
                    report['pictures'] = [p for p in report['pictures'] if p['name'] != f'{kind}-{step:03}']
                    report['pictures'].append({'name': f'{kind}-{step:03}', 'path': str(path), 'elapsed_s': elapsed})
                save(root, report)
        else:
            for item in report['expected']:
                if any(p['name'] == item['name'] for p in report['pictures']):
                    continue
                kind = item['name'].split('-')[0]
                lora = baseline['lora'] if kind == 'before' else report['training'][kind]['output']
                report['status'] = f'{item["label"]}・{item["seed"]}を生成中'
                save(root, report)
                graph = workflows.anima_txt2img(baseline['prompt'], item['seed'],
                                               loras=[(Path(lora).name, baseline['strength'])],
                                               negative=baseline['negative'], **config['generation'])
                content, elapsed = await service._run_edit(str(uuid.uuid4()), graph)
                path = service._write_generated(item['name'] + '.png', content)
                report['pictures'].append({**item, 'path': str(path), 'elapsed_s': elapsed, 'workflow': graph})
                save(root, report)
        report['status'] = '全画像生成完了・目視評価前'
        save(root, report)
    except Exception as error:
        report.update(status='処理失敗', error=str(error))
        save(root, report)
        raise
    finally:
        await service.comfy.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['localize', 'compare'], required=True)
    parser.add_argument('--localization-review')
    parser.add_argument('--retry-localization', action='store_true')
    asyncio.run(main(parser.parse_args()))
