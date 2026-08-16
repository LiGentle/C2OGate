"""Exact binary64-to-rational transcript membership checks.

The optional numerical producers may use NumPy, but an acceptance decision
must not depend on a rounded norm comparison.  This module treats every stored
binary64 datum as the exact rational number represented by that datum and uses
``fractions.Fraction`` for all affine combinations and squared norms.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Sequence


RationalVector = tuple[Fraction, ...]


def binary64_vector(values: Iterable[float]) -> RationalVector:
    """Return the exact rationals represented by a binary64 vector."""

    return tuple(Fraction.from_float(float(value)) for value in values)


def rational_squared_norm(values: Sequence[Fraction]) -> Fraction:
    """Compute a squared Euclidean norm without rounding."""

    return sum((value * value for value in values), start=Fraction(0))


def exact_linear_data_gradient(
    features: Iterable[Sequence[float]],
    labels: Sequence[float],
    loss_scale: Fraction,
) -> RationalVector:
    """Compute the logistic data gradient at the origin exactly.

    For labels in ``{0,1}``, the data contribution is
    ``loss_scale * mean(a_i * (1/2-b_i))``.  Feature entries are interpreted as
    the exact binary64 values stored by the runner.
    """

    rows = list(features)
    if not rows or len(rows) != len(labels):
        raise ValueError("features and labels must be nonempty and aligned")
    dimension = len(rows[0])
    if dimension == 0 or any(len(row) != dimension for row in rows):
        raise ValueError("feature rows must have a common positive dimension")
    totals = [Fraction(0) for _ in range(dimension)]
    for row, label in zip(rows, labels, strict=True):
        label_fraction = Fraction.from_float(float(label))
        weight = Fraction(1, 2) - label_fraction
        if weight not in (Fraction(-1, 2), Fraction(1, 2)):
            raise ValueError("labels must be binary")
        for index, value in enumerate(row):
            totals[index] += Fraction.from_float(float(value)) * weight
    scale = loss_scale / len(rows)
    return tuple(scale * value for value in totals)


def exact_max_row_squared_norm(
    features: Iterable[Sequence[float]],
) -> Fraction:
    """Return the exact maximum squared row norm of binary64 data."""

    maximum = Fraction(0)
    found = False
    for row in features:
        found = True
        maximum = max(maximum, rational_squared_norm(binary64_vector(row)))
    if not found:
        raise ValueError("features must be nonempty")
    return maximum


@dataclass(frozen=True)
class ExactEnvelopeMembership:
    """Exact result for the transcript inequalities used by the H=6 gate."""

    accepted: bool
    proposal_squared_norm: Fraction
    residual_squared_norm: Fraction
    gradient_squared_norm: Fraction
    proposal_band_passed: bool
    residual_ball_passed: bool
    distance_bound_passed: bool


def certify_h6_envelope_membership(
    candidate: Sequence[float],
    exact_gradient: Sequence[Fraction],
    *,
    proposal_step: Fraction,
    proposal_lower: Fraction,
    proposal_upper: Fraction,
    contract_radius: Fraction,
    strong_monotonicity: Fraction,
    distance_upper: Fraction,
) -> ExactEnvelopeMembership:
    """Check the H=6 proposal contract using exact rational arithmetic."""

    candidate_rational = binary64_vector(candidate)
    gradient_rational = tuple(exact_gradient)
    if len(candidate_rational) != len(gradient_rational):
        raise ValueError("candidate and gradient dimensions must agree")
    residual = tuple(
        point + proposal_step * gradient
        for point, gradient in zip(
            candidate_rational, gradient_rational, strict=True
        )
    )
    proposal_squared = rational_squared_norm(candidate_rational)
    residual_squared = rational_squared_norm(residual)
    gradient_squared = rational_squared_norm(gradient_rational)
    proposal_passed = (
        proposal_lower * proposal_lower
        <= proposal_squared
        <= proposal_upper * proposal_upper
    )
    residual_passed = residual_squared <= contract_radius * contract_radius
    distance_passed = gradient_squared <= (
        strong_monotonicity * distance_upper
    ) ** 2
    return ExactEnvelopeMembership(
        accepted=proposal_passed and residual_passed and distance_passed,
        proposal_squared_norm=proposal_squared,
        residual_squared_norm=residual_squared,
        gradient_squared_norm=gradient_squared,
        proposal_band_passed=proposal_passed,
        residual_ball_passed=residual_passed,
        distance_bound_passed=distance_passed,
    )
