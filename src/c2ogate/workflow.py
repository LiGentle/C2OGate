"""Proof-carrying aggregation for joint stopping-cell certificates.

This module deliberately does not trust a numerical solver status.  It combines
independently verified cell proof objects into the public three-valued C2OGate
decision described in the MPC manuscript.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class GateOutcome(str, Enum):
    """Public outcome of the proof-carrying gate."""

    ACCEPT = "accept"
    REJECT = "reject"
    UNCERTIFIED = "uncertified"


class CellProofStatus(str, Enum):
    """Meaning of one independently checkable bad-cell proof object."""

    EXCLUDED = "excluded"
    ATTAINABLE = "attainable"
    UNCERTIFIED = "uncertified"


@dataclass(frozen=True)
class CellProof:
    """Verification result for one joint stopping-time cell."""

    baseline_calls: int
    candidate_calls: int
    status: CellProofStatus
    independently_verified: bool

    def __post_init__(self) -> None:
        if self.baseline_calls < 0 or self.candidate_calls < 0:
            raise ValueError("cell stopping times must be nonnegative")

    @property
    def pair(self) -> tuple[int, int]:
        return self.baseline_calls, self.candidate_calls


@dataclass(frozen=True)
class ProofCarryingDecision:
    """Auditable aggregate of the required bad-cell proof objects."""

    outcome: GateOutcome
    reason: str
    bad_cell_count: int
    excluded_count: int
    witnessed_count: int
    uncertified_count: int
    cost_exact_units: float
    minimum_saved_calls: int
    horizon: int


def _is_bad_cell(
    baseline_calls: int,
    candidate_calls: int,
    *,
    cost_exact_units: float,
    minimum_saved_calls: int,
) -> bool:
    return (
        candidate_calls > baseline_calls - minimum_saved_calls
        or cost_exact_units + candidate_calls > baseline_calls
    )


def proof_carrying_gate(
    cell_proofs: Iterable[CellProof],
    cost_exact_units: float,
    *,
    minimum_saved_calls: int = 1,
    horizon: int,
    cost_ledger_verified: bool = True,
) -> ProofCarryingDecision:
    """Aggregate bad-cell proofs without promoting numerical uncertainty.

    ``ACCEPT`` requires an independently verified exclusion for every
    cost-violating cell in ``{0, ..., horizon}^2`` and a verified all-in cost
    ledger.  An independently verified attainable bad cell returns ``REJECT``.
    Missing cells, failed verification, or explicitly uncertified cells return
    ``UNCERTIFIED``.
    """

    if cost_exact_units < 0.0:
        raise ValueError("cost_exact_units must be nonnegative")
    if minimum_saved_calls < 0:
        raise ValueError("minimum_saved_calls must be nonnegative")
    if horizon < 0:
        raise ValueError("horizon must be nonnegative")

    required = {
        (baseline, candidate)
        for baseline in range(horizon + 1)
        for candidate in range(horizon + 1)
        if _is_bad_cell(
            baseline,
            candidate,
            cost_exact_units=cost_exact_units,
            minimum_saved_calls=minimum_saved_calls,
        )
    }
    provided: dict[tuple[int, int], CellProof] = {}
    for proof in cell_proofs:
        if proof.baseline_calls > horizon or proof.candidate_calls > horizon:
            raise ValueError("cell proof lies outside the declared horizon")
        if proof.pair not in required:
            raise ValueError("proof supplied for a cell that is not cost-violating")
        if proof.pair in provided:
            raise ValueError("duplicate proof for one stopping-time cell")
        provided[proof.pair] = proof

    witnessed = sum(
        proof.independently_verified
        and proof.status is CellProofStatus.ATTAINABLE
        for proof in provided.values()
    )
    excluded = sum(
        proof.independently_verified
        and proof.status is CellProofStatus.EXCLUDED
        for proof in provided.values()
    )
    unresolved = required - provided.keys()
    unverified = sum(
        (not proof.independently_verified)
        or proof.status is CellProofStatus.UNCERTIFIED
        for proof in provided.values()
    )
    uncertified = len(unresolved) + unverified

    if witnessed:
        return ProofCarryingDecision(
            outcome=GateOutcome.REJECT,
            reason="an independently verified cost-violating cell is attainable",
            bad_cell_count=len(required),
            excluded_count=excluded,
            witnessed_count=witnessed,
            uncertified_count=uncertified,
            cost_exact_units=float(cost_exact_units),
            minimum_saved_calls=minimum_saved_calls,
            horizon=horizon,
        )
    if not cost_ledger_verified:
        uncertified += 1
    if excluded == len(required) and uncertified == 0:
        outcome = GateOutcome.ACCEPT
        reason = "every cost-violating cell is independently excluded"
    else:
        outcome = GateOutcome.UNCERTIFIED
        reason = "at least one bad cell or the all-in cost ledger is uncertified"
    return ProofCarryingDecision(
        outcome=outcome,
        reason=reason,
        bad_cell_count=len(required),
        excluded_count=excluded,
        witnessed_count=0,
        uncertified_count=uncertified,
        cost_exact_units=float(cost_exact_units),
        minimum_saved_calls=minimum_saved_calls,
        horizon=horizon,
    )
