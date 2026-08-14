"""Tests for certificate and rejection-path cost accounting."""

from __future__ import annotations

from c2ogate import (
    CostBreakdown,
    cost_accounted_gate,
    productive_certificate_gate,
)


def test_certificate_and_verification_costs_are_charged_on_accept() -> None:
    costs = CostBreakdown(
        exact_call_seconds=10.0,
        cheap_oracle_seconds=3.0,
        certificate_seconds=4.0,
        verification_seconds=1.0,
        certificate_amortization_count=2,
    )
    decision = cost_accounted_gate(12, 10, costs)
    assert costs.predecision_exact_units == 0.2
    assert costs.accepted_incremental_exact_units == 0.6
    assert decision.gate.accept
    assert decision.gate.guaranteed_cost_slack_exact_units == 1.4


def test_positive_online_decision_cost_makes_unfunded_reject_unsafe() -> None:
    costs = CostBreakdown(
        exact_call_seconds=1.0,
        cheap_oracle_seconds=2.0,
        certificate_seconds=0.25,
    )
    decision = cost_accounted_gate(2, 2, costs)
    assert not decision.gate.accept
    assert not decision.reject_path_noninferior
    funded = cost_accounted_gate(2, 2, costs, banked_credit_exact_units=0.5)
    assert funded.reject_path_noninferior
    assert funded.guaranteed_credit_after == 0.25


def test_productive_certificate_funds_first_rejected_proposal() -> None:
    decision = productive_certificate_gate(
        free_baseline_lower_calls=10,
        fallback_upper_calls=8,
        refined_baseline_lower_calls=14,
        proposal_upper_calls=14,
        certificate_cost_exact_units=1.25,
    )
    assert decision.run_certificate
    assert not decision.use_proposal
    assert decision.fallback_path_noninferior
    assert decision.guaranteed_cost_slack_exact_units == 0.75


def test_productive_certificate_refuses_unfunded_first_decision() -> None:
    decision = productive_certificate_gate(
        free_baseline_lower_calls=4,
        fallback_upper_calls=4,
        refined_baseline_lower_calls=9,
        proposal_upper_calls=1,
        certificate_cost_exact_units=0.1,
    )
    assert not decision.run_certificate
    assert not decision.use_proposal
    assert not decision.fallback_path_noninferior


def test_productive_certificate_can_select_certified_proposal() -> None:
    decision = productive_certificate_gate(
        free_baseline_lower_calls=12,
        fallback_upper_calls=10,
        refined_baseline_lower_calls=20,
        proposal_upper_calls=3,
        certificate_cost_exact_units=1.0,
        proposal_cost_exact_units=0.5,
        minimum_saved_calls=2,
    )
    assert decision.run_certificate
    assert decision.use_proposal
    assert decision.guaranteed_saved_exact_calls == 17
    assert decision.guaranteed_cost_slack_exact_units == 15.5


def test_productive_certificate_enforces_requested_saving_on_fallback() -> None:
    decision = productive_certificate_gate(
        free_baseline_lower_calls=10,
        fallback_upper_calls=8,
        refined_baseline_lower_calls=20,
        proposal_upper_calls=1,
        certificate_cost_exact_units=0.5,
        minimum_saved_calls=3,
    )
    assert not decision.run_certificate
    assert not decision.use_proposal
    assert decision.fallback_path_noninferior
