"""Certified residual tubes for noncommuting quadratic Hessians.

The true stationary Hessian ``Q`` may have different eigenvectors from the
cheap model ``M``.  The only structural contract is the spectral-norm ball

``||Q - M||_2 <= radius``.

All trajectories use a residual already cached at the branch point.  Model
matrix-vector products span a Krylov space and never evaluate ``Q``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log

import numpy as np

from .core import CountEnvelope


@dataclass(frozen=True)
class MatrixUncertainty:
    """A symmetric spectral-norm uncertainty ball around a cheap model."""

    center: np.ndarray
    radius: float

    def __post_init__(self) -> None:
        center = np.asarray(self.center, dtype=float)
        if center.ndim != 2 or center.shape[0] != center.shape[1]:
            raise ValueError("center must be a square matrix")
        if not np.allclose(center, center.T, atol=1.0e-12, rtol=1.0e-12):
            raise ValueError("center must be symmetric")
        if self.radius < 0.0:
            raise ValueError("radius must be nonnegative")
        if self.lower_eigenvalue <= 0.0:
            raise ValueError("the uncertainty ball must be uniformly positive")

    @property
    def center_eigenvalues(self) -> np.ndarray:
        return np.linalg.eigvalsh(np.asarray(self.center, dtype=float))

    @property
    def lower_eigenvalue(self) -> float:
        return float(np.min(np.linalg.eigvalsh(self.center)) - self.radius)

    @property
    def upper_eigenvalue(self) -> float:
        return float(np.max(np.linalg.eigvalsh(self.center)) + self.radius)

    def true_step_norm_bound(self, step_size: float) -> float:
        """Bound ``||I-alpha Q||`` for every matrix in the ball."""

        if step_size <= 0.0:
            raise ValueError("step_size must be positive")
        lower = self.lower_eigenvalue
        upper = self.upper_eigenvalue
        return max(abs(1.0 - step_size * lower), abs(1.0 - step_size * upper))


@dataclass(frozen=True)
class KrylovResidualTube:
    """A nominal Krylov trajectory with a rigorous perturbation tube."""

    envelope: CountEnvelope
    nominal_residuals: np.ndarray
    error_radii: np.ndarray
    lower_residuals: np.ndarray
    upper_residuals: np.ndarray
    model_matvecs: int


def matrix_uncertainty_progress_factors(
    uncertainty: MatrixUncertainty,
    step_size: float,
) -> tuple[float, float]:
    """Uniform two-sided residual factors without a common eigenbasis.

    Reverse and ordinary triangle inequalities applied to
    ``(I-alpha M)g - alpha(Q-M)g`` remain valid when ``M`` and ``Q`` do not
    commute.
    """

    center = np.asarray(uncertainty.center, dtype=float)
    nominal_step = np.eye(center.shape[0]) - step_size * center
    singular_values = np.linalg.svd(nominal_step, compute_uv=False)
    lower = float(np.min(singular_values) - step_size * uncertainty.radius)
    upper = float(np.max(singular_values) + step_size * uncertainty.radius)
    if not 0.0 < lower <= upper < 1.0:
        raise ValueError("uncertainty does not certify a two-sided contraction")
    return lower, upper


def krylov_matrix_uncertainty_envelope(
    cached_residual: np.ndarray,
    uncertainty: MatrixUncertainty,
    step_size: float,
    tolerance: float,
    *,
    max_calls: int = 1_000_000,
) -> KrylovResidualTube:
    """Enclose a noncommuting exact trajectory using only cheap matvecs.

    Let ``h_{k+1}=(I-alpha M)h_k`` be the nominal trajectory and let
    ``e_k`` bound the difference from the true trajectory.  If
    ``rho >= ||I-alpha Q||`` and ``eta >= ||Q-M||``, then

    ``e_{k+1} = rho*e_k + alpha*eta*||h_k||``

    is a valid deterministic error radius.  The nominal vectors lie in
    ``K_{k+1}(M, r_0)``.  The first lower-tube crossing gives the comparator
    lower call bound; the first upper-tube crossing gives an upper bound.
    """

    residual = np.asarray(cached_residual, dtype=float)
    center = np.asarray(uncertainty.center, dtype=float)
    if residual.ndim != 1 or residual.shape[0] != center.shape[0]:
        raise ValueError("cached_residual has the wrong dimension")
    if tolerance <= 0.0 or max_calls < 1:
        raise ValueError("require tolerance > 0 and max_calls >= 1")
    rho = uncertainty.true_step_norm_bound(step_size)
    if not 0.0 < rho < 1.0:
        raise ValueError("the full uncertainty set must be contractive")

    nominal = residual.copy()
    error = 0.0
    nominal_norms: list[float] = []
    errors: list[float] = []
    lowers: list[float] = []
    uppers: list[float] = []
    lower_count: int | None = None
    upper_count: int | None = None

    for k in range(max_calls + 1):
        nominal_norm = float(np.linalg.norm(nominal))
        lower = max(0.0, nominal_norm - error)
        upper = nominal_norm + error
        nominal_norms.append(nominal_norm)
        errors.append(error)
        lowers.append(lower)
        uppers.append(upper)
        if lower_count is None and lower <= tolerance:
            lower_count = k
        if upper <= tolerance:
            upper_count = k
            break
        previous_norm = nominal_norm
        nominal = nominal - step_size * (center @ nominal)
        error = (
            rho * error
            + step_size * uncertainty.radius * previous_norm
        )

    if upper_count is None or lower_count is None:
        raise RuntimeError("Krylov tube did not cross tolerance before max_calls")
    return KrylovResidualTube(
        envelope=CountEnvelope(lower_count, upper_count),
        nominal_residuals=np.asarray(nominal_norms),
        error_radii=np.asarray(errors),
        lower_residuals=np.asarray(lowers),
        upper_residuals=np.asarray(uppers),
        model_matvecs=upper_count,
    )


def matrix_approximate_newton_post_upper(
    cached_residual: np.ndarray,
    uncertainty: MatrixUncertainty,
    step_size: float,
    tolerance: float,
) -> int:
    """Upper-bound exact calls after ``x <- x-M^{-1}g``.

    The post-transition exact residual is
    ``(I-Q M^{-1})g = -(Q-M)M^{-1}g`` and hence has norm at most
    ``radius*||M^{-1}g||``.  Future exact steps use the uniform contraction
    of the entire matrix uncertainty set.
    """

    residual = np.asarray(cached_residual, dtype=float)
    center = np.asarray(uncertainty.center, dtype=float)
    if residual.ndim != 1 or residual.shape[0] != center.shape[0]:
        raise ValueError("cached_residual has the wrong dimension")
    if tolerance <= 0.0:
        raise ValueError("tolerance must be positive")
    model_step = np.linalg.solve(center, residual)
    post_residual = uncertainty.radius * float(np.linalg.norm(model_step))
    if post_residual <= tolerance:
        return 0
    rho = uncertainty.true_step_norm_bound(step_size)
    if not 0.0 < rho < 1.0:
        raise ValueError("the full uncertainty set must be contractive")
    raw = log(tolerance / post_residual) / log(rho)
    return max(0, int(ceil(raw - 1.0e-12)))
