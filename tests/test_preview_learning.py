"""判定の固定、AI解釈、再学習と新版プレビューの接続を確認する。"""
import asyncio
import json
from pathlib import Path
import uuid

import pytest

from backend import box
from backend.preview_learning import desired_generation_prompt, pair_spatial_regions, spatial_keys_from_focus_and_text
from backend.preview_reviews import PreviewReview
from backend.preview_intent import ReviewCorrection, ReviewMeaning
from tests.test_style import make, png


def sam_prompts(comfy):
    return [workflow['2']['inputs']['text'] for workflow in comfy.submitted
            if any(node.get('class_type') == 'SAM3_Detect' for node in workflow.values())]


GENERATED = '1girl, twintails, white dress, standing'


def quiet_interpret():
    async def interpret(*args, **kwargs):
        return {'fix': [], 'preserve': [], 'questions': [], 'description_en': ''}
    return interpret


def wire_training(monkeypatch):
    async def trained(*args, **kwargs):
        yield json.dumps({'step': 1, 'total': 1, 'loss': .69})
    async def fetched(remote, local, **kwargs):
        local.write_text(json.dumps({'reference_unchanged': True, 'lora_delta_squared': .01}))
        return 0, ''
    monkeypatch.setattr(box, 'stream_preference_training', trained)
    monkeypatch.setattr(box, 'copy_from_box', fetched)


def test_pair_spatial_regions_uses_ng_focus_and_general_fix_words():
    assert pair_spatial_regions({'rating': 'ok', 'focus': ['hair', 'face']}) == ()
    assert pair_spatial_regions({'rating': 'ng', 'focus': ['hair']}) == ('hair',)
    assert pair_spatial_regions({'rating': 'ng', 'focus': ['style']}) == ()
    assert pair_spatial_regions({'rating': 'ng', 'focus': ['hair', 'face', 'hair']}) == ('hair', 'face')
    assert pair_spatial_regions({'rating': 'ng', 'focus': [], 'meaning': {'fix': ['髪型']}}) == ('hair',)
    assert pair_spatial_regions({'rating': 'ng', 'focus': [], 'meaning': {'fix': ['顔も違う']}}) == ('face',)
    assert pair_spatial_regions({'rating': 'ng', 'comment': '髪型が違う', 'focus': []}) == ()


def test_spatial_keys_from_focus_and_text_prefers_focus():
    assert spatial_keys_from_focus_and_text(['hair'], '') == ('hair',)
    assert spatial_keys_from_focus_and_text(['style'], '') == ()
    assert spatial_keys_from_focus_and_text([], '髪型が違う') == ('hair',)
    assert spatial_keys_from_focus_and_text(['hair'], '顔も違う') == ('hair',)
    assert spatial_keys_from_focus_and_text({'kind': 'whole'}, '顔も違う') == ('face',)


async def settled(service, job):
    task = service._preview_learning_tasks.get(job['job_id'])
    if task is not None:
        await task
    return service.events.load_job(job['job_id'])


async def prepared(service, tmp_path, comment=''):
    await service.create_character('probe', 'she/her', lora_name='person.safetensors')
    sample = tmp_path / 'reference.png'
    sample.write_bytes(png('red'))
    await service.add_samples('probe', str(sample), '元のサンプル')
    job = await service.preview_character('probe', count=3)
    for index, rating in enumerate(['ok', 'ng']):
        await service.save_preview_review('probe', job['job_id'], job['pictures'][index]['id'],
                                          PreviewReview(rating=rating, revision=0, comment=comment if index else ''))
    return job


