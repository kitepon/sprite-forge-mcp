"""正規の学習入口が選好学習を呼び、終了結果を返すことを確認する。"""
from pathlib import Path
from types import SimpleNamespace

from box import train


def test_entry_runs_preference_trainer_in_gpu_venv(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(train, 'ROOT', tmp_path)
    monkeypatch.setattr(train, 'VENV', tmp_path / 'venv')
    monkeypatch.setattr(train, '_free_comfy', lambda url: calls.append(url))
    monkeypatch.setattr(train.sys, 'argv', ['train.py', '--preference-config', str(tmp_path / 'input.json'),
                        '--output-name', 'new', '--output-dir', str(tmp_path / 'loras'),
                        '--max-train-steps', '1', '--learning-rate', '1e-5'])
    def execute(command, **kwargs):
        assert command[0] == str(tmp_path / 'venv' / 'Scripts' / 'python.exe')
        assert command[1] == str(tmp_path / 'preference_train.py')
        assert command[command.index('--output') + 1] == str(tmp_path / 'loras' / 'new.safetensors')
        assert '--steps' in command and command[command.index('--steps') + 1] == '1'
        return SimpleNamespace(returncode=7)
    monkeypatch.setattr(train.subprocess, 'run', execute)
    assert train.main() == 7
    assert calls == ['http://127.0.0.1:8188']
