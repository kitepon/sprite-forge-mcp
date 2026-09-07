import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('contrast', Path(__file__).resolve().parents[1] / 'evidence/preview-feedback-20260906/extract_hairstyle_contrast.py')
contrast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contrast)


def test_single_ng_feature_survives_and_all_scoped_tags_remain(tmp_path):
    scores = [{tag: .01 for tag in contrast.HAIRSTYLES} for _ in range(20)]
    scores[16]['long_hair'] = .9
    scores[0]['ahoge'] = .95
    scores[3]['twintails'] = .8
    for item in scores:
        item['pink_hair'] = 1
        item['chair'] = 1
    result = contrast.extract({'selection': {'selected_ng_numbers': [1, 17]}, 'output': {'scores': scores}})
    mapped = {row['tag']: row for row in result['rows']}
    assert len(mapped) == len(contrast.HAIRSTYLES) == len(set(contrast.HAIRSTYLES))
    assert 'pink_hair' not in mapped and 'chair' not in mapped
    assert mapped['long_hair']['exceeding_ng_numbers'] == [17]
    assert mapped['twintails']['individual_excess'] < 0
    assert result['rows'][0]['tag'] == 'ahoge'
    contrast.save(tmp_path, result)
    weights = json.loads((tmp_path / 'weights.json').read_text())
    assert weights['normalized'] is False
    assert weights['margin'] == 0
    actual = {image['number']: {item['tag']: item['weight'] for item in image['features']} for image in weights['images']}
    assert actual[17] == {'long_hair': .9 - .01}
    assert actual[1] == {'ahoge': .95 - .01}
    assert '画像別の学習重みJSON' in (tmp_path / 'report.html').read_text()
