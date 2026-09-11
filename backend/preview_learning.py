"""保存した判定から、LoRA修正と再プレビューまでを実行する。"""
from copy import deepcopy
from io import BytesIO
import asyncio
import hashlib
import json
from pathlib import Path, PureWindowsPath
import uuid

from PIL import Image, ImageChops

from . import bible, box, workflows
from .config import BOX_LORAS, BOX_TRAIN
from .intent import PREVIEW_TAGS, identity_from_preview_prompt, organize_tags, preview_content, unique_tags
from .preview_reviews import description_for_focus, review_has_input, review_needs_interpretation, review_of, require_interpreted_generation

IN_FLIGHT = ('interpreting', 'training', 'previewing')
SPATIAL_FOCUS = {'hair': 'hair', 'face': 'face', 'outfit': 'clothes', 'body': 'body'}
FIX_REGION_MARKERS = (
    ('hair', ('髪', 'ヘア')),
    ('face', ('顔', '目', '眉')),
    ('outfit', ('衣装', '服', '服装')),
    ('body', ('体形', '体型', '体')),
)


def spatial_keys_from_focus_and_text(focus, text: str = '') -> tuple[str, ...]:
    """focusの空間キーを優先し、それが無いときだけ一般語を見る。"""
    seen = set()
    ordered = []
    if isinstance(focus, list):
        for key in focus:
            if key in SPATIAL_FOCUS and key not in seen:
                seen.add(key)
                ordered.append(key)
    if ordered:
        return tuple(ordered)
    joined = text or ''
    return tuple(region for region, markers in FIX_REGION_MARKERS if any(marker in joined for marker in markers))


def learning_mode(ok: list, ng: list) -> str:
    if ok and ng:
        return 'preference'
    if ok:
        return 'ok'
    if ng:
        return 'ng'
    return 'none'


def preference_pairs(ok: list[dict], ng: list[dict]) -> list[list[str]]:
    """OKとNGがあるときだけ対にする。片方だけの学習は対を使わない。"""
    if not ok or not ng:
        return []
    return [[ok[i % len(ok)]['id'], ng[i % len(ng)]['id']] for i in range(max(len(ok), len(ng)))]


