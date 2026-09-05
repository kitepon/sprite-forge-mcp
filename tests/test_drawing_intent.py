"""一枚生成の注文を、実際に送るグラフと保存記録で確認する。"""
import asyncio
import json

import pytest

from backend import bible
from backend.intent import IntentRequest, Proposal
from tests.test_intent import proposal
from tests.test_style import make, png


async def setup(service, tmp_path):
    source = tmp_path / 'reference.png'
    source.write_bytes(png())
    await service.create_character('probe', 'she/her', lora_name='person.safetensors')
    await service.add_samples('probe', str(source))
    style = await service.create_style('probe')
    style['lora_name'] = 'look.safetensors'
    service._save_style(style)
    await service.add_style_samples('probe', str(source))


async def accepted(service, kind, stage='drawing'):
    job = await service.save_comment(IntentRequest(name='probe', kind=kind, stage=stage, comment='今回は傘を持ち、公園で。帽子は外して'))
    value = proposal(job['references'][0], scope='this_run', feature='accessory', text='holding an umbrella')
    value['changes'][0].update(avoid_en='hat', avoid_ja='帽子')
    value['changes'] += proposal(scope='this_run', feature='background', text='a green park')['changes']
    job.update(status='awaiting_confirmation', proposal=value)
    service.events.save_job(job)
    return await service.confirm_comment_intent(job['job_id'], Proposal.model_validate(value))


@pytest.mark.parametrize('kind', ['character', 'style'])
def test_drawing_uses_confirmed_conditions_in_graph_and_keeps_record(tmp_path, monkeypatch, kind):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        if kind == 'character':
            record = service._load_character('probe')
            record['intent_conditions'] = {'hair': proposal(feature='hair', text='short hair')['changes'][0]}
            service._save_character(record)
        intent = await accepted(service, kind)
        before = service._intent_record('probe', kind)
        job = await (service.generate_from_bible('probe', '', style='probe', seed=7, intent_job_id=intent['job_id'])
                     if kind == 'character' else service.generate_image('', 'probe', seed=7, intent_job_id=intent['job_id']))
        assert service._intent_record('probe', kind) == before
        assert job['intent_job_id'] == intent['job_id']
        assert 'holding an umbrella' in job['prompt'] and 'a green park' in job['prompt']
        assert job['negative'] == bible.NEGATIVE + ', hat'
        assert comfy.submitted[-1]['20']['inputs']['text'] == job['prompt']
        assert comfy.submitted[-1]['21']['inputs']['text'] == job['negative']
        assert comfy.submitted[-1]['23']['inputs']['seed'] == 7
        assert ('short hair' in job['prompt']) == (kind == 'character')
        assert service.events.load_job(job['job_id']) == json.loads(json.dumps(job))
        if kind == 'character':
            assert comfy.submitted[-1]['4']['inputs']['lora_name'] == 'person.safetensors'
            assert comfy.submitted[-1]['40']['inputs']['lora_name'] == 'look.safetensors'
        else:
            assert comfy.submitted[-1]['4']['inputs']['lora_name'] == 'look.safetensors'
            assert '40' not in comfy.submitted[-1]
        return job

    asyncio.run(scenario())


def test_common_conditions_are_used_without_new_order_but_not_combined_with_free_text(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        record = service._load_character('probe')
        record['intent_conditions'] = {'outfit': proposal(text='a yellow coat')['changes'][0]}
        service._save_character(record)
        job = await service.generate_from_bible('probe', '')
        assert job['prompt'] == 'probe, a yellow coat'
        with pytest.raises(ValueError, match='同時'):
            await service.generate_from_bible('probe', 'a red coat')
        assert len(comfy.submitted) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['character', 'style'])