def test_snapshot_uses_both_ratings_and_keeps_old_lora(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    calls = []
    async def transferred(directory, remote, **kwargs):
        config = json.loads((directory / 'input.json').read_text())
        assert len(config['pairs']) == 1
        assert config['lora'].endswith('/person.safetensors')
        assert config['size'] == [832, 1216]
        assert config['masks'] == [None]
        assert config['pair_regions'] == [[]]
        for path in config['pairs'][0]:
            assert (directory / Path(path).name).read_bytes() == png()
        calls.append(config)
        # 学習の転送中に判定を変えても固定済みの教材は変わらない。
        await service.save_preview_review('probe', source['job_id'], source['pictures'][1]['id'],
                                          PreviewReview(rating='ok', revision=1, comment='後の変更'))
        return 0, ''
    async def trained(*args, **kwargs):
        yield json.dumps({'step': 1, 'total': 1, 'loss': .69})
    async def fetched(remote, local, **kwargs):
        local.write_text(json.dumps({'reference_unchanged': True, 'lora_delta_squared': .01}))
        return 0, ''
    monkeypatch.setattr(box, 'copy_tree_to_box', transferred)
    monkeypatch.setattr(box, 'stream_preference_training', trained)
    monkeypatch.setattr(box, 'copy_from_box', fetched)
    async def scenario():
        nonlocal source
        source = await prepared(service, tmp_path)
        before = service._load_character('probe')
        request_id = str(uuid.uuid4())
        started = await service.relearn_preview('probe', source['job_id'], request_id, steps=1)
        assert started['status'] == 'interpreting'
        job = await settled(service, started)
        assert job['status'] == 'completed'
        assert [p['review']['rating'] for p in job['reviews']] == ['ok', 'ng']
        preview = service.events.load_job(job['preview_job_id'])
        assert len(preview['pictures']) == 10
        assert preview['loras'][0][0] == job['lora_name']
        assert preview['prompt'] == source['prompt'] and preview['generation'] == source['generation']
        assert service._load_character('probe') == before
        assert await service.relearn_preview('probe', source['job_id'], request_id, steps=1) == job
        assert len(calls) == 1
    source = None
    asyncio.run(scenario())


def test_comment_distinguishes_generated_image_and_samples_and_asks_only_ambiguity(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def interpret(packet, images, **kwargs):
        assert images == [png(), Path(service._load_character('probe')['samples'][0]['path']).read_bytes()]
        value = packet['review_input']
        assert value['rating'] == 'ng'
        assert value['references'][0]['kind'] == 'generated'
        assert value['references'][1]['kind'] == 'sample'
        return {'fix': [], 'preserve': ['衣装'], 'questions': ['NGなのはどの部分ですか？'], 'description_en': ''}
    service.intent_interpreter = interpret
    async def scenario():
        source = await prepared(service, tmp_path, '衣装は合っている')
        job = await settled(service, await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4())))
        assert job['status'] == 'awaiting_answers'
        image_id = source['pictures'][1]['id']
        assert job['questions'][0]['image_id'] == image_id
        review = (await service.preview_reviews('probe', source['job_id']))['pictures'][1]['review']
        assert review['meaning']['preserve'] == ['衣装'] and not review['meaning']['fix']
        corrected = await service.correct_preview_interpretation('probe', source['job_id'], image_id,
                       ReviewCorrection(revision=1, meaning=ReviewMeaning(fix=['髪型'], preserve=['衣装'], questions=[], description_en='')))
        assert corrected['history'][0]['meaning'] == review['meaning']
        assert corrected['comment'] == '衣装は合っている'
        saved = await service.save_preview_review('probe', source['job_id'], image_id,
                                                  PreviewReview(rating='ng', revision=2, comment='顔も違う'))
        assert 'meaning' not in saved
    asyncio.run(scenario())


