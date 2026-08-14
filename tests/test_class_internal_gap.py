from __future__ import annotations

import math


def _stopping_calls(curvature: float, step: float, residual: float, tolerance: float) -> int:
    contraction = 1.0 - step * curvature
    return math.ceil(math.log(residual / tolerance) / -math.log(contraction))


def test_quadratic_witnesses_share_the_declared_transcript() -> None:
    strong_convexity = 0.2
    smoothness = 1.0
    gradient = 1.0
    current = 0.0
    distance_bound = gradient / strong_convexity

    for curvature in (strong_convexity, smoothness):
        function_value = 0.5 * curvature * current**2 + gradient * current
        current_gradient = curvature * current + gradient
        optimum = -gradient / curvature
        assert function_value == 0.0
        assert current_gradient == gradient
        assert abs(current - optimum) <= distance_bound


def test_rectangular_gap_diverges_inside_smooth_strongly_convex_class() -> None:
    strong_convexity = 0.2
    smoothness = 1.0
    step = 0.5
    gradient = 1.0
    tolerances = [1.0e-2, 1.0e-4, 1.0e-8]

    gaps = [
        _stopping_calls(strong_convexity, step, gradient, tolerance)
        - _stopping_calls(smoothness, step, gradient, tolerance)
        for tolerance in tolerances
    ]
    assert gaps == sorted(gaps)
    assert gaps[0] > 0
    assert gaps[-1] > 2 * gaps[0]


def test_candidate_trajectory_is_an_exact_one_step_shift() -> None:
    curvature = 0.2
    step = 0.5
    gradient = 1.0
    contraction = 1.0 - step * curvature

    baseline_residuals = [gradient * contraction**iteration for iteration in range(8)]
    candidate_residuals = [
        gradient * contraction ** (iteration + 1) for iteration in range(7)
    ]
    assert candidate_residuals == baseline_residuals[1:]
