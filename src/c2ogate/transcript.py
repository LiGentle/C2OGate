"""Transcript-conditioned joint cost certificates.

The finite pair set used here is the discrete object produced by a joint
performance-estimation problem: every pair is a baseline/hybrid stopping-time
combination that remains possible after conditioning on the same transcript.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, order=True)
class StoppingPair:
    """One jointly attainable baseline/hybrid stopping-time pair."""

    baseline_calls: int
    hybrid_calls: int

    def __post_init__(self) -> None:
        if self.baseline_calls < 0 or self.hybrid_calls < 0:
            raise ValueError("stopping times must be nonnegative")

    @property
    def call_difference(self) -> int:
        return self.hybrid_calls - self.baseline_calls


@dataclass(frozen=True)
class TranscriptGateDecision:
    """Optimal joint gate and its independent-envelope relaxation."""

    accept_joint: bool
    accept_rectangle: bool
    worst_joint_call_difference: int
    rectangle_call_difference: int
    baseline_lower_calls: int
    hybrid_upper_calls: int
    transcript_certificate_value: float
    rectangle_certificate_value: float
    guaranteed_joint_call_slack: int
    guaranteed_joint_cost_slack: float
    minimum_saved_calls: int
    cost_exact_units: float
    pair_count: int


def transcript_optimal_gate(
    attainable_pairs: Iterable[StoppingPair | tuple[int, int]],
    cost_exact_units: float,
    *,
    minimum_saved_calls: int = 1,
) -> TranscriptGateDecision:
    """Compare the exact joint gate with the rectangular interval gate.

    Relative to the supplied transcript-conditioned pair set, the joint gate
    is the largest deterministic acceptance rule that guarantees both
    ``N_y <= N_x-m`` and ``cost + N_y <= N_x`` for every consistent instance.
    """

    if cost_exact_units < 0.0:
        raise ValueError("cost_exact_units must be nonnegative")
    if minimum_saved_calls < 0:
        raise ValueError("minimum_saved_calls must be nonnegative")
    pairs = tuple(
        pair if isinstance(pair, StoppingPair) else StoppingPair(*pair)
        for pair in attainable_pairs
    )
    if not pairs:
        raise ValueError("the attainable pair set cannot be empty")

    worst_joint = max(pair.call_difference for pair in pairs)
    baseline_lower = min(pair.baseline_calls for pair in pairs)
    hybrid_upper = max(pair.hybrid_calls for pair in pairs)
    rectangle = hybrid_upper - baseline_lower
    certificate_value = worst_joint + max(
        float(minimum_saved_calls), cost_exact_units
    )
    rectangle_certificate = rectangle + max(
        float(minimum_saved_calls), cost_exact_units
    )
    joint_safe = certificate_value <= 1.0e-12
    rectangle_safe = rectangle_certificate <= 1.0e-12
    return TranscriptGateDecision(
        accept_joint=bool(joint_safe),
        accept_rectangle=bool(rectangle_safe),
        worst_joint_call_difference=int(worst_joint),
        rectangle_call_difference=int(rectangle),
        baseline_lower_calls=int(baseline_lower),
        hybrid_upper_calls=int(hybrid_upper),
        transcript_certificate_value=float(certificate_value),
        rectangle_certificate_value=float(rectangle_certificate),
        guaranteed_joint_call_slack=int(-minimum_saved_calls - worst_joint),
        guaranteed_joint_cost_slack=float(-cost_exact_units - worst_joint),
        minimum_saved_calls=int(minimum_saved_calls),
        cost_exact_units=float(cost_exact_units),
        pair_count=len(pairs),
    )
