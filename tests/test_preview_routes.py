"""RESTから、画像に対応する判定と解釈訂正を保存できることを確認する。"""
import asyncio

from fastapi.testclient import TestClient

from backend import app as module
from tests.test_style import make


def test_review_body_and_interpretation_share_service_state(tmp_path, monkeypatch):
    service, _ = make(tmp_path, monkeypatch)
    for key, value in service.__dict__.items():
        monkeypatch.setattr(module.services, key, value, raising=False)
    asyncio.run(service.create_character('probe', 'she/her', lora_name='person.safetensors'))
    job = asyncio.run(service.preview_character('probe', count=1))
    image_id = job['pictures'][0]['id']
    url = f"/api/characters/probe/previews/{job['job_id']}/reviews"
    with TestClient(module.app) as client:
        response = client.post(f'{url}/{image_id}', json={'rating': 'ng', 'revision': 0, 'comment': '髪が違う'})
        assert response.status_code == 200
        response = client.get(url)
        assert response.json()['pictures'][0]['review']['comment'] == '髪が違う'
        response = client.post(f'{url}/{image_id}/interpretation', json={
            'revision': 1, 'meaning': {'fix': ['髪型'], 'preserve': ['衣装'], 'questions': [], 'description_en': '1girl, twintails, white dress, standing'}})
        assert response.status_code == 200
        assert response.json()['meaning_source'] == 'user'
