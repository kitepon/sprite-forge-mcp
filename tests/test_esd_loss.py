import pytest

from box.esd_loss import erasure_target, weighted_erasure_delta


def test_erasure_moves_away_from_concept():
    assert erasure_target(10, 5, 2, 1) == 7
    assert erasure_target(10, 5, 2, 2) == 4


def test_absent_concept_or_zero_strength_preserves_subject():
    assert erasure_target(10, 2, 2, 1) == 10
    assert erasure_target(10, 5, 2, 0) == 10


def test_weighted_features_keep_raw_scale_and_tiny_weights():
    delta = weighted_erasure_delta([(0.5, 6), (0.001, 3)], 2)
    assert delta == 2.001
    assert erasure_target(10, 2 + delta, 2, 1) == pytest.approx(7.999)
