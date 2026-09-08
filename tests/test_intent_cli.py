from __future__ import annotations

import asyncio
import json
import unittest
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from backend.intent_cli import (
    AUTH, INTERPRET_MAX_SIDE, MODEL, OBSERVE_MARK, _keep_region_pixels, execute, observe_range,
)
from backend.intent_runner import interpret

SCHEMA_LEAD = '出力は次の JSON Schema に厳密に従い、前後に説明を付けないでください。'
EMPTY = {
    'observations': [],
    'changes': [],
    'questions': [],
    'training_samples': None,
}


def _is_sam(workflow: dict) -> bool:
    return any(isinstance(node, dict) and node.get('class_type') == 'SAM3_Detect' for node in workflow.values())


def _mask_png(color: str) -> bytes:
    image = Image.new('RGB', (8, 8), color)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


class FakeComfy:
    def __init__(self, mask_png: bytes | None = None) -> None:
        self.prompts: list[str] = []
        self.keeps: list[bool] = []
        self.queued: list[dict] = []
        self.freed = 0
        self.queue_running: list = []
        self.queue_pending: list = []
        self.uploads: list[bytes] = []
        self.views: list[dict] = []
        self.mask_png = mask_png
        self._n = 0

    async def queue(self) -> dict:
        return {'queue_running': self.queue_running, 'queue_pending': self.queue_pending}

    async def upload(self, content: bytes, name: str) -> str:
        self.uploads.append(content)
        return name

    async def submit(self, workflow: dict, client_id: str) -> str:
        self._n += 1
        prompt_id = f'p{self._n}'
        self.queued.append(workflow)
        if _is_sam(workflow):
            return prompt_id
        qwen = workflow['2']['inputs']
        self.prompts.append(str(qwen['custom_prompt']))
        self.keeps.append(bool(qwen['keep_model_loaded']))
        return prompt_id

    async def view(self, image: dict) -> bytes:
        self.views.append(image)
        return self.mask_png if self.mask_png is not None else _mask_png('white')

    async def history(self, prompt_id: str) -> dict:
        workflow = self.queued[int(prompt_id[1:]) - 1]
        if _is_sam(workflow):
            return {
                'status': {'completed': True, 'status_str': 'success'},
                'outputs': {'6': {'images': [{'filename': 'mask.png', 'subfolder': '', 'type': 'output'}]}},
            }
        prompt = str(workflow['2']['inputs']['custom_prompt'])
        if OBSERVE_MARK in prompt:
            text = json.dumps({
                'appearance_ja': '赤いリボンの少女',
                'caption_en': 'a girl with a red ribbon',
            }, ensure_ascii=False)
        elif '入力:\n' in prompt:
            payload = _payload_from_prompt(prompt)
            stage = payload.get('stage')
            if stage == 'layout':
                # 差分契約: 先頭項目だけ名称を変えて返し、他は省略する。
                first = payload['sheet_layout'][0]
                text = json.dumps({
                    'summary_ja': '構成の確認',
                    'questions': [],
                    'panels': [dict(first, label=first['label'] + '（変更）', description_ja='名称を変更', reference=None)],
                    'removed_keys': [],
                }, ensure_ascii=False)
            elif stage == 'preview_review':
                text = json.dumps({'fix': [], 'preserve': ['衣装'], 'questions': [], 'description_en': ''}, ensure_ascii=False)
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


def _png(size: tuple[int, int], color: str = 'red') -> bytes:
    image = Image.new('RGB', size, color)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


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
            EMPTY, [_png((24, 32), 'red'), _png((24, 32), 'blue')],
            comfy=comfy, keep_model_loaded=False, reclaim_memory=True))
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

    def test_large_image_is_shrunk_before_upload(self) -> None:
        comfy = FakeComfy()
        asyncio.run(execute(EMPTY, [_png((800, 600))], comfy=comfy))
        uploaded = Image.open(BytesIO(comfy.uploads[0]))
        self.assertEqual(uploaded.size, (512, 384))
        self.assertLessEqual(max(uploaded.size), INTERPRET_MAX_SIDE)

    def test_small_image_is_not_enlarged(self) -> None:
        comfy = FakeComfy()
        asyncio.run(execute(EMPTY, [_png((24, 32))], comfy=comfy))
        uploaded = Image.open(BytesIO(comfy.uploads[0]))
        self.assertEqual(uploaded.size, (24, 32))

    def test_invalid_image_is_an_error(self) -> None:
        comfy = FakeComfy()
        with self.assertRaises(UnidentifiedImageError):
            asyncio.run(execute(EMPTY, [b'not-an-image'], comfy=comfy))
        self.assertEqual(comfy.uploads, [])


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
        payload = _payload_from_prompt(comfy.prompts[-1])
        self.assertEqual({key: payload[key] for key in review_input}, review_input)
        self.assertEqual(payload['observe_range'], {
            'regions': [],
            'topics': [],
            'comment': '袖が違う',
            'intent': 'fix',
        })
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


