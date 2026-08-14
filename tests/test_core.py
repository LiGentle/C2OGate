"""Unit tests for the information-robust cost gate."""

from __future__ import annotations

import pytest

from c2ogate import contraction_count_envelope, robust_cost_gate


def test_interval_robust_gate_accepts_exact_boundary() -> None:
    decision = robust_cost_gate(10, 8, 2.0)
    assert decision.accept
    assert decision.guaranteed_saved_exact_calls == 2
    assert decision.guaranteed_cost_slack_exact_units == 0.0


def test_gate_requires_an_exact_call_reduction() -> None:
    assert not robust_cost_gate(10, 10, 0.0).accept
    assert robust_cost_gate(
        10, 10, 0.0, minimum_saved_calls=0
    ).accept


def test_sunk_cost_cannot_be_recovered_by_rejecting_output() -> None:
    baseline_calls = 7
    cheap_cost = 0.25
    posthoc_reject_cost = cheap_cost + baseline_calls
    assert posthoc_reject_cost > baseline_calls


def test_contraction_count_envelope_contains_a_scalar_trajectory() -> None:
    envelope = contraction_count_envelope(1.0, 1.0e-6, 0.5, 0.8)
    for factor in (0.5, 0.63, 0.8):
        residual = 1.0
        calls = 0
        while residual > 1.0e-6:
            residual *= factor
            calls += 1
        assert envelope.lower <= calls <= envelope.upper


def test_invalid_envelope_is_rejected() -> None:
    with pytest.raises(ValueError):
        contraction_count_envelope(1.0, 1.0e-6, 0.9, 0.8)
