import importlib.util
import json
from pathlib import Path

import pytest


DIRECTORY = Path(__file__).resolve().parents[1] / 'evidence/ng-generalization-20260907'
spec = importlib.util.spec_from_file_location('generic_ng_probe', DIRECTORY / 'probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_owner_feedback_survives_and_research_labels_are_separate():
    selection = {'selected_ng_numbers': [1, 2, 17], 'reason': '共通の否定理由',
                 'per_image_reasons': {'17': 'この画像だけの否定理由'}}
    result = probe.cases(selection)
    actual = [item for item in result if item['origin'] == '本人のNG']
    assert sorted(item['number'] for item in actual) == [1, 2, 17]
    assert next(item for item in actual if item['number'] == 17)['comment'] == 'この画像だけの否定理由'
    assert next(item for item in actual if item['number'] == 2)['comment'] == '共通の否定理由'
    assert len(result) == len(actual) + 3


def test_unresolved_feedback_cannot_silently_become_an_erasure_target():
    meaning = dict(observed_ng_ja=None, erase_concept_en=None, evidence_ja='肯定の指摘だけ',
                   preserve_ja=['衣装'], question_ja='どこがNGですか？')
    assert probe.parse_meaning(json.dumps(meaning)) == meaning
    meaning['erase_concept_en'] = 'fur collar'
    with pytest.raises(ValueError, match='未確定'):
        probe.parse_meaning(json.dumps(meaning))


def test_same_parser_accepts_different_visual_concepts_without_part_branches():
    for target in ('multiple views', 'fur collar', 'short bob haircut', 'oversized hands'):
        meaning = dict(observed_ng_ja='否定された状態', erase_concept_en=target,
                       evidence_ja='画像と指摘の対応', preserve_ja=[], question_ja=None)
        assert probe.parse_meaning(json.dumps(meaning))['erase_concept_en'] == target


def test_training_uses_identical_algorithm_and_keeps_unresolved_case_out():
    import sys
    sys.path.insert(0, str(DIRECTORY))
    from train_compare import training_input
    experiment = json.loads((DIRECTORY / 'experiment.json').read_text())
    baseline = dict(model='anima', qwen3='encoder', lora='source', strength=.8, prompt='subject', negative='')
    analysis = {'results': [{'id': 'a', 'meaning': {'question_ja': None, 'erase_concept_en': 'fur collar'}},
                            {'id': 'b', 'meaning': {'question_ja': None, 'erase_concept_en': 'multiple views'}},
                            {'id': 'unknown', 'meaning': {'question_ja': '対象は何ですか', 'erase_concept_en': None}}]}
    a = training_input(baseline, experiment, {'case_ids': ['a']}, analysis)
    b = training_input(baseline, experiment, {'case_ids': ['b']}, analysis)
    assert a.pop('erase_concept') == 'fur collar'
    assert b.pop('erase_concept') == 'multiple views'
    assert a.pop('erase_concepts') == ['fur collar']
    assert b.pop('erase_concepts') == ['multiple views']
    assert a == b
    assert not {'locality', 'positive_images', 'pairs', 'feature_weights'} & a.keys()
    with pytest.raises(ValueError, match='未確定'):
        training_input(baseline, experiment, {'case_ids': ['unknown']}, analysis)


def test_fox_lora_receipt_uses_windows_path_on_main_server():
    import sys
    sys.path.insert(0, str(DIRECTORY))
    from train_compare import lora_filename
    assert lora_filename(r'C:\Users\kite_\ComfyUI\models\loras\trial.safetensors') == 'trial.safetensors'
    assert lora_filename('C:/Users/kite_/ComfyUI/models/loras/trial.safetensors') == 'trial.safetensors'
