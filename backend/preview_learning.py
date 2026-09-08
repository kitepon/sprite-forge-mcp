"""保存した判定から、LoRA修正と再プレビューまでを実行する。"""
from copy import deepcopy
from io import BytesIO
import asyncio
import hashlib
import json
from pathlib import Path, PureWindowsPath
import uuid

from PIL import Image, ImageChops

from . import box, workflows
from .config import BOX_LORAS, BOX_TRAIN

IN_FLIGHT = ('interpreting', 'training', 'previewing')
SPATIAL_FOCUS = {'hair': 'hair', 'face': 'face', 'outfit': 'clothes', 'body': 'body'}
FIX_REGION_MARKERS = (
    ('hair', ('髪', 'ヘア')),
    ('face', ('顔', '目', '眉')),
    ('outfit', ('衣装', '服', '服装')),
    ('body', ('体形', '体型', '体')),
)


def pair_spatial_regions(review: dict) -> tuple[str, ...]:
    """NGの空間部位。focusがあればそれを使い、なければ解釈の一般語だけを見る。"""
    if (review.get('rating') or '') != 'ng':
        return ()
    seen = set()
    ordered = []
    for key in review.get('focus') or []:
        if key in SPATIAL_FOCUS and key not in seen:
            seen.add(key)
            ordered.append(key)
    if ordered:
        return tuple(ordered)
    joined = ' '.join((review.get('meaning') or {}).get('fix') or [])
    return tuple(region for region, markers in FIX_REGION_MARKERS if any(marker in joined for marker in markers))


def mask_is_empty(png: bytes) -> bool:
    return Image.open(BytesIO(png)).convert('L').getextrema()[1] == 0


def union_masks(parts: list[bytes]) -> bytes:
    if not parts:
        raise ValueError('マスクがありません')
    combined = Image.open(BytesIO(parts[0])).convert('L')
    for part in parts[1:]:
        combined = ImageChops.lighter(combined, Image.open(BytesIO(part)).convert('L'))
    if combined.getextrema()[1] == 0:
        raise ValueError('マスクが空です')
    buffer = BytesIO()
    combined.convert('RGBA').save(buffer, format='PNG')
    return buffer.getvalue()


