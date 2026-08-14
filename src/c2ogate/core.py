"""Information-robust accounting for a cheap oracle and an exact baseline.

The gate deliberately uses only *ex-ante* certified envelopes.  A test made
after paying for an exploratory oracle cannot, by itself, guarantee dominance
over a baseline that did not pay that sunk cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log


@dataclass(frozen=True)
class CountEnvelope:
    """Certified lower and upper bounds on remaining exact calls."""

    lower: int
    upper: int

    def __post_init__(self) -> None:
        if self.lower < 0 or self.upper < self.lower:
            raise ValueError("require 0 <= lower <= upper")


@dataclass(frozen=True)
class GateDecision:
    """Decision and guarantees implied by the robust interval gate."""

    accept: bool
    baseline_lower_calls: int
    post_upper_calls: int
    cheap_cost_exact_units: float
    guaranteed_saved_exact_calls: int
    guaranteed_cost_slack_exact_units: float
    minimum_saved_calls: int


def robust_cost_gate(
    baseline_lower_calls: int,
    post_upper_calls: int,
    cheap_cost_exact_units: float,
    *,
    minimum_saved_calls: int = 1,
    atol: float = 1.0e-12,
) -> GateDecision:
    """Apply the necessary-and-sufficient interval-robust pre-query gate.

    The inputs mean

    ``baseline_lower_calls <= actual baseline calls`` and
    ``actual post-oracle baseline calls <= post_upper_calls``.

    With no other information, accepting is robustly safe exactly when the
    worst admissible post cost fits below the best admissible baseline cost,
    and the required integer reduction in exact calls also holds.
    """

    if baseline_lower_calls < 0 or post_upper_calls < 0:
        raise ValueError("call bounds must be nonnegative")
    if cheap_cost_exact_units < 0.0:
        raise ValueError("cheap oracle cost must be nonnegative")
    if minimum_saved_calls < 0:
        raise ValueError("minimum_saved_calls must be nonnegative")

    saved = baseline_lower_calls - post_upper_calls
    slack = float(saved) - float(cheap_cost_exact_units)
    accept = saved >= minimum_saved_calls and slack >= -atol
    return GateDecision(
        accept=accept,
        baseline_lower_calls=baseline_lower_calls,
        post_upper_calls=post_upper_calls,
        cheap_cost_exact_units=float(cheap_cost_exact_units),
        guaranteed_saved_exact_calls=saved,
        guaranteed_cost_slack_exact_units=slack,
        minimum_saved_calls=minimum_saved_calls,
    )


def _steps_to_cross(residual: float, tolerance: float, factor: float) -> int:
    if residual <= tolerance:
        return 0
    if not 0.0 < factor < 1.0:
        raise ValueError("factor must lie strictly between zero and one")
    raw = log(tolerance / residual) / log(factor)
    return max(0, int(ceil(raw - 1.0e-12)))


def contraction_count_envelope(
    residual: float,
    tolerance: float,
    lower_factor: float,
    upper_factor: float,
) -> CountEnvelope:
    """Convert a two-sided one-step contraction into a call-count envelope.

    If every exact step satisfies

    ``lower_factor * r_k <= r_{k+1} <= upper_factor * r_k``,

    then the returned lower/upper integers enclose the number of exact steps
    needed to first reach ``residual <= tolerance``.
    """

    if residual < 0.0 or tolerance <= 0.0:
        raise ValueError("require residual >= 0 and tolerance > 0")
    if not 0.0 < lower_factor <= upper_factor < 1.0:
        raise ValueError(
            "require 0 < lower_factor <= upper_factor < 1"
        )
    if residual <= tolerance:
        return CountEnvelope(0, 0)
    return CountEnvelope(
        lower=_steps_to_cross(residual, tolerance, lower_factor),
        upper=_steps_to_cross(residual, tolerance, upper_factor),
    )
