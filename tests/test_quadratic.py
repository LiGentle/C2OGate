"""Tests for the spectrally certified quadratic cheap oracle."""

from __future__ import annotations

import numpy as np

from c2ogate import (
    DiagonalQuadratic,
    contraction_count_envelope,
    robust_cost_gate,
)
from c2ogate.quadratic import approximate_newton_contraction


def test_approximate_newton_contract_holds_randomly() -> None:
    rng = np.random.default_rng(19)
    eigenvalues = np.geomspace(1.0, 2.0, 40)
    problem = DiagonalQuadratic(eigenvalues, np.zeros(40), 0.2)
    for delta in (0.01, 0.1, 0.3, 0.49, 0.7):
        for _ in range(20):
            x = rng.normal(size=40)
            errors = rng.uniform(-delta, delta, size=40)
            candidate = problem.approximate_newton_step(x, errors)
            assert problem.residual(candidate) <= (
                approximate_newton_contraction(delta) * problem.residual(x)
                * (1.0 + 1.0e-12)
            )


def test_every_accepted_quadratic_gate_dominates_realized_baseline() -> None:
    rng = np.random.default_rng(23)
    accepted = 0
    for _ in range(300):
        kappa = float(np.exp(rng.uniform(0.0, np.log(2.0))))
        eigenvalues = np.geomspace(1.0, kappa, 32)
        problem = DiagonalQuadratic(
            eigenvalues, np.zeros(32), 0.49 / kappa
        )
        x = problem.normalize_residual(rng.normal(size=32))
        delta = float(np.exp(rng.uniform(np.log(1.0e-3), np.log(0.3))))
        errors = rng.uniform(-delta, delta, size=32)
        candidate = problem.approximate_newton_step(x, errors)
        baseline = contraction_count_envelope(
            problem.residual(x), 1.0e-6,
            problem.lower_contraction, problem.upper_contraction,
        )
        post = contraction_count_envelope(
            approximate_newton_contraction(delta) * problem.residual(x),
            1.0e-6, problem.lower_contraction, problem.upper_contraction,
        )
        cheap_cost = 0.5
        gate = robust_cost_gate(baseline.lower, post.upper, cheap_cost)
        if not gate.accept:
            continue
        accepted += 1
        baseline_calls = problem.exact_calls_to_tolerance(x, 1.0e-6)
        post_calls = problem.exact_calls_to_tolerance(candidate, 1.0e-6)
        assert post_calls <= baseline_calls - 1
        assert cheap_cost + post_calls <= baseline_calls
    assert accepted > 0
