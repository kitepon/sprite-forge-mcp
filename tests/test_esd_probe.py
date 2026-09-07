import argparse
import asyncio
import importlib.util
import json
import pytest
from pathlib import Path
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location('esd_probe',
    Path(__file__).resolve().parents[1] / 'evidence/preview-feedback-20260906/probe_esd.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('single_concept', [False, True])
def test_esd_uses_only_text_configuration_and_preserves_generation_conditions(tmp_path, monkeypatch, single_concept):
    monkeypatch.chdir(tmp_path)
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'input': {'model': 'anima', 'qwen3': 'qwen', 'lora': 'original.safetensors',
        'strength': .8, 'prompt': 'character', 'negative': 'text', 'seed': 37, 'pairs': [['ok.png', 'ng.png']]}}))
    transfers, commands, graphs = [], [], []

    async def process(*command, **kwargs):
        commands.append(command)
        async def wait():
            return 0
        return SimpleNamespace(wait=wait)

    async def copy_to(local, destination):
        transfers.append(str(local))
        return 0, ''

    async def copy_from(remote, local):
        local.write_text(json.dumps({'reference_unchanged': True}))
        return 0, ''

    class Service:
        def __init__(self, **kwargs):
            self.root = kwargs['generated_root']
            self.root.mkdir(exist_ok=True)
            self.comfy = SimpleNamespace(client=SimpleNamespace(post=self.post), base_url='test', close=self.close)

        async def post(self, *args, **kwargs):
            return SimpleNamespace(raise_for_status=lambda: None)

        async def close(self):
            pass

        async def _run_edit(self, job, graph):
            graphs.append(graph)
            return b'image', .1

        def _write_generated(self, name, content):
            path = self.root / name
            path.write_bytes(content)
            return path

    monkeypatch.setattr(probe, 'Services', Service)
    monkeypatch.setattr(probe.asyncio, 'create_subprocess_exec', process)
    monkeypatch.setattr(probe.box, 'copy_to_box', copy_to)
    monkeypatch.setattr(probe.box, 'copy_from_box', copy_from)
    args = argparse.Namespace(output=tmp_path / '.cache' / 'esd', baseline=baseline, phase='preflight', preflight_review=None)
    if single_concept:
        args.concept_file = tmp_path / 'concept.txt'
        args.concept_file.write_text('short hair, long hair, ahoge')
    asyncio.run(probe.main(args))
    assert len(graphs) == 4
    assert not commands
    args.phase, args.preflight_review = 'train', '対象髪型の一致を確認'
    asyncio.run(probe.main(args))
    report = json.loads((args.output / 'report.json').read_text())
    assert len(report['pictures']) == 28
    assert len(transfers) == 3
    assert not any(path.endswith('.png') for path in transfers)
    assert 'pairs' not in report['input'] and 'masks' not in report['input']
    assert 'feature_weights' not in report['input']
    assert report['input']['steps'] == 20
    if single_concept:
        assert report['input']['erase_concept'] == 'short hair, long hair, ahoge'
    assert all(graph['20']['inputs']['text'] == 'character' for graph in graphs[4:])
    assert all(graph['21']['inputs']['text'] == 'text' for graph in graphs[4:])
    assert len([command for command in commands if any('esd_train.py' in arg for arg in command)]) == 1
    asyncio.run(probe.main(args))
    assert len(graphs) == 28 and len(transfers) == 3
