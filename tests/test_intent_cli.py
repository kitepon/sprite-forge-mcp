"""CLIの呼出し条件と結果境界。実モデルは呼ばない。"""
from pathlib import Path
import asyncio
import base64
import json
from types import SimpleNamespace

import pytest

from backend.intent_cli import command, check_events, run


def test_cli_uses_native_subscription_without_tools():
    args = command(Path("/tmp/probe"), [Path("/tmp/probe/1.png")])
    assert 'forced_login_method="chatgpt"' in args
    assert 'model_provider="openai"' in args
    assert "--ignore-user-config" in args and "--ephemeral" in args
    for feature in ("shell_tool", "unified_exec", "apps", "remote_plugin", "multi_agent", "image_generation", "view_image", "hooks"):
        assert args[args.index(feature) - 1] == "--disable"
    assert args[-1] == "-"


@pytest.mark.parametrize("kind", ["command_execution", "mcp_tool_call", "web_search", "file_change"])
def test_cli_rejects_tool_items(kind):
    with pytest.raises(RuntimeError, match="画像解釈以外"):
        check_events('{"type":"item.completed","item":{"type":"' + kind + '"}}')


def test_cli_requires_completion():
    with pytest.raises(RuntimeError, match="完了応答"):
        check_events('{"type":"thread.started"}')
    check_events('{"type":"item.completed","item":{"type":"agent_message"}}\n{"type":"turn.completed"}')


def test_runner_removes_api_credentials_and_uses_only_input_images(monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.setenv(key, "試験値")
    roots = []

    def execute(args, *, input, text, capture_output, cwd, env):
        roots.append(cwd)
        schema = json.loads((cwd / "schema.json").read_text())
        observation = schema["$defs"]["Observation"]
        assert set(observation["required"]) == set(observation["properties"])
        assert "default" not in observation["properties"]["caption_en"]
        assert all(key not in env for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"))
        assert (cwd / "1.png").read_bytes() == b"image-fixture"
        assert "原文の注文" in input
        (cwd / "result.json").write_text(json.dumps({"observations": [], "changes": [], "questions": []}))
        return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed"}', stderr="")

    monkeypatch.setattr("backend.intent_cli.subprocess.run", execute)
    result = run({"input": {"original_comment": "原文の注文"}, "images": [base64.b64encode(b"image-fixture").decode()]})
    assert result["auth"] == "chatgpt"
    assert not roots[0].exists()


@pytest.mark.parametrize("has_snapshot", [True, False])
def test_app_runner_transfers_recorded_stage_conditions(monkeypatch, has_snapshot):
    from backend.intent_runner import interpret

    recorded = {"pose": {"description_en": "standing, front view", "avoid_en": ""}}
    job = {"original_comment": "横向き", "record_description": "", "existing_settings": {},
           "references": [], "image_comments": [], "base_conditions": {}, "stage": "preview", "panel": ""}
    if has_snapshot:
        job["stage_conditions"] = recorded

    class Process:
        returncode = 0

        async def communicate(self, raw):
            packet = json.loads(raw)
            assert packet["input"]["stage_conditions"] == (recorded if has_snapshot else {})
            return json.dumps({"proposal": {"observations": [], "changes": [], "questions": []},
                               "model": "fixture", "elapsed_seconds": 0, "auth": "chatgpt"}).encode(), b""

    async def start(*args, **kwargs):
        return Process()

    monkeypatch.setattr("backend.intent_runner.asyncio.create_subprocess_exec", start)
    assert asyncio.run(interpret(job, []))["questions"] == []


def test_nonzero_cli_exposes_structured_error_before_generic_stderr(monkeypatch):
    monkeypatch.setattr("backend.intent_cli.subprocess.run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout='{"type":"error","message":"Invalid schema: caption_en must be required"}', stderr="Reading prompt from stdin..."))
    with pytest.raises(RuntimeError, match="Invalid schema"):
        run({"input": {}, "images": []})
