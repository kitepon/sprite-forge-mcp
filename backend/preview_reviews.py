"""生成画像の判定。生成中のジョブ更新と別に保存し、画像への対応を保つ。"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from .preview_intent import ReviewCorrection, ReviewMeaning

FOCUS_LABELS = {'hair': '髪', 'face': '顔', 'outfit': '衣装', 'body': '体形', 'style': '画風'}
HAIR_OFF_MARKERS = (
    'wearing', 'worn', 'cropped', 'skirt', 'dress', 'boot', 'shoe', 'collar',
    'standing', 'sitting', 'full body', 'looking at viewer', 'background',
    'woman', 'girl', '1girl', 'man', 'person', 'proportion', 'head-tall',
    'arms', 'outfit', 'clothes', 'jacket', 'top with', 'against a',
    'without twin', 'no twin',
)


def review_of(entry: dict) -> dict:
    return entry['review'] if isinstance(entry.get('review'), dict) else entry


def review_has_input(review: dict) -> bool:
    return bool((review.get('comment') or '').strip() or review.get('focus'))


def review_needs_interpretation(review: dict) -> bool:
    if not review_has_input(review):
        return False
    meaning = review.get('meaning')
    if not isinstance(meaning, dict):
        return True
    if (review.get('comment') or '').strip() and 'description_en' not in meaning:
        return True
    return False


def description_for_focus(source_prompt: str, description: str, focus) -> str:
    """部位指定があるとき、その部位の句だけ残す。元の生成文の写しと範囲外は落とす。"""
    if not focus:
        return description
    have = {piece.strip() for piece in source_prompt.replace(';', ',').split(',') if piece.strip()}
    off = HAIR_OFF_MARKERS if list(focus) == ['hair'] else ()
    kept = []
    for piece in description.replace(';', ',').split(','):
        text = piece.strip()
        if not text or text in have or text in kept:
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in off):
            continue
        kept.append(text)
    return ', '.join(kept)


def apply_rating_to_meaning(rating, meaning: dict, focus) -> dict:
    """外部VLの解釈を、判定の契約に合わせて直す。OKでは直したい内容を残さない。"""
    result = {
        **meaning,
        'fix': list(meaning.get('fix') or []),
        'preserve': list(meaning.get('preserve') or []),
        'questions': list(meaning.get('questions') or []),
        'description_en': meaning.get('description_en') or '',
    }
    if rating != 'ok':
        return result
    result['fix'] = []
    result['description_en'] = ''
    chosen = [FOCUS_LABELS[key] for key in (focus if isinstance(focus, list) else []) if key in FOCUS_LABELS]
    result['preserve'] = chosen + [item for item in result['preserve'] if item not in chosen]
    return result


def require_interpreted_generation(reviews: list[dict]) -> None:
    for entry in reviews:
        review = review_of(entry)
        if review.get('rating') != 'ng':
            continue
        if not (review.get('comment') or '').strip():
            continue
        meaning = review.get('meaning') or {}
        if meaning.get('questions'):
            continue
        if not str(meaning.get('description_en') or '').strip():
            raise RuntimeError('判定の理解から生成文を作れませんでした。')


class PreviewReview(BaseModel):
    rating: Literal['ok', 'ng', '']
    revision: int
    comment: str | None = None
    focus: list[str] | None = None


class PreviewReviews:
    async def adopt_preview_lora(self, name: str, job_id: str) -> dict:
        """確認したプレビューのLoRA版を、次の設定画で使う版として採用する。"""
        job = self._preview_review_source(name, job_id)
        if job['status'] != 'completed':
            raise ValueError('生成が完了したプレビューを指定してください。')
        record = self._load_character(name)
        if record.get('adopted_preview_job_id') == job_id and record['lora_name'] == job['loras'][0][0]:
            return record
        record.setdefault('lora_history', []).append({'lora_name': record['lora_name'], 'preview_job_id': record.get('adopted_preview_job_id')})
        record['lora_name'] = job['loras'][0][0]
        record['character_strength'] = job['loras'][0][1]
        record['style'] = job.get('style', '')
        if len(job['loras']) > 1:
            record['style_strength'] = job['loras'][1][1]
        record['adopted_preview_job_id'] = job_id
        return self._save_character(record)

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
            if review.get('rating') == 'ok' and isinstance(review.get('meaning'), dict):
                review = {**review, 'meaning': apply_rating_to_meaning('ok', review['meaning'], review.get('focus'))}
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

    async def correct_preview_interpretation(self, name: str, job_id: str, image_id: str, correction: ReviewCorrection) -> dict:
        """画像の横で訂正した解釈を保存する。元の解釈も履歴に残す。"""
        view = await self.preview_reviews(name, job_id)
        picture = next((p for p in view['pictures'] if p['id'] == image_id), None)
        if picture is None:
            raise ValueError('このプレビューに含まれる画像を指定してください。')
        saved = await self.save_preview_review(name, job_id, image_id,
                                               PreviewReview(rating=picture['review']['rating'], revision=correction.revision))
        saved['meaning'] = apply_rating_to_meaning(saved['rating'], correction.meaning.model_dump(), saved.get('focus'))
        saved['meaning_source'] = 'user'
        self._store_review_meaning(name, job_id, image_id, saved)
        return saved

    def _store_review_meaning(self, name, job_id, image_id, review):
        reviews = self._preview_reviews(name, job_id)
        if reviews[image_id]['revision'] == review['revision']:
            reviews[image_id] = review
            self._preview_reviews_path(name, job_id).write_text(json.dumps(reviews, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    async def _interpret_preview_review(self, name, source, picture, samples, **kwargs):
        review = picture['review']
        if not review_needs_interpretation(review):
            return
        packet = {'stage': 'preview_review', 'review_input': {
            'stage': 'preview_review', 'image_id': picture['id'], 'rating': review['rating'],
            'comment': review['comment'], 'focus': review['focus'],
            'prompt': source['prompt'], 'negative': source['negative'], 'generation': source['generation'],
            'references': [{'kind': 'generated', 'id': picture['id']},
                           *[{'kind': 'sample', 'index': s['index'], 'caption': s.get('caption', '')} for s in samples]]}}
        images = [Path(picture['path']).read_bytes(), *[Path(s['path']).read_bytes() for s in samples]]
        meaning = ReviewMeaning.model_validate(await self.intent_interpreter(packet, images, **kwargs))
        review['meaning'] = apply_rating_to_meaning(review['rating'], meaning.model_dump(), review.get('focus'))
        if review.get('focus') and source.get('prompt'):
            review['meaning']['description_en'] = description_for_focus(
                source['prompt'], review['meaning'].get('description_en') or '', review['focus'])
        review['meaning_source'] = 'ai'
        review['interpreter'] = packet.get('interpreter')
        self._store_review_meaning(name, source['job_id'], picture['id'], review)
