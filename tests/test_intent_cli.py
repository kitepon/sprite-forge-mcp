"""CLIの呼出し条件と結果境界。実モデルは呼ばない。"""
from pathlib import Path
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
        assert all(key not in env for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"))
        assert (cwd / "1.png").read_bytes() == b"image-fixture"
        assert "原文の注文" in input
        (cwd / "result.json").write_text(json.dumps({"observations": [], "changes": [], "questions": []}))
        return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed"}', stderr="")

    monkeypatch.setattr("backend.intent_cli.subprocess.run", execute)
    result = run({"input": {"original_comment": "原文の注文"}, "images": [base64.b64encode(b"image-fixture").decode()]})
    assert result["auth"] == "chatgpt"
    assert not roots[0].exists()
