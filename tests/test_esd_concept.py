import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('concept', Path(__file__).resolve().parents[1] / 'evidence/preview-feedback-20260906/build_esd_concept.py')
concept = importlib.util.module_from_spec(spec)
spec.loader.exec_module(concept)


def test_concept_keeps_tiny_positive_features_without_numeric_weights():
    result = concept.build({'images': [
        {'features': [{'tag': 'short_hair', 'weight': .2}, {'tag': 'ahoge', 'weight': .000001}]},
        {'features': [{'tag': 'short_hair', 'weight': .3}, {'tag': 'long_hair', 'weight': .1}]},
    ]})
    assert result == 'Hairstyle with the following features: short hair, long hair, ahoge.'
    assert '0.3' not in result
