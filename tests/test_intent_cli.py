"""CLIの呼出し条件と結果境界。実モデルは呼ばない。"""
import asyncio
import base64
import json

import pytest

from backend.intent_cli import AUTH, MODEL, execute, parse_json_object, prompt_for, schema_for
from backend.intent import Proposal
from backend.sheet_layout import LayoutProposal
from backend import workflows


class FakeComfy:
    def __init__(self, text, *, error=None, missing=False, busy=False):
        self.texts = list(text) if isinstance(text, list) else [text]
        self.cursor = 0
        self.error = error
        self.missing = missing
        self.busy = busy
        self.uploaded = []
        self.submitted = []
        self.freed = 0

    async def upload(self, content, name):
        self.uploaded.append((name, content))
        return name

    async def submit(self, workflow, client_id):
        self.submitted.append((workflow, client_id))
        return f"prompt-{len(self.submitted)}"

    async def history(self, prompt_id):
        if self.missing:
            return {}
        if self.error:
            return {"status": {"completed": False, "status_str": "error", "messages": self.error}}
        text = self.texts[min(self.cursor, len(self.texts) - 1)]
        self.cursor += 1
        return {"status": {"completed": True, "status_str": "success"},
                "outputs": {"3": {"text": [text]}}}

    async def queue(self):
        if self.busy:
            return {"queue_running": [[0, "other"]], "queue_pending": []}
        return {"queue_running": [], "queue_pending": []}

    async def free(self):
        self.freed += 1

    async def close(self):
        return None


def test_prompt_requires_full_schema_and_instruction_text():
    schema = schema_for(Proposal)
    observation = schema["$defs"]["Observation"]
    assert set(observation["required"]) == set(observation["properties"])
    assert "default" not in observation["properties"]["caption_en"]
    prompt = prompt_for({"input": {"original_comment": "原文の注文", "stage": "preview"}, "images": ["x"]})
    assert "原文の注文" in prompt
    assert "JSONオブジェクトだけ" in prompt
    assert "1枚の静止画" in prompt
    assert "フレーム" not in prompt


def test_layout_prompt_uses_layout_schema_and_instructions():
    prompt = prompt_for({"input": {"stage": "layout", "sheet_layout": []}, "images": []})
    schema = schema_for(LayoutProposal)
    assert "汎用キャラクターシート" in prompt
    assert "一枠に実際に描く被写体数・視点・範囲" in prompt
    assert "panels" in schema["properties"] and "changes" not in schema["properties"]
    assert "この入力に画像はありません" in prompt


def test_parse_json_object_accepts_fence_and_rejects_empty():
    assert parse_json_object('```json\n{"fix": [], "preserve": [], "questions": []}\n```') == {
        "fix": [], "preserve": [], "questions": []}
    with pytest.raises(RuntimeError, match="空"):
        parse_json_object("  ")
    with pytest.raises(RuntimeError, match="JSON"):
        parse_json_object("解釈できません")


def test_execute_uploads_one_still_image_and_reads_text():
    comfy = FakeComfy('{"observations": [], "changes": [], "questions": []}')
    result = asyncio.run(execute(
        {"input": {"original_comment": "原文の注文", "stage": "preview"},
         "images": [base64.b64encode(b"image-fixture").decode()]}, comfy))
    assert result["auth"] == AUTH and result["model"] == MODEL
    assert comfy.uploaded[0][1] == b"image-fixture"
    assert comfy.freed == 1
    graph = comfy.submitted[0][0]
    assert graph["2"]["class_type"] == "AILab_QwenVL_Advanced"
    assert graph["2"]["inputs"]["model_name"] == MODEL
    assert graph["2"]["inputs"]["quantization"] == "8-bit (Balanced)"
    assert graph["2"]["inputs"]["keep_model_loaded"] is False
    assert "video" not in graph["2"]["inputs"]
    assert graph["1"]["inputs"]["image"] == comfy.uploaded[0][0]
    assert "原文の注文" in graph["2"]["inputs"]["custom_prompt"]


