"""Tests for transcript-conditioned joint gates."""

from __future__ import annotations

from c2ogate.transcript import StoppingPair, transcript_optimal_gate


def test_joint_gate_strictly_dominates_rectangular_envelopes() -> None:
    pairs = [StoppingPair(5, 4), StoppingPair(25, 24)]
    decision = transcript_optimal_gate(pairs, 0.4)
    assert decision.accept_joint
    assert not decision.accept_rectangle
    assert decision.worst_joint_call_difference == -1
    assert decision.rectangle_call_difference == 19
    assert decision.transcript_certificate_value == 0.0
    assert decision.guaranteed_joint_call_slack == 0
    assert decision.guaranteed_joint_cost_slack == 0.6


def test_joint_gate_rejects_one_bad_consistent_instance() -> None:
    decision = transcript_optimal_gate([(10, 8), (30, 30)], 0.2)
    assert not decision.accept_joint
    assert decision.worst_joint_call_difference == 0


def test_rectangle_acceptance_implies_joint_acceptance() -> None:
    decision = transcript_optimal_gate([(12, 3), (15, 5)], 2.0, minimum_saved_calls=2)
    assert decision.accept_rectangle
    assert decision.accept_joint
