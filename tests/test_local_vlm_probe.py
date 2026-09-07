import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('local_vlm', Path(__file__).resolve().parents[1] /
                                            'evidence/preview-feedback-20260906/probe_local_vlm.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_graph_uses_local_cuda_and_preserves_image_link():
    workflow = probe.graph('Qwen3-VL-4B-Instruct', '髪型を観察', 'test.png')
    assert workflow['1']['inputs']['image'] == 'test.png'
    assert workflow['2']['inputs']['image'] == ['1', 0]
    assert workflow['2']['inputs']['device'] == 'cuda:0'
    assert workflow['3']['inputs']['source'] == ['2', 0]
    summary = probe.graph('Qwen3-VL-4B-Instruct', '比較', keep=False)
    assert '1' not in summary
    assert summary['2']['inputs']['keep_model_loaded'] is False


def test_comparison_keeps_user_reason_and_unselected_status():
    prompt = probe.comparison_prompt({'per_image_reasons': {'17': '長い髪がNG'}}, [{'number': 17, 'text': '腰までの髪'}])
    assert '長い髪がNG' in prompt
    assert '腰までの髪' in prompt
    assert '未選択は未判定' in prompt
    assert '訂正しない' in prompt
    assert '全体reasonより優先する確定済みの理由' in prompt


def test_report_escapes_model_output_and_shows_all_results(tmp_path):
    probe.save(tmp_path, {'models': ['model'], 'batch': 'batch', 'status': '解析中',
                         'results': [{'model': 'model', 'number': 17, 'status': '完了', 'text': '<bad>'}]})
    html = (tmp_path / 'report.html').read_text()
    assert '候補 17' in html
    assert '&lt;bad&gt;' in html
    assert 'candidate-17.png' in html
