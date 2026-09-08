"""プレビュー画像と判定の対応、逐次生成中の保存、競合を確認する。"""
import asyncio
import hashlib
from pathlib import Path

import pytest

from backend.preview_reviews import PreviewReview, apply_rating_to_meaning, require_interpreted_generation
from tests.test_style import make


def test_ok_rating_clears_fix_and_adds_focus_labels_to_preserve():
    meaning = {
        'fix': ['髪型', '顔'],
        'preserve': ['衣装', 'スタイル', '体格比例', '背景'],
        'questions': [],
        'description_en': '1girl, standing',
    }
    result = apply_rating_to_meaning('ok', meaning, ['hair', 'face', 'outfit', 'body', 'style'])
    assert result['fix'] == []
    assert result['description_en'] == ''
    assert result['preserve'] == ['髪', '顔', '衣装', '体形', '画風', 'スタイル', '体格比例', '背景']


def test_preview_reviews_normalizes_stored_ok_meaning_without_rewriting_json(tmp_path, monkeypatch):
    import json
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character('ベル', 'she/her', lora_name='person.safetensors')
        job = await service.preview_character('ベル', seed=7)
        image = job['pictures'][0]['id']
        await service.save_preview_review('ベル', job['job_id'], image,
                                          PreviewReview(rating='ok', revision=0, focus=['hair', 'face', 'outfit', 'body', 'style']))
        path = service._preview_reviews_path('ベル', job['job_id'])
        stored = json.loads(path.read_text(encoding='utf-8'))
        stored[image]['meaning'] = {'fix': ['髪型', '顔'], 'preserve': ['衣装', '体型', 'スタイル'], 'questions': [], 'description_en': ''}
        stored[image]['meaning_source'] = 'ai'
        path.write_text(json.dumps(stored, ensure_ascii=False), encoding='utf-8')
        view = await service.preview_reviews('ベル', job['job_id'])
        meaning = view['pictures'][0]['review']['meaning']
        assert meaning['fix'] == []
        assert meaning['preserve'] == ['髪', '顔', '衣装', '体形', '画風', '体型', 'スタイル']
        assert json.loads(path.read_text(encoding='utf-8'))[image]['meaning']['fix'] == ['髪型', '顔']

    asyncio.run(scenario())


