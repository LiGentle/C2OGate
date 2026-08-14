"""Local active-regime certificates for projection and proximal maps.

Projection and thresholding are not globally co-Lipschitz: they can collapse
whole regions.  The functions below certify that a cached iterate lies far
enough from every breakpoint that a contractive forward-backward trajectory
cannot change its active regime.  Inside that regime the method is affine and
the reduced Hessian certificates apply.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ActiveRegimeCertificate:
    """A strict-margin proof that an active pattern remains invariant."""

    pattern: np.ndarray
    reduced_indices: np.ndarray
    breakpoint_margin: float
    fixed_point_distance_upper: float
    required_margin: float
    forward_contraction: float
    certified: bool
    map_name: str


def _regime_certificate(
    pattern: np.ndarray,
    reduced_indices: np.ndarray,
    margin: float,
    displacement: float,
    forward_contraction: float,
    map_name: str,
) -> ActiveRegimeCertificate:
    if not 0.0 <= forward_contraction < 1.0:
        raise ValueError("forward_contraction must lie in [0, 1)")
    distance = displacement / (1.0 - forward_contraction)
    required = 2.0 * forward_contraction * distance
    pattern_array = np.asarray(pattern, dtype=int)
    return ActiveRegimeCertificate(
        pattern=pattern_array,
        reduced_indices=np.asarray(reduced_indices, dtype=int),
        breakpoint_margin=float(margin),
        fixed_point_distance_upper=float(distance),
        required_margin=float(required),
        forward_contraction=float(forward_contraction),
        certified=bool(margin > required + 1.0e-14),
        map_name=map_name,
    )


def box_projection_active_regime(
    point: np.ndarray,
    cached_gradient: np.ndarray,
    step_size: float,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    forward_contraction: float,
) -> ActiveRegimeCertificate:
    """Certify an invariant box-projection pattern.

    Pattern values are ``-1`` at a lower bound, ``+1`` at an upper bound, and
    ``0`` for a free coordinate.  The proof uses the contraction a-posteriori
    error bound ``||x-x*|| <= ||x-Tx||/(1-q)`` and the fact that the forward
    point can move by at most ``2*q*||x-x*||`` over all future iterates.
    """

    x = np.asarray(point, dtype=float)
    gradient = np.asarray(cached_gradient, dtype=float)
    lower = np.asarray(lower_bounds, dtype=float)
    upper = np.asarray(upper_bounds, dtype=float)
    if not (x.shape == gradient.shape == lower.shape == upper.shape):
        raise ValueError("all box inputs must be matching vectors")
    if step_size <= 0.0 or np.any(lower >= upper):
        raise ValueError("invalid step size or box bounds")
    forward = x - step_size * gradient
    projected = np.clip(forward, lower, upper)
    pattern = np.zeros(x.shape, dtype=int)
    pattern[forward < lower] = -1
    pattern[forward > upper] = 1
    margins = np.where(
        pattern == -1,
        lower - forward,
        np.where(pattern == 1, forward - upper, np.minimum(forward - lower, upper - forward)),
    )
    return _regime_certificate(
        pattern,
        np.flatnonzero(pattern == 0),
        float(np.min(margins)),
        float(np.linalg.norm(x - projected)),
        forward_contraction,
        "box projection",
    )


def box_projection_candidate_regime(
    point: np.ndarray,
    cached_gradient: np.ndarray,
    candidate_displacement: np.ndarray,
    model_hessian: np.ndarray,
    uncertainty_radius: float,
    step_size: float,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    forward_contraction: float,
) -> ActiveRegimeCertificate:
    """Certify a proposed reduced update before evaluating its true gradient.

    For ``y=x+d``, the unknown forward point differs from
    ``y-alpha*(g+M d)`` by at most ``alpha*radius*||d||``.  Shrinking every
    breakpoint margin by that amount gives an ex-ante certificate covering
    every true Hessian in the matrix uncertainty ball.
    """

    x = np.asarray(point, dtype=float)
    gradient = np.asarray(cached_gradient, dtype=float)
    displacement = np.asarray(candidate_displacement, dtype=float)
    model = np.asarray(model_hessian, dtype=float)
    lower = np.asarray(lower_bounds, dtype=float)
    upper = np.asarray(upper_bounds, dtype=float)
    if not (
        x.shape == gradient.shape == displacement.shape == lower.shape == upper.shape
    ):
        raise ValueError("all candidate box vectors must match")
    if model.shape != (x.size, x.size) or uncertainty_radius < 0.0:
        raise ValueError("invalid model Hessian or uncertainty radius")
    candidate = x + displacement
    nominal_forward = candidate - step_size * (
        gradient + model @ displacement
    )
    forward_error = step_size * uncertainty_radius * float(
        np.linalg.norm(displacement)
    )
    nominal_projection = np.clip(nominal_forward, lower, upper)
    pattern = np.zeros(x.shape, dtype=int)
    pattern[nominal_forward < lower] = -1
    pattern[nominal_forward > upper] = 1
    margins = np.where(
        pattern == -1,
        lower - nominal_forward,
        np.where(
            pattern == 1,
            nominal_forward - upper,
            np.minimum(nominal_forward - lower, upper - nominal_forward),
        ),
    )
    robust_margin = float(np.min(margins)) - forward_error
    displacement_upper = (
        float(np.linalg.norm(candidate - nominal_projection)) + forward_error
    )
    return _regime_certificate(
        pattern,
        np.flatnonzero(pattern == 0),
        robust_margin,
        displacement_upper,
        forward_contraction,
        "box projection candidate",
    )


def soft_threshold_active_regime(
    point: np.ndarray,
    cached_gradient: np.ndarray,
    step_size: float,
    l1_weight: float,
    forward_contraction: float,
) -> ActiveRegimeCertificate:
    """Certify an invariant support/sign pattern for proximal gradient."""

    x = np.asarray(point, dtype=float)
    gradient = np.asarray(cached_gradient, dtype=float)
    if x.shape != gradient.shape or x.ndim != 1:
        raise ValueError("point and gradient must be matching vectors")
    if step_size <= 0.0 or l1_weight < 0.0:
        raise ValueError("invalid step size or l1 weight")
    threshold = step_size * l1_weight
    forward = x - step_size * gradient
    proximal = np.sign(forward) * np.maximum(np.abs(forward) - threshold, 0.0)
    pattern = np.zeros(x.shape, dtype=int)
    pattern[forward > threshold] = 1
    pattern[forward < -threshold] = -1
    margin = float(np.min(np.abs(np.abs(forward) - threshold)))
    return _regime_certificate(
        pattern,
        np.flatnonzero(pattern != 0),
        margin,
        float(np.linalg.norm(x - proximal)),
        forward_contraction,
        "soft threshold",
    )


def soft_threshold_candidate_regime(
    point: np.ndarray,
    cached_gradient: np.ndarray,
    candidate_displacement: np.ndarray,
    model_hessian: np.ndarray,
    uncertainty_radius: float,
    step_size: float,
    l1_weight: float,
    forward_contraction: float,
) -> ActiveRegimeCertificate:
    """Certify the support/sign of an approximate proximal-Newton candidate."""

    x = np.asarray(point, dtype=float)
    gradient = np.asarray(cached_gradient, dtype=float)
    displacement = np.asarray(candidate_displacement, dtype=float)
    model = np.asarray(model_hessian, dtype=float)
    if not (x.shape == gradient.shape == displacement.shape) or x.ndim != 1:
        raise ValueError("candidate proximal vectors must match")
    if model.shape != (x.size, x.size) or uncertainty_radius < 0.0:
        raise ValueError("invalid model Hessian or uncertainty radius")
    if step_size <= 0.0 or l1_weight < 0.0:
        raise ValueError("invalid step size or l1 weight")
    threshold = step_size * l1_weight
    candidate = x + displacement
    nominal_forward = candidate - step_size * (
        gradient + model @ displacement
    )
    forward_error = step_size * uncertainty_radius * float(
        np.linalg.norm(displacement)
    )
    nominal_proximal = np.sign(nominal_forward) * np.maximum(
        np.abs(nominal_forward) - threshold, 0.0
    )
    pattern = np.zeros(x.shape, dtype=int)
    pattern[nominal_forward > threshold] = 1
    pattern[nominal_forward < -threshold] = -1
    robust_margin = (
        float(np.min(np.abs(np.abs(nominal_forward) - threshold)))
        - forward_error
    )
    displacement_upper = (
        float(np.linalg.norm(candidate - nominal_proximal)) + forward_error
    )
    return _regime_certificate(
        pattern,
        np.flatnonzero(pattern != 0),
        robust_margin,
        displacement_upper,
        forward_contraction,
        "soft threshold candidate",
    )


def reduced_matrix(matrix: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Compress a Hessian/model to a certified free manifold."""

    source = np.asarray(matrix, dtype=float)
    selected = np.asarray(indices, dtype=int)
    if source.ndim != 2 or source.shape[0] != source.shape[1]:
        raise ValueError("matrix must be square")
    if selected.ndim != 1 or np.any(selected < 0) or np.any(selected >= source.shape[0]):
        raise ValueError("indices are invalid")
    return source[np.ix_(selected, selected)]
