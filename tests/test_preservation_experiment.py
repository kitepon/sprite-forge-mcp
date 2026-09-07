import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'evidence/ng-preservation-20260907'
sys.path.insert(0, str(DIRECTORY))
from probe_concepts import expected_pictures
from probe_preserve import training_input


def test_experiment_covers_all_owner_ng_without_relabeling_unselected():
    config = json.loads((DIRECTORY / 'config.json').read_text())
    selection = json.loads((ROOT / config['selection_file']).read_text())
    numbers = [n for concept in config['concepts'] for n in concept['source_numbers']]
    assert sorted(numbers) == selection['selected_ng_numbers']
    assert len(numbers) == len(set(numbers))
    assert next(c for c in config['concepts'] if c['source_numbers'] == [17])['reason'] == selection['per_image_reasons']['17']
    pictures = expected_pictures(config)
    assert len(pictures) == 6 and len({p['name'] for p in pictures}) == 6
    assert not set(config['preflight_seeds']) & set(config['comparison_seeds'])
    assert not set(config['comparison_seeds']) & set(config['confirmation_seeds'])


def test_comparison_changes_only_preservation_weight():
    config = json.loads((DIRECTORY / 'config.json').read_text())
    baseline = {'model': 'model', 'qwen3': 'encoder', 'lora': 'original', 'strength': .8,
                'prompt': 'original prompt', 'negative': 'original negative'}
    no_preserve = training_input(baseline, config, 0)
    preserve = training_input(baseline, config, 1)
    assert preserve['locality']['weight'] == 1
    preserve['locality']['weight'] = 0
    assert preserve == no_preserve
    assert no_preserve['prompt'] == baseline['prompt']
    assert no_preserve['negative'] == baseline['negative']
    assert not {'pairs', 'positive_images', 'feature_weights'} & no_preserve.keys()
