import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location('review_batch',
    Path(__file__).resolve().parents[1] / 'evidence/preview-feedback-20260906/generate_review_batch.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_twenty_numbered_original_outputs_without_training(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'input': {'model': 'anima', 'lora': 'original.safetensors',
        'strength': .8, 'prompt': 'character', 'negative': 'text'}}))
    graphs = []

    class Service:
        def __init__(self, **kwargs):
            self.root = kwargs['generated_root']
            self.root.mkdir(exist_ok=True)
            self.comfy = SimpleNamespace(close=self.close)

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
    args = argparse.Namespace(output=tmp_path / '.cache' / 'batch', baseline=baseline)
    asyncio.run(probe.main(args))
    report = json.loads((args.output / 'report.json').read_text())
    assert [item['number'] for item in report['pictures']] == list(range(1, 21))
    assert [item['seed'] for item in report['pictures']] == list(range(501, 521))
    assert report['training_started'] is False
    assert all(graph['4']['inputs']['lora_name'] == 'original.safetensors' for graph in graphs)
    assert all(graph['20']['inputs']['text'] == 'character' for graph in graphs)
    assert (args.output / 'report.html').read_text().count('<img ') == 20
    asyncio.run(probe.main(args))
    assert len(graphs) == 20
