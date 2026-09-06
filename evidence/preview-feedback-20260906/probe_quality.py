"""隔離台帳で学習前・OKのみ・OKとNGを未学習seedで比較する。"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path, PureWindowsPath
import sys
import time
import uuid

sys.path.insert(0, str(Path.cwd()))
from backend import box
from backend.config import BOX_LORAS
from backend.events import EventStore
from backend.services import Services

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pipeline', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--steps', type=int, default=20)
parser.add_argument('--resume', action='store_true', help='保存済みの比較記録から中断した条件を再開する')
args = parser.parse_args()


async def main():
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    original = json.loads((args.pipeline / 'result.json').read_text())['job']
    source = json.loads((args.pipeline / 'jobs' / f"{original['source_job_id']}.json").read_text())
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    report = {'training_seeds': [1, 2], 'evaluation_seeds': list(range(21, 31)), 'steps': args.steps,
              'source_job_id': source['job_id'], 'conditions': [], 'status': 'running'}
    if args.resume:
        report = json.loads((root / 'report.json').read_text())
        args.steps = report['steps']
        report['status'] = 'running'

    def save():
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))

    try:
        for condition in ('before', 'ok_only', 'preference'):
            row = next((c for c in report['conditions'] if c['condition'] == condition), None)
            if row and row['status'] == 'completed':
                continue
            if row is None:
                row = {'condition': condition, 'status': 'running'}
                report['conditions'].append(row)
            if row.get('preview_job_id'):
                row.setdefault('interrupted_previews', []).append(row['preview_job_id'])
            row['status'] = 'running'; save()
            started = time.monotonic()
            lora = row.get('lora_name', source['loras'][0][0])
            if condition != 'before' and 'training_result' not in row:
                response = await service.comfy.client.post(f'{service.comfy.base_url}/free', json={'unload_models': True, 'free_memory': True})
                response.raise_for_status()
                lora = f'quality_{condition}_{uuid.uuid4().hex[:8]}.safetensors'
                output = f'{PureWindowsPath(BOX_LORAS).as_posix()}/{lora}'
                remote_config = original['training_config']
                config_path = root / 'input.json'
                config_path.write_text(json.dumps(remote_config))
                code, result = await box.copy_to_box(config_path, 'C:/sf/quality-input.json')
                if code: raise RuntimeError(result)
                trainer = 'train_ok_control.py' if condition == 'ok_only' else 'preference_train.py'
                command = ['ssh', 'fox', 'C:/sf/venv/Scripts/python.exe', f'C:/sf/{trainer}',
                           '--sd-scripts', 'C:/sd-scripts', '--input', 'C:/sf/quality-input.json',
                           '--output', output, '--steps', str(args.steps), '--learning-rate', '1e-5', '--beta', '1']
                with (root / f'{condition}.log').open('wb') as log:
                    process = await asyncio.create_subprocess_exec(*command, stdout=log, stderr=asyncio.subprocess.STDOUT)
                    if await process.wait(): raise RuntimeError(f'{condition}の学習失敗。ログを確認してください。')
                metrics_path = root / f'{condition}.json'
                code, result = await box.copy_from_box(output.replace('.safetensors', '.json'), metrics_path)
                if code: raise RuntimeError(result)
                row['training_result'] = json.loads(metrics_path.read_text())
            preview = {k: deepcopy(v) for k, v in source.items() if k not in ('created_at', 'updated_at')}
            preview.update(job_id=str(uuid.uuid4()), name=f'品質比較・{condition}', status='queued', pictures=[], total_images=10, seed=21)
            preview['loras'][0][0] = lora
            row.update(preview_job_id=preview['job_id'], lora_name=lora); save()
            await service._generate_preview_images(preview)
            row.update(status='completed', pictures=preview['pictures'], elapsed_seconds=time.monotonic() - started)
            save()
            print(json.dumps({'condition': condition, 'status': row['status'], 'elapsed_seconds': row['elapsed_seconds']}), flush=True)
        report['status'] = 'awaiting_visual_review'; save()
    except Exception as error:
        report.update(status='failed', error=str(error)); save()
        raise
    finally:
        await service.comfy.close()


asyncio.run(main())