def test_execute_observes_each_still_image_then_composes():
    comfy = FakeComfy([
        '{"index": 1, "appearance_ja": "銀髪の人物"}',
        '{"index": 2, "appearance_ja": "参考の全身"}',
        '{"observations": [], "changes": [], "questions": []}',
    ])
    result = asyncio.run(execute(
        {"input": {"original_comment": "原文の注文", "stage": "preview"},
         "images": [base64.b64encode(b"one").decode(), base64.b64encode(b"two").decode()]}, comfy))
    assert result["proposal"]["questions"] == []
    assert len(comfy.submitted) == 3
    first, second, last = (item[0] for item in comfy.submitted)
    assert first["1"]["inputs"]["image"] == comfy.uploaded[0][0]
    assert second["1"]["inputs"]["image"] == comfy.uploaded[1][0]
    assert "video" not in first["2"]["inputs"] and "video" not in last["2"]["inputs"]
    assert "1" not in last
    assert first["2"]["inputs"]["keep_model_loaded"] is True
    assert last["2"]["inputs"]["keep_model_loaded"] is False
    assert "observations" in last["2"]["inputs"]["custom_prompt"]


def test_execute_surfaces_comfy_error():
    comfy = FakeComfy("", error=[["execution_error", {"exception_message": "model missing"}]])
    with pytest.raises(RuntimeError, match="解釈に失敗"):
        asyncio.run(execute({"input": {"stage": "preview_review"}, "images": []}, comfy))


def test_execute_skips_free_while_queue_busy():
    comfy = FakeComfy('{"fix": [], "preserve": [], "questions": []}', busy=True)
    asyncio.run(execute({"input": {"stage": "preview_review"}, "images": []}, comfy))
    assert comfy.freed == 0


@pytest.mark.parametrize("has_snapshot", [True, False])
def test_app_runner_transfers_recorded_stage_conditions(monkeypatch, has_snapshot):
    from backend.intent_runner import interpret

    recorded = {"pose": {"description_en": "standing, front view", "avoid_en": ""}}
    job = {"original_comment": "横向き", "record_description": "", "existing_settings": {},
           "references": [], "image_comments": [], "base_conditions": {}, "stage": "preview", "panel": "", "record_kind": "character"}
    if has_snapshot:
        job["stage_conditions"] = recorded
        job["training_captions"] = [{"appearance_ja": "成人に見える人物。小さめの頭と長い手足。",
                                    "caption_en": "adult figure, small head relative to body, long limbs"}]
        job["available_styles"] = [{"name": "確認用", "note": "登録された画風", "lora_name": "look.safetensors"}]

    async def execute_packet(packet, comfy):
        assert packet["input"]["stage_conditions"] == (recorded if has_snapshot else {})
        assert packet["input"]["record_kind"] == "character"
        assert packet["input"]["available_styles"] == job.get("available_styles", [])
        assert packet["input"]["training_captions"] == job.get("training_captions", [])
        return {"proposal": {"observations": [], "changes": [], "questions": []},
                "model": "fixture", "elapsed_seconds": 0, "auth": AUTH}

    monkeypatch.setattr("backend.intent_runner.execute", execute_packet)
    assert asyncio.run(interpret(job, [], FakeComfy("unused")))["questions"] == []
    assert job["interpreter"] == {"model": "fixture", "elapsed_seconds": 0, "auth": AUTH}


def test_runner_ignores_intent_ssh_and_uses_comfy(monkeypatch):
    from backend.intent_runner import interpret
    monkeypatch.setenv("SPRITEFORGE_INTENT_SSH", "app@cli-host")
    monkeypatch.setenv("SPRITEFORGE_INTENT_HOST_ROOT", "/project with space")
    job = {"original_comment": "参照画像の衣装", "record_description": "", "existing_settings": {},
           "references": [], "image_comments": [], "base_conditions": {}, "stage": "samples",
           "panel": "", "record_kind": "character"}
    comfy = FakeComfy('{"observations": [], "changes": [], "questions": [], "training_samples": []}')
    result = asyncio.run(interpret(job, [b"reference"], comfy))
    assert result["questions"] == []
    assert comfy.uploaded[0][1] == b"reference"
    assert job["interpreter"]["auth"] == AUTH


def test_qwen_vl_graph_is_one_still_image():
    graph = workflows.qwen_vl_interpret("prompt", "one.png", model=MODEL)
    assert graph["1"]["inputs"]["image"] == "one.png"
    assert graph["2"]["inputs"]["image"] == ["1", 0]
    assert "video" not in graph["2"]["inputs"]
    empty = workflows.qwen_vl_interpret("p", None, model=MODEL)
    assert "1" not in empty and "image" not in empty["2"]["inputs"]
    assert "video" not in empty["2"]["inputs"]
