"""判定の固定、AI解釈、再学習と新版プレビューの接続を確認する。"""
import asyncio
import json
from pathlib import Path
import uuid

import pytest

from backend import box
from backend.preview_reviews import PreviewReview
from backend.preview_intent import ReviewCorrection, ReviewMeaning
from tests.test_style import make, png


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
        return {'fix': [], 'preserve': ['衣装'], 'questions': ['NGなのはどの部分ですか？']}
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
                       ReviewCorrection(revision=1, meaning=ReviewMeaning(fix=['髪型'], preserve=['衣装'], questions=[])))
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
    service, _ = make(tmp_path, monkeypatch)
    async def interpret(*args, **kwargs):
        return {'fix': [], 'preserve': ['衣装'], 'questions': ['NGなのはどの部分ですか？']}
    async def trained(*args, **kwargs):
        yield '{"step": 1, "total": 1}'
    async def fetched(remote, local, **kwargs):
        local.write_text('{}')
        return 0, ''
    service.intent_interpreter = interpret
    monkeypatch.setattr(box, 'stream_preference_training', trained)
    monkeypatch.setattr(box, 'copy_from_box', fetched)
    async def scenario():
        source = await prepared(service, tmp_path, '衣装は合っている')
        request_id = str(uuid.uuid4())
        waiting = await settled(service, await service.relearn_preview('probe', source['job_id'], request_id, steps=1))
        assert waiting['status'] == 'awaiting_answers'
        assert await service.relearn_preview('probe', source['job_id'], request_id) == waiting
        await service.correct_preview_interpretation('probe', source['job_id'], source['pictures'][1]['id'],
                    ReviewCorrection(revision=1, meaning=ReviewMeaning(fix=['髪型'], preserve=['衣装'], questions=[])))
        result = await settled(service, await service.relearn_preview('probe', source['job_id'], request_id))
        assert result['status'] == 'completed' and result['job_id'] == request_id and result['steps'] == 1
        assert result['preparation_history'][0]['questions'] == waiting['questions']
        assert result['preparation_history'][0]['reviews'][1]['review']['revision'] == 1
        assert result['reviews'][1]['review']['revision'] == 2
    asyncio.run(scenario())


def test_preview_burst_keeps_model_loaded_until_last_interpretation(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    calls = []
    async def interpret(packet, images, **kwargs):
        calls.append({k: kwargs[k] for k in ('keep_model_loaded', 'reclaim_memory')})
        return {'fix': [], 'preserve': ['衣装'], 'questions': []}
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
