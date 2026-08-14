"""Residual tubes for nonlinear Hessians and curved active manifolds.

The certificate covers dynamics of the form

``r[k+1] = (I - alpha * H[k]) r[k] + w[k]``

with step-dependent matrix contracts ``||H[k] - M[k]|| <= eta[k]``,
``||I-alpha H[k]|| <= rho[k]``, and an optional nonlinear defect
``||w[k]|| <= kappa ||r[k]||^2``.  The model matrices, radii, and
contraction bounds may all vary with the iteration.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import ceil, log

import numpy as np

from .core import CountEnvelope


MatrixSchedule = np.ndarray | Sequence[np.ndarray] | Callable[[int], np.ndarray]
ScalarSchedule = float | Sequence[float] | Callable[[int], float]


@dataclass(frozen=True)
class DynamicResidualTube:
    """Nominal trajectory and rigorous radii for nonstationary dynamics."""

    envelope: CountEnvelope
    nominal_residuals: np.ndarray
    error_radii: np.ndarray
    lower_residuals: np.ndarray
    upper_residuals: np.ndarray
    uncertainty_radii: np.ndarray
    contraction_bounds: np.ndarray
    model_matvecs: int


@dataclass(frozen=True)
class LipschitzHessianSchedule:
    """Shrinking matrix radius around a model certified at the solution.

    If ``||M-H(x*)|| <= model_error_at_solution``, the Hessian is
    ``hessian_lipschitz``-Lipschitz, ``||x_k-x*|| <= q^k R``, and the
    gradient is ``smoothness``-Lipschitz, then the average Hessian on the
    gradient step lies within this schedule of ``M``.
    """

    model_error_at_solution: float
    hessian_lipschitz: float
    initial_distance_upper: float
    smoothness: float
    step_size: float
    contraction: float

    def __post_init__(self) -> None:
        values = (
            self.model_error_at_solution,
            self.hessian_lipschitz,
            self.initial_distance_upper,
            self.smoothness,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("model and region constants must be nonnegative")
        if self.step_size <= 0.0:
            raise ValueError("step_size must be positive")
        if not 0.0 < self.contraction < 1.0:
            raise ValueError("contraction must lie in (0, 1)")

    def __call__(self, iteration: int) -> float:
        if iteration < 0:
            raise ValueError("iteration must be nonnegative")
        radius = self.initial_distance_upper * self.contraction**iteration
        path_radius = (1.0 + self.step_size * self.smoothness) * radius
        return self.model_error_at_solution + self.hessian_lipschitz * path_radius


@dataclass(frozen=True)
class BranchPointHessianSchedule:
    """Stepwise Hessian radius around a model certified at the branch point."""

    model_error_at_branch: float
    hessian_lipschitz: float
    initial_distance_upper: float
    smoothness: float
    step_size: float
    contraction: float

    def __post_init__(self) -> None:
        values = (
            self.model_error_at_branch,
            self.hessian_lipschitz,
            self.initial_distance_upper,
            self.smoothness,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("model and region constants must be nonnegative")
        if self.step_size <= 0.0:
            raise ValueError("step_size must be positive")
        if not 0.0 < self.contraction < 1.0:
            raise ValueError("contraction must lie in (0, 1)")

    def __call__(self, iteration: int) -> float:
        if iteration < 0:
            raise ValueError("iteration must be nonnegative")
        q_power = self.contraction**iteration
        radius = self.initial_distance_upper
        direct_displacement = (1.0 + q_power) * radius
        telescoping_displacement = (
            self.step_size
            * self.smoothness
            * radius
            * (1.0 - q_power)
            / (1.0 - self.contraction)
        )
        iterate_displacement = min(
            direct_displacement, telescoping_displacement
        )
        step_displacement = (
            self.step_size * self.smoothness * q_power * radius
        )
        return self.model_error_at_branch + self.hessian_lipschitz * (
            iterate_displacement + step_displacement
        )

    @property
    def uniform_radius(self) -> float:
        """A safe stationary radius for every future average Hessian."""

        region = (
            2.0 + self.step_size * self.smoothness
        ) * self.initial_distance_upper
        return self.model_error_at_branch + self.hessian_lipschitz * region


@dataclass(frozen=True)
class ChartedIterationCertificate:
    """Local quadratic-defect certificate for a smooth charted iteration."""

    nominal_contraction: float
    jacobian_lipschitz: float
    chart_radius: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.nominal_contraction < 1.0:
            raise ValueError("nominal_contraction must lie in [0, 1)")
        if self.jacobian_lipschitz < 0.0 or self.chart_radius <= 0.0:
            raise ValueError("require nonnegative Lipschitz constant and radius")
        if self.local_contraction >= 1.0:
            raise ValueError("the certified chart is not contractive")

    @property
    def quadratic_defect(self) -> float:
        """Taylor remainder coefficient ``K/2``."""

        return 0.5 * self.jacobian_lipschitz

    @property
    def local_contraction(self) -> float:
        """Norm ratio certified from the nominal map and Taylor remainder."""

        return (
            self.nominal_contraction
            + self.quadratic_defect * self.chart_radius
        )


def _matrix_at(schedule: MatrixSchedule, iteration: int) -> np.ndarray:
    if callable(schedule):
        matrix = schedule(iteration)
    else:
        array = np.asarray(schedule, dtype=float)
        if array.ndim == 2:
            matrix = array
        elif array.ndim == 3:
            if iteration >= array.shape[0]:
                raise ValueError("matrix schedule is shorter than the trajectory")
            matrix = array[iteration]
        else:
            raise ValueError("model schedule must be a matrix or matrix sequence")
    result = np.asarray(matrix, dtype=float)
    if result.ndim != 2 or result.shape[0] != result.shape[1]:
        raise ValueError("every model must be a square matrix")
    if not np.allclose(result, result.T, atol=1.0e-12, rtol=1.0e-12):
        raise ValueError("every model must be symmetric")
    return result


def _scalar_at(schedule: ScalarSchedule, iteration: int, name: str) -> float:
    if callable(schedule):
        value = schedule(iteration)
    elif np.isscalar(schedule):
        value = schedule
    else:
        if iteration >= len(schedule):
            raise ValueError(f"{name} schedule is shorter than the trajectory")
        value = schedule[iteration]
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} values must be finite")
    return result


def dynamic_krylov_envelope(
    cached_residual: np.ndarray,
    model_matrices: MatrixSchedule,
    step_size: float,
    tolerance: float,
    uncertainty_radii: ScalarSchedule,
    contraction_bounds: ScalarSchedule,
    *,
    quadratic_defect: float = 0.0,
    certified_region_radius: float | None = None,
    max_calls: int = 1_000_000,
) -> DynamicResidualTube:
    """Certify time-varying, noncommuting, mildly nonlinear dynamics.

    The optional quadratic term covers a curved local chart or retraction.
    The caller must verify its declared contracts on the full certified
    region.  If a tube leaves that region, the routine fails closed.
    """

    residual = np.asarray(cached_residual, dtype=float)
    first_model = _matrix_at(model_matrices, 0)
    if residual.ndim != 1 or residual.shape[0] != first_model.shape[0]:
        raise ValueError("cached_residual has the wrong dimension")
    if step_size <= 0.0 or tolerance <= 0.0 or max_calls < 1:
        raise ValueError("require positive step/tolerance and max_calls >= 1")
    if quadratic_defect < 0.0:
        raise ValueError("quadratic_defect must be nonnegative")
    if certified_region_radius is not None and certified_region_radius <= 0.0:
        raise ValueError("certified_region_radius must be positive")

    nominal = residual.copy()
    error = 0.0
    nominal_norms: list[float] = []
    errors: list[float] = []
    lowers: list[float] = []
    uppers: list[float] = []
    radii: list[float] = []
    contractions: list[float] = []
    lower_count: int | None = None
    upper_count: int | None = None

    for k in range(max_calls + 1):
        nominal_norm = float(np.linalg.norm(nominal))
        lower = max(0.0, nominal_norm - error)
        upper = nominal_norm + error
        if (
            certified_region_radius is not None
            and upper > certified_region_radius + 1.0e-12
        ):
            raise RuntimeError("dynamic tube left its certified local region")
        nominal_norms.append(nominal_norm)
        errors.append(error)
        lowers.append(lower)
        uppers.append(upper)
        if lower_count is None and lower <= tolerance:
            lower_count = k
        if upper <= tolerance:
            upper_count = k
            break

        model = _matrix_at(model_matrices, k)
        if model.shape != first_model.shape:
            raise ValueError("all models must have the same dimension")
        eta = _scalar_at(uncertainty_radii, k, "uncertainty radius")
        rho = _scalar_at(contraction_bounds, k, "contraction bound")
        if eta < 0.0:
            raise ValueError("uncertainty radii must be nonnegative")
        if not 0.0 <= rho < 1.0:
            raise ValueError("contraction bounds must lie in [0, 1)")
        radii.append(eta)
        contractions.append(rho)
        nominal = nominal - step_size * (model @ nominal)
        error = (
            rho * error
            + step_size * eta * nominal_norm
            + quadratic_defect * upper * upper
        )

    if upper_count is None or lower_count is None:
        raise RuntimeError("dynamic tube did not cross tolerance before max_calls")
    return DynamicResidualTube(
        envelope=CountEnvelope(lower_count, upper_count),
        nominal_residuals=np.asarray(nominal_norms),
        error_radii=np.asarray(errors),
        lower_residuals=np.asarray(lowers),
        upper_residuals=np.asarray(uppers),
        uncertainty_radii=np.asarray(radii),
        contraction_bounds=np.asarray(contractions),
        model_matvecs=upper_count,
    )


def lipschitz_hessian_schedule_from_gradient(
    initial_gradient_norm: float,
    strong_convexity: float,
    smoothness: float,
    hessian_lipschitz: float,
    step_size: float,
    contraction: float,
    *,
    model_error_at_solution: float = 0.0,
) -> LipschitzHessianSchedule:
    """Build a verifiable nonlinear-Hessian radius from a cached gradient."""

    if initial_gradient_norm < 0.0 or strong_convexity <= 0.0:
        raise ValueError("require nonnegative gradient and positive convexity")
    return LipschitzHessianSchedule(
        model_error_at_solution=model_error_at_solution,
        hessian_lipschitz=hessian_lipschitz,
        initial_distance_upper=initial_gradient_norm / strong_convexity,
        smoothness=smoothness,
        step_size=step_size,
        contraction=contraction,
    )


def branch_point_hessian_schedule_from_gradient(
    initial_gradient_norm: float,
    strong_convexity: float,
    smoothness: float,
    hessian_lipschitz: float,
    step_size: float,
    contraction: float,
    *,
    model_error_at_branch: float = 0.0,
) -> BranchPointHessianSchedule:
    """Build a dynamic radius around a model available at the current state."""

    if initial_gradient_norm < 0.0 or strong_convexity <= 0.0:
        raise ValueError("require nonnegative gradient and positive convexity")
    return BranchPointHessianSchedule(
        model_error_at_branch=model_error_at_branch,
        hessian_lipschitz=hessian_lipschitz,
        initial_distance_upper=initial_gradient_norm / strong_convexity,
        smoothness=smoothness,
        step_size=step_size,
        contraction=contraction,
    )


def composite_chart_jacobian_lipschitz(
    inner_derivative_bound: float,
    inner_jacobian_lipschitz: float,
    outer_derivative_bound: float,
    outer_jacobian_lipschitz: float,
) -> float:
    """Lipschitz bound for the Jacobian of a smooth composition.

    For ``T = outer(inner(z))``, the chain rule gives
    ``Lip(DT) <= Lip(Douter)*||Dinner||^2 + ||Douter||*Lip(Dinner)``.
    These component constants can be certified with interval automatic
    differentiation for the tangent update, chart, and retraction.
    """

    values = (
        inner_derivative_bound,
        inner_jacobian_lipschitz,
        outer_derivative_bound,
        outer_jacobian_lipschitz,
    )
    if any(value < 0.0 for value in values):
        raise ValueError("derivative bounds must be nonnegative")
    return (
        outer_jacobian_lipschitz * inner_derivative_bound**2
        + outer_derivative_bound * inner_jacobian_lipschitz
    )


def nonlinear_model_step_post_residual_upper(
    cached_residual: np.ndarray,
    model_matrix: np.ndarray,
    path_hessian_radius: float,
    *,
    damping: float = 1.0,
) -> float:
    """Bound the residual after a damped model-Newton transition.

    For ``y=x-damping*M^{-1}g`` and an average candidate-path Hessian within
    ``path_hessian_radius`` of ``M``, the bound is
    ``|1-damping|*||g|| + damping*eta*||M^{-1}g||``.
    """

    residual = np.asarray(cached_residual, dtype=float)
    model = np.asarray(model_matrix, dtype=float)
    if model.ndim != 2 or model.shape[0] != model.shape[1]:
        raise ValueError("model_matrix must be square")
    if residual.ndim != 1 or residual.shape[0] != model.shape[0]:
        raise ValueError("cached_residual has the wrong dimension")
    if path_hessian_radius < 0.0 or not 0.0 <= damping <= 1.0:
        raise ValueError("require nonnegative radius and damping in [0, 1]")
    direction = np.linalg.solve(model, residual)
    return (
        abs(1.0 - damping) * float(np.linalg.norm(residual))
        + damping * path_hessian_radius * float(np.linalg.norm(direction))
    )


def contraction_calls_from_residual_upper(
    residual_upper: float,
    tolerance: float,
    contraction: float,
) -> int:
    """Convert a residual upper bound to remaining contractive steps."""

    if residual_upper < 0.0 or tolerance <= 0.0:
        raise ValueError("require nonnegative residual and positive tolerance")
    if not 0.0 < contraction < 1.0:
        raise ValueError("contraction must lie in (0, 1)")
    if residual_upper <= tolerance:
        return 0
    raw = log(tolerance / residual_upper) / log(contraction)
    return max(0, int(ceil(raw - 1.0e-12)))


def sphere_retraction_defect_coefficient(
    step_size: float,
    maximum_spectral_gap: float,
    chart_radius: float,
    nominal_contraction: float,
) -> float:
    """Quadratic defect coefficient for normalized sphere gradient descent.

    In the graph chart around the smallest eigenvector of a symmetric
    Rayleigh-quotient problem, the exact defect is cubic.  On
    ``||z|| <= chart_radius < 1`` this returns a valid quadratic coefficient.
    """

    if step_size <= 0.0 or maximum_spectral_gap < 0.0:
        raise ValueError("require positive step and nonnegative spectral gap")
    if not 0.0 < chart_radius < 1.0:
        raise ValueError("chart_radius must lie in (0, 1)")
    if not 0.0 <= nominal_contraction < 1.0:
        raise ValueError("nominal_contraction must lie in [0, 1)")
    cubic = (
        step_size * maximum_spectral_gap
        + 0.5
        * nominal_contraction
        * step_size**2
        * maximum_spectral_gap**2
    )
    return chart_radius * cubic
