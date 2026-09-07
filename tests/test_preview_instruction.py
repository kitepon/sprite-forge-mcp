"""判定から指示文書を更新し、同じLoRAでプレビューを作り直す。"""
import asyncio
import base64
import json
import uuid

import pytest

from backend.intent_cli import run
from tests.test_preview_learning import prepared
from tests.test_style import make


def interpret_both(include='twin tails', questions=None):
    async def interpret(packet, images):
        if packet.get('stage') == 'preview_instruction' or 'instruction_input' in packet:
            return {'include_en': include, 'avoid_en': '', 'summary_ja': 'ツインテールを要求する',
                    'questions': questions or []}
        return {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': []}
    return interpret


def test_revise_keeps_lora_and_inserts_instruction(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)
    service.intent_interpreter = interpret_both()

    async def scenario():
        source = await prepared(service, tmp_path, '髪型がツインテールではない')
        before = service._load_character('probe')
        request_id = str(uuid.uuid4())
        job = await service.revise_preview_instruction('probe', source['job_id'], request_id)
        assert job['status'] == 'completed'
        assert job['lora_name'] == 'person.safetensors'
        preview = service.events.load_job(job['preview_job_id'])
        assert list(preview['loras'][0]) == list(source['loras'][0])
        assert preview['seed'] == source['seed']
        assert preview['prompt'].startswith('probe, twin tails,')
        assert 'twin tails' in preview['prompt']
        assert preview['generation'] == source['generation']
        record = service._load_character('probe')
        assert record['lora_name'] == before['lora_name']
        assert record['identity_instruction']['include_en'] == 'twin tails'
        assert record['identity_instruction']['lora_name'] == 'person.safetensors'
        adopted = await service.adopt_preview_lora('probe', preview['job_id'])
        assert adopted['lora_name'] == 'person.safetensors'
        assert adopted['identity_instruction']['include_en'] == 'twin tails'
        drawing = await service.generate_from_bible('probe', 'on stage')
        assert drawing['prompt'].startswith('probe, twin tails, on stage')
        assert await service.revise_preview_instruction('probe', source['job_id'], request_id) == job

    asyncio.run(scenario())


def test_ng_requires_reason_and_does_not_train(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    service.intent_interpreter = interpret_both()

    async def scenario():
        source = await prepared(service, tmp_path)
        with pytest.raises(ValueError, match='理由'):
            await service.revise_preview_instruction('probe', source['job_id'], str(uuid.uuid4()))
        assert service._load_character('probe')['lora_name'] == 'person.safetensors'
        assert 'identity_instruction' not in service._load_character('probe')

    asyncio.run(scenario())


def test_style_words_in_instruction_fail_without_saving(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    service.intent_interpreter = interpret_both('anime style, twin tails')

    async def scenario():
        source = await prepared(service, tmp_path, '画風を変えたい')
        with pytest.raises(ValueError, match='画風'):
            await service.revise_preview_instruction('probe', source['job_id'], str(uuid.uuid4()))
        assert 'identity_instruction' not in service._load_character('probe')

    asyncio.run(scenario())


def test_preview_can_omit_saved_instruction(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    service.intent_interpreter = interpret_both()

    async def scenario():
        source = await prepared(service, tmp_path, '髪型がツインテールではない')
        await service.revise_preview_instruction('probe', source['job_id'], str(uuid.uuid4()))
        with_instruction = await service.preview_character('probe', count=1)
        without = await service.preview_character('probe', count=1, use_instruction=False)
        assert 'twin tails' in with_instruction['prompt']
        assert 'twin tails' not in without['prompt']
        style = await service.create_style('glow')
        style['lora_name'] = 'look.safetensors'
        service._save_style(style)
        image = await service.generate_image('a landscape', 'glow', character='probe', use_instruction=True)
        assert image['prompt'].startswith('glow_style, twin tails, a landscape')
        plain = await service.generate_image('a landscape', 'glow')
        assert 'twin tails' not in plain['prompt']

    asyncio.run(scenario())


def test_answers_continue_same_request(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    calls = []

    async def interpret(packet, images):
        calls.append(packet.get('stage') or packet.get('instruction_input', {}).get('stage'))
        if packet.get('stage') == 'preview_instruction' or 'instruction_input' in packet:
            return {'include_en': 'twin tails', 'avoid_en': '', 'summary_ja': 'ツインテール', 'questions': []}
        if len(calls) == 1:
            return {'fix': [], 'preserve': ['衣装'], 'questions': ['NGなのはどの部分ですか？']}
        return {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': []}

    service.intent_interpreter = interpret

    async def scenario():
        source = await prepared(service, tmp_path, '衣装は合っている')
        request_id = str(uuid.uuid4())
        waiting = await service.revise_preview_instruction('probe', source['job_id'], request_id)
        assert waiting['status'] == 'awaiting_answers'
        assert service._load_character('probe').get('identity_instruction') is None
        from backend.preview_intent import ReviewCorrection, ReviewMeaning
        await service.correct_preview_interpretation('probe', source['job_id'], source['pictures'][1]['id'],
                    ReviewCorrection(revision=1, meaning=ReviewMeaning(fix=['髪型'], preserve=['衣装'], questions=[])))
        result = await service.revise_preview_instruction('probe', source['job_id'], request_id)
        assert result['status'] == 'completed' and result['job_id'] == request_id
        assert result['identity_instruction']['include_en'] == 'twin tails'

    asyncio.run(scenario())


def test_cli_uses_instruction_file_without_style_or_part_branches():
    from backend.intent_cli import prompt_for
    from tests.test_intent_cli import FakeComfy
    prompt = prompt_for({'input': {'stage': 'preview_instruction', 'previous': {'include_en': ''}}, 'images': ['x']})
    assert '画風・質感・線・彩色の語句は入れません' in prompt
    assert '特定の部位専用の手順は作りません' in prompt
    result = run({'input': {'stage': 'preview_instruction', 'previous': {'include_en': ''}},
                  'images': [base64.b64encode(b'image-fixture').decode()]},
                 FakeComfy(json.dumps({
                     'include_en': 'twin tails', 'avoid_en': '', 'summary_ja': '要約', 'questions': []})))
    assert result['proposal']['include_en'] == 'twin tails'
