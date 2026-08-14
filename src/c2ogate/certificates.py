"""No-new-exact-query lower certificates for stationary gradient baselines.

The certificates consume a residual already cached at the branch point and
metadata known before querying the cheap transition.  They never evaluate the
true gradient or Hessian at a new point.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log, sqrt
from typing import Callable

import numpy as np

from .core import CountEnvelope


@dataclass(frozen=True)
class ModalCertificate:
    """A simultaneous diagonal spectral enclosure in a known basis.

    The true quadratic Hessian is diagonal in the declared basis and its
    eigenvalues obey ``lower_eigenvalues <= lambda <= upper_eigenvalues``.
    ``model_eigenvalues`` defines the cheap approximate Newton transition.
    """

    lower_eigenvalues: np.ndarray
    model_eigenvalues: np.ndarray
    upper_eigenvalues: np.ndarray

    def __post_init__(self) -> None:
        lower = np.asarray(self.lower_eigenvalues, dtype=float)
        model = np.asarray(self.model_eigenvalues, dtype=float)
        upper = np.asarray(self.upper_eigenvalues, dtype=float)
        if lower.ndim != 1 or model.shape != lower.shape or upper.shape != lower.shape:
            raise ValueError("all modal eigenvalue arrays must be matching vectors")
        if np.any(lower <= 0.0) or np.any(lower > model) or np.any(model > upper):
            raise ValueError("require 0 < lower <= model <= upper componentwise")


def smooth_gradient_call_lower_bound(
    gradient_norm: float,
    tolerance: float,
    step_size: float,
    smoothness: float,
) -> int:
    """Lower-bound fixed-step GD calls from a cached gradient norm.

    For a convex L-smooth objective and ``0 < alpha*L < 1``, the exact
    gradient residual satisfies

    ``||g_{k+1}|| >= (1-alpha*L) ||g_k||``.

    No strong-convexity constant or new exact query is required.
    """

    if gradient_norm < 0.0 or tolerance <= 0.0:
        raise ValueError("require gradient_norm >= 0 and tolerance > 0")
    if smoothness <= 0.0 or not 0.0 < step_size * smoothness < 1.0:
        raise ValueError("require smoothness > 0 and 0 < step_size*L < 1")
    if gradient_norm <= tolerance:
        return 0
    factor = 1.0 - step_size * smoothness
    raw = log(tolerance / gradient_norm) / log(factor)
    return max(0, int(ceil(raw - 1.0e-12)))


def _first_certified_crossing(
    bound_at_step: Callable[[int], float],
    tolerance: float,
    *,
    max_calls: int = 10_000_000,
) -> int:
    """Find the first integer k whose monotone bound is at most tolerance."""

    if bound_at_step(0) <= tolerance:
        return 0
    high = 1
    while high < max_calls and bound_at_step(high) > tolerance:
        high *= 2
    high = min(high, max_calls)
    if bound_at_step(high) > tolerance:
        raise RuntimeError("certificate did not cross tolerance before max_calls")
    low = high // 2
    while low + 1 < high:
        middle = (low + high) // 2
        if bound_at_step(middle) <= tolerance:
            high = middle
        else:
            low = middle
    return high


def modal_gradient_descent_envelope(
    cached_gradient_components: np.ndarray,
    certificate: ModalCertificate,
    step_size: float,
    tolerance: float,
) -> CountEnvelope:
    """Return an instance-specific exact-call envelope without a new query.

    For a quadratic whose Hessian shares the certified modal basis, exact
    gradient descent evolves each cached gradient component as

    ``g_i(k) = (1-alpha*lambda_i)^k g_i(0)``.

    The interval endpoints therefore give simultaneous lower and upper norm
    trajectories.  The lower trajectory yields the missing comparator-side
    call lower bound.
    """

    gradient = np.asarray(cached_gradient_components, dtype=float)
    lower = np.asarray(certificate.lower_eigenvalues, dtype=float)
    upper = np.asarray(certificate.upper_eigenvalues, dtype=float)
    if gradient.shape != lower.shape:
        raise ValueError("cached gradient has the wrong modal dimension")
    if tolerance <= 0.0:
        raise ValueError("tolerance must be positive")
    if not 0.0 < step_size * float(np.max(upper)) < 1.0:
        raise ValueError("require 0 < alpha*max(upper eigenvalue) < 1")

    abs_gradient = np.abs(gradient)
    lower_factors = 1.0 - step_size * upper
    upper_factors = 1.0 - step_size * lower

    def lower_norm(k: int) -> float:
        return float(np.linalg.norm(abs_gradient * np.power(lower_factors, k)))

    def upper_norm(k: int) -> float:
        return float(np.linalg.norm(abs_gradient * np.power(upper_factors, k)))

    return CountEnvelope(
        lower=_first_certified_crossing(lower_norm, tolerance),
        upper=_first_certified_crossing(upper_norm, tolerance),
    )


def modal_approximate_newton_post_upper(
    cached_gradient_components: np.ndarray,
    certificate: ModalCertificate,
    step_size: float,
    tolerance: float,
) -> int:
    """Upper-bound post-query exact calls for a modal approximate Newton step.

    The cheap transition uses ``model_eigenvalues^{-1}`` on the cached exact
    gradient.  For every true eigenvalue in its certified interval, the new
    gradient component has magnitude at most

    ``max(|1-lower/model|, |1-upper/model|) * |g_i|``.

    Subsequent exact GD decay is slowest at the lower eigenvalue endpoint.
    """

    gradient = np.asarray(cached_gradient_components, dtype=float)
    lower = np.asarray(certificate.lower_eigenvalues, dtype=float)
    model = np.asarray(certificate.model_eigenvalues, dtype=float)
    upper = np.asarray(certificate.upper_eigenvalues, dtype=float)
    if gradient.shape != lower.shape:
        raise ValueError("cached gradient has the wrong modal dimension")
    if tolerance <= 0.0:
        raise ValueError("tolerance must be positive")
    if not 0.0 < step_size * float(np.max(upper)) < 1.0:
        raise ValueError("require 0 < alpha*max(upper eigenvalue) < 1")

    transition = np.maximum(
        np.abs(1.0 - lower / model),
        np.abs(1.0 - upper / model),
    )
    post_component_upper = np.abs(gradient) * transition
    slow_factors = 1.0 - step_size * lower

    def post_upper_norm(k: int) -> float:
        return float(
            np.linalg.norm(post_component_upper * np.power(slow_factors, k))
        )

    return _first_certified_crossing(post_upper_norm, tolerance)


def relative_modal_certificate(
    model_eigenvalues: np.ndarray,
    relative_error_bounds: np.ndarray,
) -> ModalCertificate:
    """Build lambda intervals from |model/lambda - 1| <= delta < 1."""

    model = np.asarray(model_eigenvalues, dtype=float)
    delta = np.asarray(relative_error_bounds, dtype=float)
    if model.ndim != 1 or delta.shape != model.shape:
        raise ValueError("model and delta must be matching vectors")
    if np.any(model <= 0.0) or np.any(delta < 0.0) or np.any(delta >= 1.0):
        raise ValueError("require model > 0 and 0 <= delta < 1")
    return ModalCertificate(
        lower_eigenvalues=model / (1.0 + delta),
        model_eigenvalues=model,
        upper_eigenvalues=model / (1.0 - delta),
    )


def modal_bound_at_step(
    component_magnitudes: np.ndarray,
    factors: np.ndarray,
    step: int,
) -> float:
    """Public helper used to audit a modal residual trajectory."""

    components = np.asarray(component_magnitudes, dtype=float)
    factors = np.asarray(factors, dtype=float)
    if components.shape != factors.shape or step < 0:
        raise ValueError("matching vectors and a nonnegative step are required")
    return sqrt(float(np.sum(np.square(components * np.power(factors, step)))))
