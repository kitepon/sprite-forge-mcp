"""保存した判定から、LoRA修正と再プレビューまでを実行する。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import uuid

from . import box
from .config import BOX_LORAS, BOX_TRAIN


class PreviewLearning:
    async def relearn_preview(self, name: str, job_id: str, request_id: str, steps: int = 20) -> dict:
        """OKとNGを両方使って再学習する。開始時の判定と教材を固定する。"""
        source = self._preview_review_source(name, job_id)
        existing = self.events.load_job(request_id)
        if existing:
            if existing.get('kind') != 'preview_learning' or existing.get('source_job_id') != job_id or existing.get('name') != name:
                raise ValueError('別の学習に使われた要求IDです。')
            return existing
        # 要求IDは画像やサーバーパスではなく、呼出しごとのUUID。
        uuid.UUID(request_id)
        if steps < 1:
            raise ValueError('学習回数は1以上にしてください。')
        view = await self.preview_reviews(name, job_id)
        if view['relearning_unavailable_reason']:
            raise ValueError(view['relearning_unavailable_reason'])
        selected = [deepcopy(p) for p in view['pictures'] if p['review']['rating']]
        ok = [p for p in selected if p['review']['rating'] == 'ok']
        ng = [p for p in selected if p['review']['rating'] == 'ng']
        if not ok or not ng:
            raise ValueError('再学習にはOKとNGをそれぞれ1枚以上指定してください。未判定の画像は使いません。')
        pairs = [[ok[i % len(ok)]['id'], ng[i % len(ng)]['id']] for i in range(max(len(ok), len(ng)))]
        if steps < len(pairs):
            raise ValueError(f'すべての判定を学習に使うには、学習回数を{len(pairs)}以上にしてください。')
        record = self._load_character(name)
        directory = self.generated_root / f'preference-{request_id}'
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
               'learning_rate': 1e-5, 'beta': 1., 'lora_name': f"{record['key']}_preference_{request_id}.safetensors"}
        self.events.save_job(job)
        with self._job_errors(job):
            for picture in selected:
                await self._interpret_preview_review(name, source, picture, samples)
                self.events.save_job(job)
            questions = [{'image_id': p['id'], 'questions': p['review']['meaning']['questions']}
                         for p in selected if p['review'].get('meaning', {}).get('questions')]
            if questions:
                job.update(status='awaiting_answers', questions=questions)
                self.events.save_job(job)
                return job
            remote_root = PureWindowsPath(BOX_TRAIN).parent.as_posix()
            remote_directory = f'{remote_root}/{directory.name}'
            models = PureWindowsPath(BOX_LORAS).parent.as_posix()
            generation = source['generation']
            config = {'model': f"{models}/diffusion_models/{generation['model']}",
                      'qwen3': f"{models}/text_encoders/{generation['text_encoder']}",
                      'vae': f"{models}/vae/{generation['vae']}",
                      'lora': f"{PureWindowsPath(BOX_LORAS).as_posix()}/{source['loras'][0][0]}",
                      'strength': source['loras'][0][1], 'prompt': source['prompt'], 'negative': source['negative'],
                      'seed': source['seed'], 'size': [generation['width'], generation['height']],
                      'pairs': [[f'{remote_directory}/{image_id}.png' for image_id in pair] for pair in pairs],
                      'fixed_loras': [{'path': f'{PureWindowsPath(BOX_LORAS).as_posix()}/{filename}', 'strength': strength}
                                      for filename, strength in source['loras'][1:]]}
            (directory / 'input.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
            job['dataset'] = str(directory)
            job['training_config'] = config
            job['status'] = 'training'
            self.events.save_job(job)
            code, output = await box.copy_tree_to_box(directory, remote_root)
            if code:
                raise RuntimeError(output)
            log_path = directory / 'training.log'
            with log_path.open('w', encoding='utf-8') as log:
                async for line in box.stream_preference_training(f'{remote_directory}/input.json', Path(job['lora_name']).stem,
                                                                 steps, BOX_LORAS, job['learning_rate'], job['beta']):
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
            preview = {k: deepcopy(v) for k, v in source.items() if k not in ('created_at', 'updated_at')}
            preview.update(job_id=str(uuid.uuid4()), status='queued', pictures=[], total_images=10, learning_job_id=request_id)
            preview['loras'][0] = [job['lora_name'], source['loras'][0][1]]
            job['preview_job_id'] = preview['job_id']
            self.events.save_job(job)
            await self._generate_preview_images(preview)
            job['status'] = 'completed'
            self.events.save_job(job)
            return job