def pair_spatial_regions(review: dict) -> tuple[str, ...]:
    """NGの空間部位。focusがあればそれを使い、なければ解釈の一般語だけを見る。"""
    if (review.get('rating') or '') != 'ng':
        return ()
    from_focus = spatial_keys_from_focus_and_text(review.get('focus'))
    if from_focus:
        return from_focus
    joined = ' '.join((review.get('meaning') or {}).get('fix') or [])
    return spatial_keys_from_focus_and_text([], joined)


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
    async def grow_lora_from_preview(self, name: str, job_id: str, request_id: str, steps: int = 0) -> dict:
        """OKにしたプレビューを教材に足し、サンプルと同じLoRA学習で更新する。"""
        source = self._preview_review_source(name, job_id)
        existing = self.events.load_job(request_id)
        if existing:
            if existing.get('kind') != 'lora_grow' or existing.get('source_job_id') != job_id or existing.get('name') != name:
                raise ValueError('別の学習に使われた要求IDです。')
            if existing['status'] in ('running', 'training', 'previewing'):
                self._ensure_grow(request_id)
            return existing
        uuid.UUID(request_id)
        view = await self.preview_reviews(name, job_id)
        if view['relearning_unavailable_reason']:
            raise ValueError(view['relearning_unavailable_reason'])
        ok = await self._ok_pictures_from_pair(name, job_id)
        if not ok:
            raise ValueError('OKの画像を選んでから教材に足してください。')
        record = self._load_character(name)
        if not record.get('lora_name'):
            raise ValueError('先にサンプルからLoRAを作ってください。')
        steps = steps or record.get('steps') or 1200
        if steps < 1:
            raise ValueError('学習ステップは1以上を指定してください。')
        sibling = self.events.load_job(source['paired_job_id']) if source.get('paired_job_id') else None
        ordered = source if source.get('preview_role') == 'with_order' or source.get('intent_job_id') else (
            sibling if sibling and (sibling.get('preview_role') == 'with_order' or sibling.get('intent_job_id')) else source)
        job = {
            'job_id': request_id, 'kind': 'lora_grow', 'status': 'running', 'name': name,
            'source_job_id': job_id, 'character_created': record['created'],
            'ok_ids': [picture['id'] for picture in ok],
            'pictures': [{'id': picture['id'], 'path': picture['path'], 'sha256': picture['sha256']} for picture in ok],
            'source': {
                'prompt': ordered['prompt'], 'tags': ordered.get('tags') or PREVIEW_TAGS,
                'intent_job_id': ordered.get('intent_job_id') or '',
                'intent_positive': ordered.get('intent_positive') or '',
                'seed': ordered['seed'], 'style': ordered.get('style') or '',
                'total_images': ordered.get('total_images') or 10,
            },
            'steps': steps, 'progress': {'step': 0, 'total': steps},
        }
        self.events.save_job(job)
        self._ensure_grow(request_id)
        return self.events.load_job(request_id)

    def _ensure_grow(self, job_id: str) -> asyncio.Task:
        task = self._grow_tasks.get(job_id)
        if task is None or task.done():
            task = asyncio.create_task(self._run_grow(job_id))
            self._grow_tasks[job_id] = task
        return task

    async def _run_grow(self, job_id: str) -> None:
        job = self.events.load_job(job_id)
        with self._job_errors(job):
            record = self._load_character(job['name'])
            if record['created'] != job['character_created']:
                raise ValueError('学習中に対象のキャラクターが作り直されたため、結果を採用していません。')
            if not job.get('additions'):
                job['additions'] = self._store_preview_additions(record, job)
                self._save_character(record)
                self.events.save_job(job)
            if not job.get('training_job_id'):
                prepared = await self.prepare_training(job['name'], 'character', job['steps'])
                job['training_job_id'] = prepared['job_id']
                job['status'] = 'training'
                self.events.save_job(job)
                await self.train_character_lora(job['name'], prepared['steps'], prepared['job_id'])
            if not job.get('preview_job_id'):
                job['status'] = 'previewing'
                self.events.save_job(job)
                source = job['source']
                pair = await self.preview_character_pair(
                    job['name'], tags=source.get('tags') or PREVIEW_TAGS, seed=source['seed'],
                    count=source.get('total_images') or 10, style=source.get('style') or '',
                    intent_job_id=source.get('intent_job_id') or '')
                plain, ordered = pair['without_order'], pair['with_order']
                for preview in (plain, ordered):
                    if not preview:
                        continue
                    preview['learning_job_id'] = job_id
                    self.events.save_job(preview)
                job['plain_preview_job_id'] = plain['job_id']
                job['preview_job_id'] = pair['job_id']
            job['status'] = 'completed'
            self.events.save_job(job)

    async def _ok_pictures_from_pair(self, name: str, job_id: str) -> list[dict]:
        view = await self.preview_reviews(name, job_id)
        pictures = [picture for picture in view['pictures'] if picture['review']['rating'] == 'ok']
        job = self.events.load_job(job_id) or {}
        sibling_id = job.get('paired_job_id')
        if sibling_id:
            other = await self.preview_reviews(name, sibling_id)
            pictures.extend(picture for picture in other['pictures'] if picture['review']['rating'] == 'ok')
        return pictures

    def _store_preview_additions(self, record: dict, job: dict) -> list[dict]:
        caption = identity_from_preview_prompt(job['source']['prompt'], record['trigger'])
        if not caption:
            caption = (job['source'].get('intent_positive') or '').strip()
        folder = self._character_dir(record['name']) / 'additions'
        folder.mkdir(parents=True, exist_ok=True)
        existing = {(item.get('source_image_id'), item.get('sha256')) for item in record.get('training_additions') or []}
        added = []
        for picture in job['pictures']:
            content = Path(picture['path']).read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != picture['sha256']:
                raise ValueError('判定した画像の内容が変わっています。新しくプレビューを生成してください。')
            key = (picture['id'], digest)
            if key in existing:
                continue
            path = folder / f"{picture['id']}.png"
            path.write_bytes(content)
            item = {'path': str(path), 'caption_en': caption, 'source_job_id': job['source_job_id'],
                    'source_image_id': picture['id'], 'sha256': digest}
            record.setdefault('training_additions', []).append(item)
            existing.add(key)
            added.append(item)
        if not added and not record.get('training_additions'):
            raise ValueError('足す教材がありません。')
        return added

    async def relearn_preview(self, name: str, job_id: str, request_id: str, steps: int = 20) -> dict:
        """判定から再学習する。OKだけ・NGだけ・判定なしでも開始できる。開始時の判定と教材を固定する。"""
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
        record = self._load_character(name)
        mode = learning_mode(ok, ng)
        pairs = preference_pairs(ok, ng)
        images = [p['id'] for p in (ok if mode == 'ok' else ng if mode == 'ng' else [])]
        needed = len(pairs) if mode == 'preference' else len(images)
        if needed and steps < needed:
            raise ValueError(f'すべての判定を学習に使うには、学習回数を{needed}以上にしてください。')
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
               'reviews': selected, 'samples': samples, 'mode': mode, 'pairs': pairs, 'images': images, 'steps': steps,
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
            if job.get('kind') == 'lora_grow' and job.get('status') in ('running', 'training', 'previewing'):
                self._ensure_grow(job['job_id'])

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
            await self._compose_generation_prompt(job)
        if job['status'] in ('interpreting', 'training'):
            await self._train_preview_learning(job)
        if job['status'] == 'previewing':
            await self._preview_after_learning(job)

    async def _interpret_preview_learning(self, job: dict) -> bool:
        """質問があれば True。学習は始めない。"""
        selected = job['reviews']
        pending = [picture for picture in selected if review_needs_interpretation(picture['review'])]
        targets = [p for p in selected if review_has_input(p['review'])]
        job['progress'] = {'step': sum(1 for p in targets if 'meaning' in p['review']), 'total': len(targets)}
        self.events.save_job(job)
        for i, picture in enumerate(pending):
            await self._interpret_preview_review(
                job['name'], job['source'], picture, job['samples'],
                keep_model_loaded=True,
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

    async def _compose_generation_prompt(self, job: dict) -> None:
        """プレビュー全体の生成文を、判定メモから生成AIが一本にまとめる。"""
        if 'generation_prompt' in job:
            return
        mode = job.get('mode') or learning_mode(
            [p for p in job['reviews'] if p['review']['rating'] == 'ok'],
            [p for p in job['reviews'] if p['review']['rating'] == 'ng'])
        ratings = {'ok': ('ok',), 'ng': ('ng',), 'preference': ('ok', 'ng'), 'none': ()}[mode]
        notes = []
        focuses = []
        for picture in job['reviews']:
            review = picture['review']
            if ratings and (review.get('rating') or '') not in ratings:
                continue
            meaning = review.get('meaning') or {}
            notes.append({
                'comment': review.get('comment') or '',
                'focus': review.get('focus') or [],
                'rating': review.get('rating') or '',
                'description_en': meaning.get('description_en') or '',
                'fix': meaning.get('fix') or [],
                'preserve': meaning.get('preserve') or [],
            })
            focuses.extend(review.get('focus') or [])
        if not notes or not any(note['comment'] or note['description_en'] or note['fix'] for note in notes):
            job['generation_prompt'] = ''
            self.events.save_job(job)
            return
        focus = list(dict.fromkeys(focuses))
        packet = {'stage': 'preview_batch_prompt', 'review_input': {
            'stage': 'preview_batch_prompt', 'focus': focus, 'notes': notes,
        }}
        proposal = await self.intent_interpreter(packet, [], keep_model_loaded=False, reclaim_memory=False)
        text = str(proposal.get('description_en') or '').strip()
        if focus:
            text = description_for_focus('', text, focus)
        if not text:
            raise RuntimeError('生成文を作れませんでした。')
        job['generation_prompt'] = text
        self.events.save_job(job)

    async def _train_preview_learning(self, job: dict) -> None:
        require_interpreted_generation(job['reviews'])
        mode = job.get('mode') or learning_mode(
            [p for p in job['reviews'] if p['review']['rating'] == 'ok'],
            [p for p in job['reviews'] if p['review']['rating'] == 'ng'])
        if mode == 'none':
            job['lora_name'] = job['source']['loras'][0][0]
            job['status'] = 'previewing'
            self.events.save_job(job)
            return
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
            regions = pair_spatial_regions(by_id.get(ng_id) or {})
            pair_regions.append(list(regions))
            if not regions:
                pair_masks.append(None)
                continue
            ok_name, ng_name = f'{ok_id}.mask.png', f'{ng_id}.mask.png'
            await self._pair_region_mask(ok_id, (directory / f'{ok_id}.png').read_bytes(), regions, directory, ok_name, cache, job['job_id'])
            await self._pair_region_mask(ng_id, (directory / f'{ng_id}.png').read_bytes(), regions, directory, ng_name, cache, job['job_id'])
            pair_masks.append([f'{remote_directory}/{ok_name}', f'{remote_directory}/{ng_name}'])
        ratings = {'ok': ('ok',), 'ng': ('ng',), 'preference': ('ok', 'ng')}[mode]
        extra = job.get('generation_prompt')
        if extra is None:
            extra = desired_generation_prompt(source['prompt'], job['reviews'], ratings)
        config = {'model': f"{models}/diffusion_models/{generation['model']}",
                  'qwen3': f"{models}/text_encoders/{generation['text_encoder']}",
                  'vae': f"{models}/vae/{generation['vae']}",
                  'lora': f"{PureWindowsPath(BOX_LORAS).as_posix()}/{source['loras'][0][0]}",
                  'strength': source['loras'][0][1],
                  'prompt': self._training_appearance_prompt(job['name'], extra or ''),
                  'negative': source['negative'],
                  'seed': source['seed'], 'size': [generation['width'], generation['height']],
                  'mode': mode,
                  'pairs': [[f'{remote_directory}/{image_id}.png' for image_id in pair] for pair in job['pairs']],
                  'images': [f'{remote_directory}/{image_id}.png' for image_id in job.get('images') or []],
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

    def _training_appearance_prompt(self, name: str, extra: str = "") -> str:
        """学習画面で確認したキャプションを使う。差分があれば足す。"""
        record = self._load_character(name)
        chosen = ""
        fallback = []
        for sample in record.get("samples") or []:
            english = (sample.get("training_caption") or {}).get("caption_en") or ""
            if not english:
                continue
            comment = sample.get("caption") or ""
            if "服装" in comment or "等身" in comment:
                chosen = english
            fallback.append(english)
        appearance = chosen or (max(fallback, key=len) if fallback else "")
        return unique_tags(record["trigger"], appearance, extra)

    def _prompt_after_learning(self, job: dict) -> str:
        """学習文は指定部位だけ。再プレビューは普通の全身プレビューにその差分を足す。"""
        extras = job.get('generation_prompt') or ''
        record = self._load_character(job['name'])
        _, style_word, _ = self._generation_loras(record, job['source'].get('style') or '', {})
        return unique_tags(record['trigger'], style_word, PREVIEW_TAGS, extras, '1girl, solo', bible.COMMON)

    async def _preview_after_learning(self, job: dict) -> None:
        source = job['source']
        preview = self.events.load_job(job['preview_job_id']) if job.get('preview_job_id') else None
        if preview is None:
            preview = {k: deepcopy(v) for k, v in source.items() if k not in ('created_at', 'updated_at')}
            preview.update(job_id=str(uuid.uuid4()), status='queued', pictures=[], total_images=10, learning_job_id=job['job_id'])
            preview['loras'][0] = [job['lora_name'], source['loras'][0][1]]
            preview['generation_prompt'] = job.get('generation_prompt') or ''
            preview['prompt'] = self._prompt_after_learning(job)
            job['preview_job_id'] = preview['job_id']
            job['status'] = 'previewing'
            self.events.save_job(job)
        if preview.get('status') != 'completed':
            await self._generate_preview_images(preview)
        job['status'] = 'completed'
        self.events.save_job(job)


def desired_generation_prompt(source_prompt: str, reviews: list[dict], ratings: tuple[str, ...] = ('ok', 'ng')) -> str:
    """プレビュー全体で一つの生成文。画像ごとの description_en を並べない。"""
    extras = []
    focused = False
    seen = set()
    for entry in reviews:
        review = review_of(entry)
        rating = review.get('rating') or ''
        if rating and rating not in ratings:
            continue
        text = str((review.get('meaning') or {}).get('description_en') or '').strip()
        if review.get('focus'):
            focused = True
            text = description_for_focus(source_prompt, text, review['focus'])
        if not text or text in seen:
            continue
        seen.add(text)
        extras.append(text)
    extras = [text for text in extras if text]
    if not extras:
        return '' if focused else source_prompt
    if focused:
        return organize_tags(*extras)
    if len(extras) == 1:
        return extras[0]
    kept = [text for text in extras if not any(text != other and text in other for other in extras)]
    if not kept:
        return extras[0]
    if len(kept) == 1:
        return kept[0]
    return organize_tags(*kept)
