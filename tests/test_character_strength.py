"""強度の保存、旧台帳、生成経路と既存シートの再現を確認する。"""
import asyncio
from copy import deepcopy

import pytest

from tests.test_style import make
from tests.test_drawing_intent import setup


def test_strength_defaults_save_zero_reset_and_reject_invalid(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        original = service._load_character('probe')
        assert 'character_strength' not in original
        assert service._loras(original)[0] == [('person.safetensors', 0.8)]
        for strength in (0.4, 0, 2):
            saved = await service.set_character_strength('probe', strength)
            assert saved == {**original, 'character_strength': strength}
            assert service._loras(service._load_character('probe'))[0][0][1] == strength
        before = service._load_character('probe')
        for bad in (-0.1, 2.1, float('nan'), float('inf')):
            with pytest.raises(ValueError, match='0〜2'):
                await service.set_character_strength('probe', bad)
            assert service._load_character('probe') == before
        assert (await service.set_character_strength('probe'))['character_strength'] == 0.8

    asyncio.run(scenario())


def test_strength_reaches_every_new_generation_and_redraw_keeps_sheet_strength(tmp_path, monkeypatch):
    service, comfy = make(tmp_path, monkeypatch)

    async def scenario():
        await setup(service, tmp_path)
        await service.set_character_style('probe', 'probe', 0.6)
        await service.set_character_strength('probe', 0.4)
        for call, kwargs in ((service.preview_character, {}),
                             (service.generate_from_bible, {'prompt': 'standing'}),
                             (service.generate_character_bible, {})):
            start = len(comfy.submitted)
            job = await call('probe', **kwargs)
            assert job['loras'] == [('person.safetensors', 0.4), ('look.safetensors', 0.6)]
            for graph in comfy.submitted[start:]:
                assert graph['4']['inputs']['strength_model'] == 0.4
                assert graph['40']['inputs']['strength_model'] == 0.6
        sheet = deepcopy(service._load_character('probe')['bible'])
        await service.set_character_strength('probe', 0.8)
        assert service._load_character('probe')['bible'] == sheet
        await service.redraw_panel('probe', sheet['layout'][0]['key'], tags='standing')
        assert comfy.submitted[-1]['4']['inputs']['strength_model'] == 0.4
        assert comfy.submitted[-1]['40']['inputs']['strength_model'] == 0.6

    asyncio.run(scenario())


def test_strength_http_uses_shared_service(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import app, services
    service, _ = make(tmp_path, monkeypatch)
    asyncio.run(service.create_character('強度確認', 'she/her'))
    monkeypatch.setattr(services, 'characters_root', service.characters_root)
    monkeypatch.setattr(services, 'events', service.events)
    with TestClient(app) as client:
        response = client.post('/api/characters/強度確認/strength', params={'strength': 0.4})
        assert response.status_code == 200
        assert response.json()['character_strength'] == 0.4
        assert client.get('/api/characters/強度確認').json()['character_strength'] == 0.4
