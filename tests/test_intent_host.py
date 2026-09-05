"""SSH接続の許可は解釈コマンドに限定し、他用途の登録を保持する。"""
from pathlib import Path

import pytest

from scripts.configure_intent_host import authorized_text


def test_host_entry_restricts_command_and_preserves_other_keys():
    before = "# 既存設定\nssh-ed25519 other-key owner\n"
    result = authorized_text(before, "ssh-ed25519 fixture-key app", Path("/app/with space"), "/usr/bin/uv")
    assert result.startswith(before)
    assert 'restrict,command="cd \'/app/with space\' && exec /usr/bin/uv run --no-sync python -m backend.intent_cli"' in result
    assert result.endswith("ssh-ed25519 fixture-key sprite-forge-intent\n")
    assert authorized_text(result, "ssh-ed25519 fixture-key app", Path("/app/with space"), "/usr/bin/uv") == result


def test_host_entry_updates_only_its_own_registration():
    first = authorized_text("ssh-ed25519 other-key owner\n", "ssh-ed25519 fixture-key app", Path("/probe"), "uv")
    updated = authorized_text(first, "ssh-ed25519 fixture-key app", Path("/production"), "uv")
    assert "cd /production" in updated
    assert "/probe" not in updated
    assert updated.count("fixture-key") == 1
    with pytest.raises(ValueError, match="別用途"):
        authorized_text("ssh-ed25519 fixture-key owner\n", "ssh-ed25519 fixture-key app", Path("/app"), "uv")