class PreviewLearning:
    async def relearn_preview(self, name: str, job_id: str, request_id: str, steps: int = 20) -> dict:
        """OKとNGを両方使って再学習する。開始時の判定と教材を固定する。"""
        source = self._preview_review_source(name, job_id)
        existing = self.events.load_job(request_id)
        if existing:
            if existing.get('kind') != 'preview_learning' or existing.get('source_job_id') != job_id or existing.get('name') != name:
                raise ValueError('別の学習に使われた要求IDです。')
            if existing['status'] != 'awaiting_answers':
                if existing['status'] in IN_FLIGHT:
                    self._ensure_preview_learning(request_id)
                return existing
            steps = existing['steps']
        # 要求IDは画像やサーバーパスではなく、呼出しごとのUUID。
        uuid.UUID(request_id)
        if steps < 1:
            raise ValueError('学習回数は1以上にしてください。')
        view = await self.preview_reviews(name, job_id)
        if view['relearning_unavailable_reason']:
            raise ValueError(view['relearning_unavailable_reason'])
        selected = [deepcopy(p) for p in view['pictures'] if p['review']['rating']]
        if existing and [(p['id'], p['review']['revision']) for p in selected] == [(p['id'], p['review']['revision']) for p in existing['reviews']]:
            return existing
        ok = [p for p in selected if p['review']['rating'] == 'ok']
        ng = [p for p in selected if p['review']['rating'] == 'ng']
        if not ok or not ng:
            raise ValueError('再学習にはOKとNGをそれぞれ1枚以上指定してください。未判定の画像は使いません。')
        pairs = [[ok[i % len(ok)]['id'], ng[i % len(ng)]['id']] for i in range(max(len(ok), len(ng)))]
        if steps < len(pairs):
            raise ValueError(f'すべての判定を学習に使うには、学習回数を{len(pairs)}以上にしてください。')
        record = self._load_character(name)
        history = existing.get('preparation_history', []) + [{k: deepcopy(existing[k]) for k in ('reviews', 'samples', 'questions')}] if existing else []
        directory = self.generated_root / f'preference-{request_id}-{len(history)}'
        directory.mkdir(parents=True)
        samples = deepcopy(record['samples'])
        for sample in samples:
            target = directory / f"sample-{sample['index']}.png"
            target.write_bytes(Path(sample['path']).read_bytes())
            sample['path'] = str(target)
        for picture in selected:
            content = Path(picture['path']).read_bytes()
            if hashlib.sha256(content).hexdigest() != picture['sha256']:
                raise ValueError('判定した画像の内容が変わっています。新しくプレビューを生成してください。')
            target = directory / f"{picture['id']}.png"
            target.write_bytes(content)
            picture['path'] = str(target)
        job = {'job_id': request_id, 'kind': 'preview_learning', 'status': 'interpreting', 'name': name,
               'source_job_id': job_id, 'character_created': record['created'], 'source': deepcopy(source),
               'reviews': selected, 'samples': samples, 'pairs': pairs, 'steps': steps,
               'learning_rate': 1e-5, 'beta': 1., 'preparation_history': history,
               'dataset': str(directory),
               'lora_name': f"{record['key']}_preference_{request_id}.safetensors"}
        self.events.save_job(job)
        self._ensure_preview_learning(request_id)
        return self.events.load_job(request_id)

    def _ensure_preview_learning(self, job_id: str) -> asyncio.Task:
        task = self._preview_learning_tasks.get(job_id)
        if task is not None and not task.done():
            return task
        task = asyncio.create_task(self._run_preview_learning(job_id))
        self._preview_learning_tasks[job_id] = task
        return task

    async def resume_preview_learning(self) -> None:
        """起動時に、解釈・学習・再プレビューの途中で止まっているジョブを再開する。"""
        for job in self.events.list_jobs():
            if job.get('kind') == 'preview_learning' and job.get('status') in IN_FLIGHT:
                self._ensure_preview_learning(job['job_id'])

    async def _run_preview_learning(self, job_id: str) -> None:
        job = self.events.load_job(job_id)
        with self._job_errors(job):
            await self._continue_preview_learning(job)

    async def _continue_preview_learning(self, job: dict) -> None:
        if job['status'] not in IN_FLIGHT:
            return
        if job['status'] == 'interpreting':
            if await self._interpret_preview_learning(job):
                return
        if job['status'] in ('interpreting', 'training'):
            await self._train_preview_learning(job)
        if job['status'] == 'previewing':
            await self._preview_after_learning(job)

    async def _interpret_preview_learning(self, job: dict) -> bool:
        """質問があれば True。学習は始めない。"""
        selected = job['reviews']
        pending = [
            picture for picture in selected
            if 'meaning' not in picture['review'] and (picture['review']['comment'].strip() or picture['review']['focus'])
        ]
        targets = [p for p in selected if picture_needs_meaning(p)]
        job['progress'] = {'step': sum(1 for p in targets if 'meaning' in p['review']), 'total': len(targets)}
        self.events.save_job(job)
        for i, picture in enumerate(pending):
            await self._interpret_preview_review(
                job['name'], job['source'], picture, job['samples'],
                keep_model_loaded=i < len(pending) - 1,
                reclaim_memory=i == 0,
            )
            job['progress'] = {'step': sum(1 for p in targets if 'meaning' in p['review']), 'total': len(targets)}
            self.events.save_job(job)
        questions = [{'image_id': p['id'], 'questions': p['review']['meaning']['questions']}
                     for p in selected if p['review'].get('meaning', {}).get('questions')]
        if questions:
            job.update(status='awaiting_answers', questions=questions)
            self.events.save_job(job)
            return True
        return False

    async def _train_preview_learning(self, job: dict) -> None:
        job['status'] = 'training'
        self.events.save_job(job)
        directory = Path(job['dataset'])
        directory.mkdir(parents=True, exist_ok=True)
        source = job['source']
        remote_root = PureWindowsPath(BOX_TRAIN).parent.as_posix()
        remote_directory = f'{remote_root}/{directory.name}'
        models = PureWindowsPath(BOX_LORAS).parent.as_posix()
        generation = source['generation']
        by_id = {picture['id']: picture['review'] for picture in job['reviews']}
        pair_regions = []
        pair_masks: list[list[str] | None] = []
        cache: dict[tuple[str, str], bytes] = {}
        for ok_id, ng_id in job['pairs']:
            regions = pair_spatial_regions(by_id[ng_id])
            pair_regions.append(list(regions))
            if not regions:
                pair_masks.append(None)
                continue
            ok_name, ng_name = f'{ok_id}.mask.png', f'{ng_id}.mask.png'
            await self._pair_region_mask(ok_id, (directory / f'{ok_id}.png').read_bytes(), regions, directory, ok_name, cache, job['job_id'])
            await self._pair_region_mask(ng_id, (directory / f'{ng_id}.png').read_bytes(), regions, directory, ng_name, cache, job['job_id'])
            pair_masks.append([f'{remote_directory}/{ok_name}', f'{remote_directory}/{ng_name}'])
        config = {'model': f"{models}/diffusion_models/{generation['model']}",
                  'qwen3': f"{models}/text_encoders/{generation['text_encoder']}",
                  'vae': f"{models}/vae/{generation['vae']}",
                  'lora': f"{PureWindowsPath(BOX_LORAS).as_posix()}/{source['loras'][0][0]}",
                  'strength': source['loras'][0][1], 'prompt': source['prompt'], 'negative': source['negative'],
                  'seed': source['seed'], 'size': [generation['width'], generation['height']],
                  'pairs': [[f'{remote_directory}/{image_id}.png' for image_id in pair] for pair in job['pairs']],
                  'masks': pair_masks, 'pair_regions': pair_regions,
                  'fixed_loras': [{'path': f'{PureWindowsPath(BOX_LORAS).as_posix()}/{filename}', 'strength': strength}
                                  for filename, strength in source['loras'][1:]]}
        (directory / 'input.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        job['training_config'] = config
        self.events.save_job(job)
        code, output = await box.copy_tree_to_box(directory, remote_root)
        if code:
            raise RuntimeError(output)
        log_path = directory / 'training.log'
        with log_path.open('w', encoding='utf-8') as log:
            async for line in box.stream_preference_training(f'{remote_directory}/input.json', Path(job['lora_name']).stem,
                                                             job['steps'], BOX_LORAS, job['learning_rate'], job['beta']):
                log.write(line + '\n'); log.flush()
                if line.startswith('{'):
                    result = json.loads(line)
                    if 'step' in result:
                        job['progress'] = result
                        self.events.save_job(job)
        metrics = directory / 'result.json'
        code, output = await box.copy_from_box(f"{PureWindowsPath(BOX_LORAS).as_posix()}/{Path(job['lora_name']).stem}.json", metrics)
        if code:
            raise RuntimeError(output)
        job['training_result'] = json.loads(metrics.read_text(encoding='utf-8'))
        job['status'] = 'previewing'
        self.events.save_job(job)

    async def _region_mask_png(self, content: bytes, prompt: str, name: str, job_id: str) -> bytes:
        uploaded = await self.comfy.upload(content, name)
        prompt_id = await self.comfy.submit(workflows.sam3_mask(uploaded, prompt), job_id)
        return self._as_rgba_png(await self._view(self._first_image(await self._history_until_done(prompt_id))))

    async def _pair_region_mask(self, image_id, content, regions, dataset, filename, cache, job_id):
        parts = []
        for region in regions:
            cache_key = (image_id, region)
            if cache_key not in cache:
                prompt = SPATIAL_FOCUS[region]
                png = await self._region_mask_png(content, prompt, f'{image_id}-{region}.png', job_id)
                if mask_is_empty(png):
                    raise RuntimeError(f'マスクが空です: {prompt}')
                cache[cache_key] = png
            parts.append(cache[cache_key])
        path = dataset / filename
        path.write_bytes(union_masks(parts))
        return path

    async def _preview_after_learning(self, job: dict) -> None:
        source = job['source']
        preview = self.events.load_job(job['preview_job_id']) if job.get('preview_job_id') else None
        if preview is None:
            preview = {k: deepcopy(v) for k, v in source.items() if k not in ('created_at', 'updated_at')}
            preview.update(job_id=str(uuid.uuid4()), status='queued', pictures=[], total_images=10, learning_job_id=job['job_id'])
            preview['loras'][0] = [job['lora_name'], source['loras'][0][1]]
            job['preview_job_id'] = preview['job_id']
            job['status'] = 'previewing'
            self.events.save_job(job)
        if preview.get('status') != 'completed':
            await self._generate_preview_images(preview)
        job['status'] = 'completed'
        self.events.save_job(job)


def picture_needs_meaning(picture: dict) -> bool:
    review = picture['review']
    return bool(review['comment'].strip() or review['focus'])