def test_interpretation_failure_stays_failed_and_does_not_train(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def failed(*args, **kwargs):
        raise RuntimeError('解釈サービスの失敗')
    service.intent_interpreter = failed
    async def scenario():
        source = await prepared(service, tmp_path, '髪型が違う')
        request_id = str(uuid.uuid4())
        started = await service.relearn_preview('probe', source['job_id'], request_id)
        assert started['status'] == 'interpreting'
        with pytest.raises(RuntimeError, match='解釈サービス'):
            await service._preview_learning_tasks[request_id]
        job = service.events.load_job(request_id)
        assert job['status'] == 'failed'
        assert 'training_config' not in job
    asyncio.run(scenario())


def test_too_few_steps_does_not_silently_omit_a_rating(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def scenario():
        source = await prepared(service, tmp_path)
        await service.save_preview_review('probe', source['job_id'], source['pictures'][2]['id'], PreviewReview(rating='ng', revision=0))
        with pytest.raises(ValueError, match='学習回数を2以上'):
            await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1)
    asyncio.run(scenario())


def test_answers_continue_same_request_and_keep_preparation_history(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    async def interpret(*args, **kwargs):
        return {'fix': [], 'preserve': ['衣装'], 'questions': ['NGなのはどの部分ですか？'], 'description_en': ''}
    service.intent_interpreter = interpret
    wire_training(monkeypatch)
    async def scenario():
        source = await prepared(service, tmp_path, '衣装は合っている')
        request_id = str(uuid.uuid4())
        waiting = await settled(service, await service.relearn_preview('probe', source['job_id'], request_id, steps=1))
        assert waiting['status'] == 'awaiting_answers'
        assert await service.relearn_preview('probe', source['job_id'], request_id) == waiting
        await service.correct_preview_interpretation('probe', source['job_id'], source['pictures'][1]['id'],
                    ReviewCorrection(revision=1, meaning=ReviewMeaning(fix=['髪型'], preserve=['衣装'], questions=[], description_en=GENERATED)))
        result = await settled(service, await service.relearn_preview('probe', source['job_id'], request_id))
        assert result['status'] == 'completed' and result['job_id'] == request_id and result['steps'] == 1
        assert result['preparation_history'][0]['questions'] == waiting['questions']
        assert result['preparation_history'][0]['reviews'][1]['review']['revision'] == 1
        assert result['reviews'][1]['review']['revision'] == 2
        assert result['training_config']['pair_regions'] == [['hair']]
        assert result['training_config']['prompt'] == GENERATED
        assert '衣装は合っている' not in result['training_config']['prompt']
        assert service.events.load_job(result['preview_job_id'])['prompt'] == GENERATED
        assert sam_prompts(comfy) == ['hair', 'hair']
        ok_id, ng_id = result['pairs'][0]
        assert (Path(result['dataset']) / f'{ok_id}.mask.png').is_file()
        assert (Path(result['dataset']) / f'{ng_id}.mask.png').is_file()
    asyncio.run(scenario())


def test_ng_hair_focus_masks_only_hair_and_keeps_source_prompt(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    service.intent_interpreter = quiet_interpret()
    wire_training(monkeypatch)
    async def scenario():
        source = await prepared(service, tmp_path)
        await service.save_preview_review(
            'probe', source['job_id'], source['pictures'][0]['id'],
            PreviewReview(rating='ok', revision=1, focus=['hair', 'face', 'outfit', 'body', 'style']))
        await service.save_preview_review(
            'probe', source['job_id'], source['pictures'][1]['id'],
            PreviewReview(rating='ng', revision=1, focus=['hair']))
        job = await settled(service, await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1))
        assert job['status'] == 'completed'
        assert job['training_config']['pair_regions'] == [['hair']]
        assert job['training_config']['prompt'] == source['prompt']
        assert sam_prompts(comfy) == ['hair', 'hair']
        ok_id, ng_id = job['pairs'][0]
        assert (Path(job['dataset']) / f'{ok_id}.mask.png').is_file()
        assert (Path(job['dataset']) / f'{ng_id}.mask.png').is_file()
        assert job['training_config']['masks'][0] is not None
    asyncio.run(scenario())


def test_style_only_ng_uses_fullscreen_without_sam(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    service.intent_interpreter = quiet_interpret()
    wire_training(monkeypatch)
    async def scenario():
        source = await prepared(service, tmp_path)
        await service.save_preview_review(
            'probe', source['job_id'], source['pictures'][1]['id'],
            PreviewReview(rating='ng', revision=1, focus=['style']))
        job = await settled(service, await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1))
        assert job['status'] == 'completed'
        assert job['training_config']['pair_regions'] == [[]]
        assert job['training_config']['masks'] == [None]
        assert sam_prompts(comfy) == []
    asyncio.run(scenario())


def test_empty_sam_mask_fails_without_fullscreen_fallback(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    service.intent_interpreter = quiet_interpret()
    async def black(_image):
        return png('#000000')
    async def scenario():
        source = await prepared(service, tmp_path)
        service._view = black
        await service.save_preview_review(
            'probe', source['job_id'], source['pictures'][1]['id'],
            PreviewReview(rating='ng', revision=1, focus=['hair']))
        started = await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1)
        with pytest.raises(RuntimeError, match='マスクが空です'):
            await settled(service, started)
        job = service.events.load_job(started['job_id'])
        assert job['status'] == 'failed'
        assert 'マスクが空です' in job['error']
        assert 'training_config' not in job
    asyncio.run(scenario())


def test_preview_burst_keeps_model_loaded_until_last_interpretation(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    calls = []
    async def interpret(packet, images, **kwargs):
        calls.append({k: kwargs[k] for k in ('keep_model_loaded', 'reclaim_memory')})
        return {'fix': [], 'preserve': ['衣装'], 'questions': [], 'description_en': GENERATED}
    async def trained(*args, **kwargs):
        yield json.dumps({'step': 1, 'total': 1, 'loss': .69})
    async def fetched(remote, local, **kwargs):
        local.write_text('{}')
        return 0, ''
    service.intent_interpreter = interpret
    monkeypatch.setattr(box, 'stream_preference_training', trained)
    monkeypatch.setattr(box, 'copy_from_box', fetched)
    async def scenario():
        source = await prepared(service, tmp_path, '髪型が違う')
        await service.save_preview_review(
            'probe', source['job_id'], source['pictures'][0]['id'],
            PreviewReview(rating='ok', revision=1, comment='衣装は合っている'))
        job = await settled(service, await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1))
        assert job['status'] == 'completed'
        assert calls == [
            {'keep_model_loaded': True, 'reclaim_memory': True},
            {'keep_model_loaded': False, 'reclaim_memory': False},
        ]
    asyncio.run(scenario())


def test_relearn_preview_returns_before_training_and_resume_does_not_double_start(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    gate = asyncio.Event()
    async def trained(*args, **kwargs):
        await gate.wait()
        yield json.dumps({'step': 1, 'total': 1})
    async def fetched(remote, local, **kwargs):
        local.write_text('{}')
        return 0, ''
    monkeypatch.setattr(box, 'stream_preference_training', trained)
    monkeypatch.setattr(box, 'copy_from_box', fetched)
    async def scenario():
        source = await prepared(service, tmp_path)
        started = await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1)
        assert started['status'] == 'interpreting'
        live = service._ensure_preview_learning(started['job_id'])
        assert not live.done()
        await service.resume_preview_learning()
        assert service._preview_learning_tasks[started['job_id']] is live
        orphan = service._preview_learning_tasks.pop(started['job_id'])
        orphan.cancel()
        with pytest.raises(asyncio.CancelledError):
            await orphan
        await service.resume_preview_learning()
        restarted = service._preview_learning_tasks[started['job_id']]
        assert restarted is not orphan and not restarted.done()
        gate.set()
        final = await settled(service, started)
        assert final['status'] == 'completed'
    asyncio.run(scenario())


def test_desired_generation_prompt_uses_interpreted_english_not_comment():
    source = '1girl, standing'
    assert desired_generation_prompt(source, []) == source
    assert desired_generation_prompt(source, [{'comment': '髪型が違う', 'meaning': {}}]) == source
    nested = {'review': {'comment': '日本語の原文は貼らない', 'meaning': {'description_en': GENERATED}}}
    assert desired_generation_prompt(source, [nested]) == GENERATED
    assert '日本語' not in desired_generation_prompt(source, [nested])
    shorter = '1girl, twintails'
    assert desired_generation_prompt(source, [
        {'meaning': {'description_en': shorter}},
        {'review': {'meaning': {'description_en': GENERATED}}},
    ]) == GENERATED
    assert desired_generation_prompt(source, [
        {'meaning': {'description_en': 'red hair'}},
        {'meaning': {'description_en': 'white dress'}},
    ]) == 'red hair, white dress'
    assert desired_generation_prompt(source, [
        {'meaning': {'description_en': GENERATED}},
        {'meaning': {'description_en': GENERATED}},
    ]) == GENERATED


def test_learning_and_preview_use_interpreted_generation_text(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def interpret(*args, **kwargs):
        return {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': [], 'description_en': GENERATED}
    service.intent_interpreter = interpret
    wire_training(monkeypatch)
    async def scenario():
        source = await prepared(service, tmp_path, '髪型が違う。衣装は合っている')
        job = await settled(service, await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1))
        assert job['status'] == 'completed'
        assert job['training_config']['prompt'] == GENERATED
        assert '髪型が違う' not in job['training_config']['prompt']
        assert service.events.load_job(job['preview_job_id'])['prompt'] == GENERATED
        review = (await service.preview_reviews('probe', source['job_id']))['pictures'][1]['review']
        assert review['meaning']['description_en'] == GENERATED
    asyncio.run(scenario())


def test_empty_generation_text_fails_before_training(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    async def interpret(*args, **kwargs):
        return {'fix': ['髪型'], 'preserve': [], 'questions': [], 'description_en': ''}
    service.intent_interpreter = interpret
    wire_training(monkeypatch)
    async def scenario():
        source = await prepared(service, tmp_path, '髪型が違う')
        started = await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1)
        with pytest.raises(RuntimeError, match='生成文を作れませんでした'):
            await settled(service, started)
        job = service.events.load_job(started['job_id'])
        assert job['status'] == 'failed'
        assert '生成文を作れませんでした' in job['error']
        assert 'training_config' not in job
    asyncio.run(scenario())


def test_legacy_meaning_without_generation_text_is_reinterpreted(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    calls = []
    async def interpret(*args, **kwargs):
        calls.append(1)
        return {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': [], 'description_en': GENERATED}
    service.intent_interpreter = interpret
    wire_training(monkeypatch)
    async def scenario():
        source = await prepared(service, tmp_path, '髪型が違う')
        path = service._preview_reviews_path('probe', source['job_id'])
        reviews = json.loads(path.read_text(encoding='utf-8'))
        image_id = source['pictures'][1]['id']
        reviews[image_id]['meaning'] = {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': []}
        reviews[image_id]['meaning_source'] = 'ai'
        path.write_text(json.dumps(reviews, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        job = await settled(service, await service.relearn_preview('probe', source['job_id'], str(uuid.uuid4()), steps=1))
        assert job['status'] == 'completed'
        assert len(calls) == 1
        assert job['training_config']['prompt'] == GENERATED
        assert '髪型が違う' not in job['training_config']['prompt']
    asyncio.run(scenario())
