"""隔離した台帳で、実生成→判定→正規学習→再プレビューを通す。"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path.cwd()))
from backend.events import EventStore
from backend.services import Services
from backend.preview_reviews import PreviewReview

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()


async def main():
    from PIL import Image, ImageChops
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    source = json.loads((args.source_root / '.cache/jobs/f0e53145-c159-4c0e-81ce-d58723746656.json').read_text())
    service = Services(events=EventStore(root / 'events.ndjson', root / 'jobs'), generated_root=root / 'generated',
                       characters_root=root / 'characters', styles_root=root / 'styles', uploads_root=root / 'uploads')
    try:
        record = await service.create_character('LoRA修正・実機検証', 'she/her', lora_name=source['loras'][0][0])
        await service.add_samples(record['name'], str(args.source_root / '.cache/characters/ndac1de01/samples/000.png'))
        job = {k: deepcopy(v) for k, v in source.items() if k not in ('created_at', 'updated_at')}
        job.update(job_id=str(uuid.uuid4()), name=record['name'], character_created=record['created'], pictures=[], total_images=2,
                   status='queued', generation={'model': 'anima-base-v1.0.safetensors', 'text_encoder': 'qwen_3_06b_base.safetensors',
                   'vae': 'qwen_image_vae.safetensors', 'width': 832, 'height': 1216, 'turbo': False,
                   'steps': 28, 'cfg': 4., 'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.})
        await service._generate_preview_images(job)
        matched = []
        for index, rating in enumerate(('ok', 'ng')):
            picture = job['pictures'][index]
            original = args.source_root / '.cache/generated' / Path(source['pictures'][index]['path']).name
            with Image.open(original) as a, Image.open(picture['path']) as b:
                matched.append(a.size == b.size and ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox() is None)
            await service.save_preview_review(record['name'], job['job_id'], picture['id'], PreviewReview(rating=rating, revision=0))
        print(json.dumps({'source_job_id': job['job_id'], 'matches_user_rated_pixels': matched}), flush=True)
        # 不一致時も経路試験用の判定として扱い、画質の証拠にはしない。
        result = await service.relearn_preview(record['name'], job['job_id'], str(uuid.uuid4()), steps=1)
        (root / 'result.json').write_text(json.dumps({'matches_user_rated_pixels': matched, 'job': result}, ensure_ascii=False, indent=2))
        print(json.dumps({'status': result['status'], 'preview_job_id': result.get('preview_job_id'),
                          'training_result': result.get('training_result')}), flush=True)
    finally:
        await service.comfy.close()


asyncio.run(main())
