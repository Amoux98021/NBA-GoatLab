from __future__ import annotations

import numpy as np

from goatlab.rankings.longevity_calibration import (
    conformal_radius,
    run_bridge_candidates,
    threshold_components,
)


def test_threshold_components_preserve_frozen_semantics() -> None:
    seasons = np.asarray([2000, 2001, 2002, 2004])
    values = np.asarray([[79.0, 80.0, 95.0, 85.0]])
    result = threshold_components(values, seasons)
    assert result.breadth.tolist() == [3.0]
    assert result.capped_area.tolist() == [1.5]
    assert result.longest_run.tolist() == [2.0]


def test_run_bridge_event_detects_uncertain_connector() -> None:
    probability = np.asarray([0.9, 0.8, 0.5, 0.9, 0.8])
    events = run_bridge_candidates(probability, np.arange(2000, 2005))
    assert events == [(2, 2, 2)]


def test_run_bridge_event_respects_calendar_gaps() -> None:
    probability = np.asarray([0.9, 0.5, 0.9])
    events = run_bridge_candidates(probability, np.asarray([2000, 2001, 2003]))
    assert events == []


def test_conformal_radius_uses_finite_sample_rank() -> None:
    assert conformal_radius(np.asarray([1.0, -2.0, 3.0, 4.0]), 0.80) == 4.0
