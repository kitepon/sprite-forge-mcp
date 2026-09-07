from __future__ import annotations

import asyncio
import json
import unittest

from backend.intent_cli import AUTH, MODEL, OBSERVE_MARK, execute
from backend.intent_runner import interpret

SCHEMA_LEAD = '出力は次の JSON Schema に厳密に従い、前後に説明を付けないでください。'
EMPTY = {
    'observations': [],
    'changes': [],
    'questions': [],
    'training_samples': None,
}


class FakeComfy:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.keeps: list[bool] = []
        self.queued: list[dict] = []
        self.freed = 0
        self.queue_running: list = []
        self.queue_pending: list = []
        self._n = 0

    async def queue(self) -> dict:
        return {'queue_running': self.queue_running, 'queue_pending': self.queue_pending}

    async def upload(self, content: bytes, name: str) -> str:
        return name

    async def submit(self, workflow: dict, client_id: str) -> str:
        self._n += 1
        prompt_id = f'p{self._n}'
        self.queued.append(workflow)
        qwen = workflow['2']['inputs']
        self.prompts.append(str(qwen['custom_prompt']))
        self.keeps.append(bool(qwen['keep_model_loaded']))
        return prompt_id

    async def history(self, prompt_id: str) -> dict:
        prompt = self.prompts[int(prompt_id[1:]) - 1]
        if OBSERVE_MARK in prompt:
            text = json.dumps({
                'appearance_ja': '赤いリボンの少女',
                'caption_en': 'a girl with a red ribbon',
            }, ensure_ascii=False)
        elif '入力:\n' in prompt:
            payload = _payload_from_prompt(prompt)
            stage = payload.get('stage')
            if stage == 'layout':
                layout = payload['sheet_layout']
                text = json.dumps({
                    'summary_ja': '構成の確認',
                    'questions': [],
                    'panels': [dict(panel, description_ja=panel['label'], reference=None) for panel in layout],
                }, ensure_ascii=False)
            elif stage == 'preview_review':
                text = json.dumps({'fix': [], 'preserve': ['衣装'], 'questions': []}, ensure_ascii=False)
            else:
                text = json.dumps(EMPTY)
        else:
            text = json.dumps(EMPTY)
        return {
            'status': {'completed': True, 'status_str': 'success'},
            'outputs': {'3': {'text': [text]}},
        }

    async def free(self) -> None:
        self.freed += 1


def _payload_from_prompt(prompt: str) -> dict:
    _, after = prompt.split('入力:\n', 1)
    if '\n観察:\n' in after:
        blob, _ = after.split('\n観察:\n', 1)
    else:
        blob, _ = after.split('\n' + SCHEMA_LEAD, 1)
    return json.loads(blob)


class IntentCliTests(unittest.TestCase):
    def test_missing_comfy_is_an_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, 'Comfyが渡されていない'):
            asyncio.run(execute(EMPTY, [], comfy=None))

    def test_busy_gpu_is_an_error(self) -> None:
        comfy = FakeComfy()
        comfy.queue_running = [{'prompt_id': 'busy'}]
        with self.assertRaisesRegex(RuntimeError, 'GPUが生成中なので解釈を始められない'):
            asyncio.run(execute(EMPTY, [], comfy=comfy))
        self.assertEqual(comfy.freed, 0)

    def test_text_only_reclaims_then_unloads(self) -> None:
        comfy = FakeComfy()
        result = asyncio.run(execute(EMPTY, [], comfy=comfy))
        graph = comfy.queued[0]
        self.assertEqual(comfy.freed, 1)
        self.assertEqual(comfy.keeps, [False])
        self.assertNotIn('1', graph)
        self.assertIn('2', graph)
        self.assertNotIn('video', graph['2']['inputs'])
        self.assertEqual(result['model'], MODEL)
        self.assertEqual(result['auth'], AUTH)
        self.assertIsInstance(result['proposal'], dict)
        self.assertEqual(result['proposal']['training_samples'], None)

    def test_keep_loaded_skips_reclaim(self) -> None:
        comfy = FakeComfy()
        asyncio.run(execute(EMPTY, [], comfy=comfy, keep_model_loaded=True, reclaim_memory=False))
        self.assertEqual(comfy.freed, 0)
        self.assertEqual(comfy.keeps, [True])

    def test_two_images_observe_then_compose_without_video(self) -> None:
        comfy = FakeComfy()
        result = asyncio.run(execute(
            EMPTY, [b'one', b'two'], comfy=comfy, keep_model_loaded=False, reclaim_memory=True))
        self.assertEqual(comfy.freed, 1)
        self.assertEqual(comfy.keeps, [True, True, False])
        self.assertEqual(len(comfy.queued), 3)
        self.assertEqual(comfy.queued[0]['1']['inputs']['image'], 'intent-0.png')
        self.assertNotIn('video', comfy.queued[0]['2']['inputs'])
        self.assertNotIn('1', comfy.queued[2])
        self.assertIn('赤いリボン', comfy.prompts[2])
        self.assertIn('観察:', comfy.prompts[2])
        self.assertNotIn('赤いリボン', json.dumps(_payload_from_prompt(comfy.prompts[2]), ensure_ascii=False))
        self.assertIsInstance(result['proposal'], dict)

    def test_invalid_json_is_an_error(self) -> None:
        class Broken(FakeComfy):
            async def history(self, prompt_id: str) -> dict:
                return {
                    'status': {'completed': True, 'status_str': 'success'},
                    'outputs': {'3': {'text': ['not-json']}},
                }

        with self.assertRaisesRegex(RuntimeError, '解釈の応答をJSONとして読めません'):
            asyncio.run(execute(EMPTY, [], comfy=Broken()))

    def test_schema_mismatch_is_an_error(self) -> None:
        class Mismatch(FakeComfy):
            async def history(self, prompt_id: str) -> dict:
                return {
                    'status': {'completed': True, 'status_str': 'success'},
                    'outputs': {'3': {'text': ['{"unexpected": true}']}},
                }

        with self.assertRaisesRegex(RuntimeError, '解釈のJSONがスキーマに合いません'):
            asyncio.run(execute(EMPTY, [], comfy=Mismatch()))


class IntentRunnerTests(unittest.TestCase):
    def test_preview_review_sends_recorded_review_input(self) -> None:
        comfy = FakeComfy()
        review_input = {
            'stage': 'preview_review',
            'rating': 'NG',
            'comment': '袖が違う',
            'focus': {'kind': 'whole'},
        }
        result = asyncio.run(interpret({
            'stage': 'preview_review',
            'review_input': review_input,
        }, [], comfy=comfy))
        self.assertEqual(_payload_from_prompt(comfy.prompts[-1]), review_input)
        self.assertEqual(result['preserve'], ['衣装'])

    def test_app_runner_transfers_recorded_stage_conditions(self) -> None:
        comfy = FakeComfy()
        conditions = [{'text': 'リボンを残す', 'scope': 'character'}]
        asyncio.run(interpret({
            'original_comment': '',
            'record_description': '',
            'existing_settings': {},
            'references': [],
            'image_comments': [],
            'base_conditions': {},
            'stage': 'character',
            'panel': '',
            'record_kind': 'character',
            'stage_conditions': conditions,
        }, [], comfy=comfy))
        payload = _payload_from_prompt(comfy.prompts[-1])
        self.assertEqual(payload['stage_conditions'], conditions)
        self.assertNotIn('working_layout', payload)
        self.assertNotIn('recorded_layout', payload)
