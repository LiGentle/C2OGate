"""Tests for no-new-exact-query comparator lower certificates."""

from __future__ import annotations

import numpy as np

from c2ogate import (
    modal_approximate_newton_post_upper,
    modal_gradient_descent_envelope,
    relative_modal_certificate,
    smooth_gradient_call_lower_bound,
)


def _actual_calls(
    gradient: np.ndarray,
    eigenvalues: np.ndarray,
    step_size: float,
    tolerance: float,
) -> int:
    point = np.asarray(gradient, dtype=float).copy()
    calls = 0
    while np.linalg.norm(point) > tolerance:
        point *= 1.0 - step_size * eigenvalues
        calls += 1
    return calls


def test_smooth_gradient_lower_bound_is_valid_for_random_quadratics() -> None:
    rng = np.random.default_rng(101)
    for _ in range(200):
        eigenvalues = np.exp(rng.uniform(np.log(0.2), np.log(5.0), size=20))
        smoothness = float(np.max(eigenvalues))
        step_size = 0.8 / smoothness
        gradient = rng.normal(size=20)
        tolerance = 1.0e-7
        lower = smooth_gradient_call_lower_bound(
            float(np.linalg.norm(gradient)), tolerance, step_size, smoothness
        )
        assert lower <= _actual_calls(
            gradient, eigenvalues, step_size, tolerance
        )


def test_modal_envelope_contains_actual_calls() -> None:
    rng = np.random.default_rng(102)
    for _ in range(200):
        true_eigenvalues = np.exp(
            rng.uniform(np.log(0.5), np.log(8.0), size=32)
        )
        delta = rng.uniform(0.001, 0.2, size=32)
        errors = rng.uniform(-delta, delta)
        model = true_eigenvalues * (1.0 + errors)
        certificate = relative_modal_certificate(model, delta)
        step_size = 0.85 / float(np.max(certificate.upper_eigenvalues))
        gradient = rng.normal(size=32)
        tolerance = 1.0e-8
        envelope = modal_gradient_descent_envelope(
            gradient, certificate, step_size, tolerance
        )
        actual = _actual_calls(
            gradient, true_eigenvalues, step_size, tolerance
        )
        assert envelope.lower <= actual <= envelope.upper


def test_modal_post_upper_contains_actual_approximate_newton_path() -> None:
    rng = np.random.default_rng(103)
    for _ in range(200):
        true_eigenvalues = np.exp(
            rng.uniform(np.log(0.5), np.log(6.0), size=24)
        )
        delta = rng.uniform(0.001, 0.25, size=24)
        errors = rng.uniform(-delta, delta)
        model = true_eigenvalues * (1.0 + errors)
        certificate = relative_modal_certificate(model, delta)
        step_size = 0.8 / float(np.max(certificate.upper_eigenvalues))
        gradient = rng.normal(size=24)
        tolerance = 1.0e-8
        post_upper = modal_approximate_newton_post_upper(
            gradient, certificate, step_size, tolerance
        )
        post_gradient = (1.0 - true_eigenvalues / model) * gradient
        actual_post = _actual_calls(
            post_gradient, true_eigenvalues, step_size, tolerance
        )
        assert actual_post <= post_upper


def test_exact_modal_model_recovers_exact_call_count() -> None:
    eigenvalues = np.array([0.5, 1.0, 2.0, 4.0])
    certificate = relative_modal_certificate(eigenvalues, np.zeros(4))
    gradient = np.array([1.0, -2.0, 0.5, 4.0])
    step_size = 0.2
    tolerance = 1.0e-9
    envelope = modal_gradient_descent_envelope(
        gradient, certificate, step_size, tolerance
    )
    actual = _actual_calls(gradient, eigenvalues, step_size, tolerance)
    assert envelope.lower == actual == envelope.upper
    assert modal_approximate_newton_post_upper(
        gradient, certificate, step_size, tolerance
    ) == 0
