import importlib.util
from pathlib import Path

from PIL import Image
from box.animetimm_node import pad_picture, SpriteAnimeTimm

spec = importlib.util.spec_from_file_location('animetimm_probe', Path(__file__).resolve().parents[1] / 'evidence/preview-feedback-20260906/probe_animetimm.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_padding_preserves_shape_and_white_margin():
    output = pad_picture(Image.new('RGB', (832, 1216), 'black'), [512, 512], 'white')
    assert output.size == (512, 512)
    assert output.getpixel((0, 256)) == (255, 255, 255)
    assert output.getpixel((256, 256)) == (0, 0, 0)


def test_graph_keeps_batch_order():
    workflow = probe.graph(['first.png', 'second.png'])
    assert workflow['4']['inputs'] == {'image1': ['1', 0], 'image2': ['3', 0]}
    assert workflow['100']['inputs']['image'] == ['4', 0]
    assert SpriteAnimeTimm.INPUT_TYPES()['required']['image'] == ('IMAGE',)


def test_report_separates_individual_reason_and_unselected(tmp_path):
    report = {'batch': 'test', 'status': '完了', 'selection': {
        'selected_ng_numbers': [1, 17], 'reason': 'ツインテールではない',
        'per_image_reasons': {'17': '長い髪の毛がNG'}},
        'output': {'scores': [{'short_hair': number / 20, 'blue_dress': 1} for number in range(20)]}}
    comparison = probe.comparisons(report)
    assert 'blue_dress' not in comparison
    assert comparison['short_hair']['候補17：長い髪の毛がNG'] == .8
    assert comparison['short_hair']['全体理由のNG'] == 0
    probe.save(tmp_path, report)
    html = (tmp_path / 'report.html').read_text()
    assert html.count('<article>') == 20
    assert '長い髪の毛がNG' in html
    assert '未選択・未判定' in html
