"""生成画像の判定。生成中のジョブ更新と別に保存し、画像への対応を保つ。"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class PreviewReview(BaseModel):
    rating: Literal['ok', 'ng', '']
    revision: int
    comment: str | None = None
    focus: list[str] | None = None


class PreviewReviews:
    def _preview_review_source(self, name, job_id):
        record = self._load_character(name)
        job = self.events.load_job(job_id)
        if not job or job.get('kind') != 'preview' or job.get('name') != record['name']:
            raise ValueError('このキャラクターのプレビューを指定してください。')
        if job.get('character_created', record['created']) != record['created'] or (
            datetime.fromisoformat(job['created_at']) < datetime.fromisoformat(record['created'])
        ):
            raise ValueError('作り直す前のキャラクターのプレビューです。')
        return job

    def _preview_reviews_path(self, name, job_id):
        return self._character_dir(name) / 'preview-reviews' / f'{job_id}.json'

    def _preview_reviews(self, name, job_id):
        path = self._preview_reviews_path(name, job_id)
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    async def preview_reviews(self, name: str, job_id: str) -> dict:
        """生成画像と保存済みのOK／NGを取得する。未判定をOKに補完しない。"""
        job = self._preview_review_source(name, job_id)
        reviews = self._preview_reviews(name, job_id)
        pictures = []
        for picture in job.get('pictures', []):
            image_id = picture.get('id') or Path(picture['path']).stem
            review = reviews.get(image_id, {'rating': '', 'comment': '', 'focus': [], 'revision': 0, 'history': []})
            pictures.append({**picture, 'id': image_id, 'review': review})
        reason = '' if job.get('generation') and job.get('character_created') else '以前の生成条件の記録が不足しています。再学習するには新しくプレビューを生成してください。'
        return {'job_id': job_id, 'name': name, 'pictures': pictures, 'generation': job.get('generation'),
                'relearning_unavailable_reason': reason}

    async def save_preview_review(self, name: str, job_id: str, image_id: str, review: PreviewReview) -> dict:
        """一枚の判定を保存する。古い画面からの更新は理由を示して返す。"""
        view = await self.preview_reviews(name, job_id)
        picture = next((p for p in view['pictures'] if p['id'] == image_id), None)
        if picture is None:
            raise ValueError('このプレビューに含まれる画像を指定してください。')
        previous = picture['review']
        if review.revision != previous['revision']:
            raise ValueError('別の画面で判定が更新されました。最新の判定を読み直してください。')
        history = previous['history'] + ([{k: deepcopy(v) for k, v in previous.items() if k != 'history'}] if previous['revision'] else [])
        saved = {'rating': review.rating, 'comment': previous['comment'] if review.comment is None else review.comment,
                 'focus': previous['focus'] if review.focus is None else review.focus,
                 'revision': previous['revision'] + 1, 'history': history}
        reviews = self._preview_reviews(name, job_id)
        reviews[image_id] = saved
        path = self._preview_reviews_path(name, job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reviews, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.events.append(job_id, 'preview_review_saved', {'image_id': image_id, 'revision': saved['revision'], 'rating': saved['rating']})
        return saved
