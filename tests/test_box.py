from __future__ import annotations

import asyncio
from pathlib import Path

from backend import box


class _Process:
    returncode = 0

    async def communicate(self):
        return b"ok", b""


def test_training_command_is_argument_vector_without_shell(monkeypatch):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(box.run_training(
        r"C:\\sf\\dataset.toml", "fire_mage", "base.safetensors", "text.safetensors",
        "vae.safetensors", 12, ssh="kite_@fox", train=r"C:\\sf\\train.py"))

    command, kwargs = calls[0]
    assert result == (0, "ok", "")
    assert command[:6] == ("ssh", "-o", "ConnectTimeout=20", "kite_@fox", "py", "-3.13")
    assert "--mixed-precision" in command and command[command.index("--mixed-precision") + 1] == "bf16"
    assert all(";" not in part and "powershell" not in part.lower() for part in command)
    assert kwargs["stdout"] is asyncio.subprocess.PIPE


def test_copy_to_box_uses_scp_argument_vector(monkeypatch, tmp_path):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    local = tmp_path / "dataset.toml"
    local.write_text("[general]\n", encoding="utf-8")

    result = asyncio.run(box.copy_to_box(local, r"C:\\sf\\dataset.toml", ssh="kite_@fox"))

    assert result == (0, "ok")
    assert calls[0][0] == ("scp", str(local), r"kite_@fox:C:\\sf\\dataset.toml")