def test_ng_rating_keeps_vl_meaning():
    meaning = {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': [], 'description_en': '1girl'}
    assert apply_rating_to_meaning('ng', meaning, ['hair']) == {
        'fix': ['髪型'], 'preserve': ['衣装'], 'questions': [], 'description_en': '1girl',
    }


def test_require_interpreted_generation_skips_ok_comment_and_fails_ng_empty():
    require_interpreted_generation([
        {'rating': 'ok', 'comment': '衣装は合っている', 'meaning': {'description_en': ''}},
    ])
    with pytest.raises(RuntimeError, match='生成文を作れませんでした'):
        require_interpreted_generation([
            {'rating': 'ng', 'comment': '髪型が違う', 'meaning': {'description_en': ''}},
        ])



def test_ten_previews_keep_ratings_during_generation_and_reload(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await service.create_character('ベル', 'she/her', lora_name='person.safetensors')
        run_edit = service._run_edit
        async def generate(job_id, graph):
            prior = service.events.load_job(job_id)['pictures']
            if len(prior) == 1:
                await service.save_preview_review('ベル', job_id, prior[0]['id'], PreviewReview(rating='ok', revision=0))
            return await run_edit(job_id, graph)
        service._run_edit = generate
        job = await service.preview_character('ベル', seed=7)
        assert len(job['pictures']) == 10
        assert [p['seed'] for p in job['pictures']] == list(range(7, 17))
        assert len({p['id'] for p in job['pictures']}) == 10
        assert all(p['sha256'] == hashlib.sha256(Path(p['path']).read_bytes()).hexdigest() for p in job['pictures'])
        assert job['generation']['steps'] == comfy.submitted[0]['23']['inputs']['steps']
        assert job['loras'] == [('person.safetensors', .8)]
        result = await service.preview_reviews('ベル', job['job_id'])
        assert result['pictures'][0]['review']['rating'] == 'ok'
        assert all(not p['review']['rating'] for p in result['pictures'][1:])
        image = result['pictures'][1]['id']
        await service.save_preview_review('ベル', job['job_id'], image,
                                          PreviewReview(rating='ng', revision=0, comment='髪が違う。衣装は合っている', focus=['hair']))
        saved = await service.save_preview_review('ベル', job['job_id'], image, PreviewReview(rating='', revision=1))
        assert saved['comment'] == '髪が違う。衣装は合っている'
        assert saved['history'][0]['rating'] == 'ng'
        fresh, _ = make(tmp_path, monkeypatch)
        reloaded = await fresh.preview_reviews('ベル', job['job_id'])
        assert reloaded['pictures'][1]['review'] == saved
        assert reloaded['relearning_unavailable_reason'] == ''
        assert fresh._load_character('ベル')['samples'] == []
    asyncio.run(scenario())


def test_conflicts_wrong_images_and_recreated_characters(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await service.create_character('first', 'she/her', lora_name='person.safetensors')
        await service.create_character('other', 'she/her', lora_name='other.safetensors')
        job = await service.preview_character('first', count=2)
        image = job['pictures'][0]['id']
        await service.save_preview_review('first', job['job_id'], image, PreviewReview(rating='ok', revision=0))
        with pytest.raises(ValueError, match='別の画面'):
            await service.save_preview_review('first', job['job_id'], image, PreviewReview(rating='ng', revision=0))
        with pytest.raises(ValueError, match='含まれる画像'):
            await service.save_preview_review('first', job['job_id'], 'unknown', PreviewReview(rating='ng', revision=0))
        with pytest.raises(ValueError, match='このキャラクター'):
            await service.preview_reviews('other', job['job_id'])
        await service.create_character('first', 'new character', lora_name='new.safetensors')
        with pytest.raises(ValueError, match='作り直す前'):
            await service.preview_reviews('first', job['job_id'])
    asyncio.run(scenario())


def test_old_preview_can_be_rated_but_explains_missing_training_context(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        await service.create_character('old', 'she/her', lora_name='person.safetensors')
        job = await service.preview_character('old', count=1)
        del job['generation'], job['character_created']
        del job['pictures'][0]['id'], job['pictures'][0]['sha256']
        service.events.save_job(job)
        view = await service.preview_reviews('old', job['job_id'])
        assert '新しくプレビュー' in view['relearning_unavailable_reason']
        image = view['pictures'][0]['id']
        await service.save_preview_review('old', job['job_id'], image, PreviewReview(rating='ng', revision=0))
        assert (await service.preview_reviews('old', job['job_id']))['pictures'][0]['review']['rating'] == 'ng'
    asyncio.run(scenario())


def test_adopted_lora_is_used_by_setting_sheet_and_old_version_can_be_restored(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    async def scenario():
        await service.create_character('probe', 'she/her', lora_name='old.safetensors')
        old = await service.preview_character('probe', count=1)
        new = {**old, 'job_id': 'new-preview', 'loras': [['new.safetensors', .65]]}
        service.events.save_job(new)
        adopted = await service.adopt_preview_lora('probe', new['job_id'])
        assert adopted['lora_name'] == 'new.safetensors' and adopted['character_strength'] == .65
        assert await service.adopt_preview_lora('probe', new['job_id']) == adopted
        comfy.submitted.clear()
        await service.generate_character_bible('probe')
        assert comfy.submitted and all(graph['4']['inputs']['lora_name'] == 'new.safetensors' for graph in comfy.submitted)
        restored = await service.adopt_preview_lora('probe', old['job_id'])
        assert restored['lora_name'] == 'old.safetensors'
        assert restored['lora_history'][-1]['lora_name'] == 'new.safetensors'
    asyncio.run(scenario())
