import argparse
import asyncio
import importlib.util
import json
from pathlib import Path

from PIL import Image
import pytest


spec = importlib.util.spec_from_file_location(
    'correction_pair_probe',
    Path(__file__).resolve().parents[1] / 'evidence/preview-feedback-20260906/probe_correction_pair.py',
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('empty_mask', [False, True])
def test_probe_preserves_source_and_never_approves(tmp_path, monkeypatch, empty_mask):
    source = tmp_path / 'source.png'
    reference = tmp_path / 'reference.png'
    raw = tmp_path / 'raw.png'
    mask_path = tmp_path / 'mask.png'
    Image.new('RGB', (4, 4), 'white').save(source)
    Image.new('RGB', (4, 4), 'blue').save(reference)
    Image.new('RGB', (4, 4), 'red').save(raw)
    mask = Image.new('L', (4, 4))
    if not empty_mask:
        mask.putpixel((1, 1), 255)
    mask.save(mask_path)
    original = source.read_bytes()

    async def upload(self, content, name):
        return name

    async def edit(self, job_id, graph):
        return raw.read_bytes(), 0.1

    async def make_mask(self, image_id, prompt):
        return {'path': str(mask_path)}

    monkeypatch.setattr(probe.Services, '_run_edit', edit)
    monkeypatch.setattr(probe.Services, 'make_mask', make_mask)
    from backend.comfy import Comfy
    monkeypatch.setattr(Comfy, 'upload', upload)
    args = argparse.Namespace(source=source, reference=reference, output=tmp_path / 'result',
                              comment='髪型が違う', prompt='髪を修正', mask_prompt='hair', seed=1)
    if empty_mask:
        with pytest.raises(ValueError, match='検出できません'):
            asyncio.run(probe.main(args))
    else:
        asyncio.run(probe.main(args))
        with Image.open(args.output / 'candidate.png') as result:
            assert result.getpixel((0, 0)) == (255, 255, 255, 255)
            assert result.getpixel((1, 1)) == (255, 0, 0, 255)
    record = json.loads((args.output / 'result.json').read_text())
    assert record['user_approval'] is None
    assert record['status'] == ('処理失敗' if empty_mask else '候補生成済み・本人の確認待ち')
    if not empty_mask:
        assert record['measurements']['outside_mask_changed_pixels'] == 0
    assert source.read_bytes() == original
    assert '未承認' in (args.output / 'report.html').read_text()
    if not empty_mask:
        async def forbidden_edit(*unused):
            raise AssertionError('範囲の修正で画像を再生成してはいけません')

        monkeypatch.setattr(probe.Services, '_run_edit', forbidden_edit)
        args.remask = True
        args.mask_padding = 1
        asyncio.run(probe.main(args))
        assert len(list((args.output / 'attempts').iterdir())) == 1
        with Image.open(args.output / 'candidate.png') as result:
            assert result.getpixel((0, 0)) == (255, 0, 0, 255)
            assert result.getpixel((3, 3)) == (255, 255, 255, 255)
        assert source.read_bytes() == original
        raw_bytes = (args.output / 'raw.png').read_bytes()
        probe.approve_generated(args.output, '正しく修正できている')
        accepted = json.loads((args.output / 'approved-pair.json').read_text())
        assert accepted['pair']['preferred']['path'] == 'raw.png'
        assert accepted['pair']['rejected']['path'] == 'source.png'
        assert accepted['training_started'] is False
        assert accepted['user_approval']['comment'] == '正しく修正できている'
        assert (args.output / 'raw.png').read_bytes() == raw_bytes
        report = (args.output / 'report.html').read_text()
        assert '生成した修正候補・本人承認済み' in report
        assert '過去の合成実験（不採用）' in report