class PreviewReviewRangeTests(unittest.TestCase):
    def test_observe_range_from_focus_and_comment(self) -> None:
        self.assertEqual(observe_range({'focus': ['hair'], 'comment': ''}), {
            'regions': ['hair'], 'topics': ['hair'], 'comment': '', 'intent': 'fix',
        })
        self.assertEqual(observe_range({'focus': ['style'], 'comment': ''}), {
            'regions': [], 'topics': ['style'], 'comment': '', 'intent': 'fix',
        })
        self.assertEqual(observe_range({'focus': ['hair', 'style'], 'comment': ''}), {
            'regions': ['hair'], 'topics': ['hair', 'style'], 'comment': '', 'intent': 'fix',
        })
        self.assertEqual(observe_range({'focus': [], 'comment': '髪型が違う'}), {
            'regions': ['hair'], 'topics': ['hair'], 'comment': '髪型が違う', 'intent': 'fix',
        })
        self.assertEqual(observe_range({'focus': ['hair'], 'comment': '顔も違う'}), {
            'regions': ['hair'], 'topics': ['hair'], 'comment': '顔も違う', 'intent': 'fix',
        })
        self.assertEqual(observe_range({'focus': {'kind': 'whole'}, 'comment': '袖が違う'}), {
            'regions': [], 'topics': [], 'comment': '袖が違う', 'intent': 'fix',
        })
        self.assertEqual(observe_range({'rating': 'ok', 'focus': ['hair'], 'comment': ''}), {
            'regions': ['hair'], 'topics': ['hair'], 'comment': '', 'intent': 'preserve',
        })

    def test_keep_region_pixels_blacks_out_outside_mask(self) -> None:
        source = _png((4, 2), 'red')
        mask = Image.new('L', (4, 2), 0)
        mask.putpixel((0, 0), 255)
        mask.putpixel((0, 1), 255)
        output = BytesIO()
        mask.save(output, format='PNG')
        result = Image.open(BytesIO(_keep_region_pixels(source, output.getvalue()))).convert('RGB')
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(result.getpixel((3, 0)), (0, 0, 0))

    def test_preview_review_masks_hair_before_observe(self) -> None:
        comfy = FakeComfy()
        asyncio.run(execute({
            'stage': 'preview_review',
            'rating': 'NG',
            'comment': '',
            'focus': ['hair'],
        }, [_png((24, 32), 'red'), _png((24, 32), 'blue')], comfy=comfy))
        self.assertTrue(all(_is_sam(workflow) for workflow in comfy.queued[:2]))
        self.assertTrue(all(not _is_sam(workflow) for workflow in comfy.queued[2:]))
        self.assertEqual(comfy.queued[0]['2']['inputs']['text'], 'hair')
        self.assertIn('見る範囲は髪', comfy.prompts[0])
        self.assertIn('見る範囲は髪', comfy.prompts[1])
        self.assertNotIn('顔', comfy.prompts[0])
        payload = _payload_from_prompt(comfy.prompts[-1])
        self.assertEqual(payload['observe_range']['regions'], ['hair'])
        self.assertEqual(payload['focus'], ['hair'])

    def test_preview_review_comment_words_mask_when_focus_empty(self) -> None:
        comfy = FakeComfy()
        asyncio.run(execute({
            'stage': 'preview_review',
            'rating': 'NG',
            'comment': '髪型が違う',
            'focus': [],
        }, [_png((24, 32), 'red'), _png((24, 32), 'blue')], comfy=comfy))
        self.assertEqual(comfy.queued[0]['2']['inputs']['text'], 'hair')
        self.assertIn('ユーザーの文: 髪型が違う', comfy.prompts[0])
        self.assertEqual(_payload_from_prompt(comfy.prompts[-1])['observe_range']['regions'], ['hair'])

    def test_preview_review_style_does_not_call_sam(self) -> None:
        comfy = FakeComfy()
        asyncio.run(execute({
            'stage': 'preview_review',
            'rating': 'NG',
            'comment': '',
            'focus': ['style'],
        }, [_png((24, 32), 'red'), _png((24, 32), 'blue')], comfy=comfy))
        self.assertFalse(any(_is_sam(workflow) for workflow in comfy.queued))
        self.assertIn('見る範囲は画風', comfy.prompts[0])
        self.assertEqual(_payload_from_prompt(comfy.prompts[-1])['observe_range']['topics'], ['style'])

    def test_ok_focus_observes_as_preserve_not_fix(self) -> None:
        comfy = FakeComfy()
        asyncio.run(execute({
            'stage': 'preview_review',
            'rating': 'ok',
            'comment': '',
            'focus': ['hair'],
        }, [_png((24, 32), 'red'), _png((24, 32), 'blue')], comfy=comfy))
        self.assertIn('残したい範囲は髪', comfy.prompts[0])
        self.assertNotIn('見る範囲は髪', comfy.prompts[0])
        self.assertIn('直す内容は書かないでください', comfy.prompts[0])
        payload = _payload_from_prompt(comfy.prompts[-1])
        self.assertEqual(payload['observe_range']['intent'], 'preserve')
        self.assertEqual(payload['observe_range']['regions'], ['hair'])

    def test_empty_region_mask_is_an_error(self) -> None:
        comfy = FakeComfy(mask_png=_mask_png('black'))
        with self.assertRaisesRegex(RuntimeError, 'マスクが空です: hair'):
            asyncio.run(execute({
                'stage': 'preview_review',
                'rating': 'NG',
                'comment': '',
                'focus': ['hair'],
            }, [_png((24, 32))], comfy=comfy))
        self.assertTrue(_is_sam(comfy.queued[0]))
        self.assertEqual(comfy.prompts, [])