def test_negative_only_order_without_positive_conditions_cannot_draw(tmp_path, monkeypatch, kind):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        job = await service.save_comment(IntentRequest(name='probe',kind=kind,stage='drawing',comment='帽子なし'))
        value = proposal(scope='this_run',feature='accessory',text='')
        value['changes'][0].update(avoid_en='hat',avoid_ja='帽子')
        job.update(status='awaiting_confirmation',proposal=value)
        service.events.save_job(job)
        await service.confirm_comment_intent(job['job_id'],Proposal.model_validate(value))
        with pytest.raises(ValueError,match='内容'):
            await (service.generate_from_bible('probe','',intent_job_id=job['job_id']) if kind=='character'
                   else service.generate_image('','probe',intent_job_id=job['job_id']))
        assert not comfy.submitted
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['character', 'style'])
@pytest.mark.parametrize('bad', ['unconfirmed', 'stage', 'kind', 'recreated', 'free_text', 'empty_order_free_text'])
def test_invalid_drawing_intent_never_starts_generation(tmp_path, monkeypatch, kind, bad):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        intent = await accepted(service, 'style' if kind == 'character' and bad == 'kind' else 'character' if bad == 'kind' else kind,
                                'preview' if bad == 'stage' else 'drawing')
        if bad == 'unconfirmed':
            intent['status'] = 'awaiting_confirmation'
            service.events.save_job(intent)
        if bad == 'recreated':
            record = service._intent_record('probe', kind)
            record['created'] = 'new record'
            service._save_intent_record(record, kind)
        if bad == 'empty_order_free_text':
            intent = await service.save_comment(IntentRequest(name='probe',kind=kind,stage='drawing',comment='維持'))
            value = {'observations':[], 'changes':[], 'questions':[]}
            intent.update(status='awaiting_confirmation',proposal=value)
            service.events.save_job(intent)
            intent = await service.confirm_comment_intent(intent['job_id'],Proposal.model_validate(value))
        prompt = 'a red room' if bad in ('free_text', 'empty_order_free_text') else ''
        with pytest.raises(ValueError):
            await (service.generate_from_bible('probe', prompt, intent_job_id=intent['job_id'])
                   if kind == 'character' else service.generate_image(prompt, 'probe', intent_job_id=intent['job_id']))
        assert not comfy.submitted
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['character', 'style'])
def test_drawing_preserves_legacy_free_input_and_rejects_empty_content(tmp_path, monkeypatch, kind):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        call = lambda prompt: service.generate_from_bible('probe', prompt) if kind == 'character' else service.generate_image(prompt, 'probe')
        job = await call('a fox under a tree')
        assert job['prompt'] == ('probe' if kind == 'character' else 'probe_style') + ', a fox under a tree'
        assert comfy.submitted[-1]['20']['inputs']['text'] == job['prompt']
        assert job['intent_job_id'] is None
        with pytest.raises(ValueError, match='内容'):
            await call('  ')
        assert len(comfy.submitted) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['character', 'style'])
@pytest.mark.parametrize('transport', ['rest', 'mcp'])
def test_drawing_public_entry_passes_adopted_order(tmp_path, monkeypatch, kind, transport):
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from backend import app

    service, comfy = make(tmp_path, monkeypatch)
    for key in ('characters_root', 'styles_root', 'generated_root', 'events', 'comfy', '_view'):
        monkeypatch.setattr(app.services, key, getattr(service, key))
    asyncio.run(setup(app.services, tmp_path))
    intent = asyncio.run(accepted(app.services, kind))
    args = {'prompt':'', 'intent_job_id':intent['job_id'], 'seed':9}
    args['name' if kind == 'character' else 'style'] = 'probe'
    if transport == 'rest':
        with TestClient(app.app) as client:
            response = client.post('/api/from-bible' if kind == 'character' else '/api/image', params=args)
            assert response.status_code == 200
            job = response.json()
    else:
        async def call():
            async with Client(app.mcp) as client:
                name = 'generate_from_bible' if kind == 'character' else 'generate_image'
                tool = next(tool for tool in await client.list_tools() if tool.name == name)
                assert 'intent_job_id' in tool.model_dump(by_alias=True)['inputSchema']['properties']
                result = await client.call_tool(name, args)
                assert not result.is_error
                return result.structured_content
        job = asyncio.run(call())
    assert job['intent_job_id'] == intent['job_id']
    assert job['prompt'] == comfy.submitted[-1]['20']['inputs']['text']
    assert job['negative'] == comfy.submitted[-1]['21']['inputs']['text']
