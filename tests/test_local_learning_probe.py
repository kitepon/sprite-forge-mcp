import argparse
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location('local_learning_probe',
    Path(__file__).resolve().parents[1] / 'evidence/preview-feedback-20260906/probe_local_learning.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_approved_pair_three_conditions_and_resume_without_retraining(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    approval = tmp_path / '.cache' / 'approved'
    approval.mkdir(parents=True)
    for filename in ('raw.png', 'source.png', 'mask.png'):
        (approval / filename).write_bytes(filename.encode())
    pair = {key: {'path': filename, 'sha256': hashlib.sha256((approval / filename).read_bytes()).hexdigest()}
            for key, filename in (('preferred', 'raw.png'), ('rejected', 'source.png'))}
    (approval / 'approved-pair.json').write_text(json.dumps({'pair': pair, 'user_approval': {'comment': '正しい'}}))
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'input': {'lora': 'original.safetensors', 'strength': .8, 'prompt': 'character', 'negative': ''}}))
    commands, transfers, generations = [], [], []

    async def process(*command, **kwargs):
        commands.append(command)
        async def wait():
            return 0
        return SimpleNamespace(wait=wait)

    async def copy_to(local, remote):
        transfers.append(str(local))
        return 0, ''

    async def copy_from(remote, local):
        local.write_text(json.dumps({'reference_unchanged': True}))
        return 0, ''

    class Service:
        def __init__(self, **kwargs):
            self.root = kwargs['generated_root']
            self.root.mkdir()
            self.comfy = SimpleNamespace(client=SimpleNamespace(post=self.post), base_url='http://test', close=self.close)

        async def post(self, *args, **kwargs):
            return SimpleNamespace(raise_for_status=lambda: None)

        async def close(self):
            pass

        async def _run_edit(self, job_id, graph):
            generations.append(graph)
            return b'image', .1

        def _write_generated(self, name, content):
            path = self.root / name
            path.write_bytes(content)
            return path

    monkeypatch.setattr(probe, 'Services', Service)
    monkeypatch.setattr(probe.asyncio, 'create_subprocess_exec', process)
    monkeypatch.setattr(probe.box, 'copy_to_box', copy_to)
    monkeypatch.setattr(probe.box, 'copy_from_box', copy_from)
    args = argparse.Namespace(output=tmp_path / '.cache' / 'experiment', approval=approval,
                              baseline=baseline, resume=False, recover_trained=None, steps=20, seed=101)
    asyncio.run(probe.main(args))
    report = json.loads((args.output / 'report.json').read_text())
    assert all(len(row['pictures']) == 10 for row in report['conditions'].values())
    assert len(generations) == 30
    assert len([command for command in commands if '--objective' in command]) == 2
    assert not any('candidate.png' in path for path in transfers)
    args.resume = True
    monkeypatch.setattr(Service, '__init__', lambda self, **kwargs: setattr(self, 'comfy', SimpleNamespace(close=self.close)))
    asyncio.run(probe.main(args))
    assert len(generations) == 30
    assert len([command for command in commands if '--objective' in command]) == 2
