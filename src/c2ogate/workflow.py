"""Proof-carrying aggregation for joint stopping-cell certificates.

This module deliberately does not trust a numerical solver status.  It combines
independently verified cell proof objects into the public three-valued C2OGate
decision described in the MPC manuscript.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable
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


class TranscriptConstraintForm(str, Enum):
    """Representation exposed by one transcript constraint to the PEP layer."""

    AFFINE_GRAM = "affine_gram"
    EXACT_AFFINE_LIFT = "exact_affine_lift"
    NONAFFINE = "nonaffine"


@dataclass(frozen=True)
class TranscriptConstraintSpec:
    """Machine-checkable interface declaration for one transcript constraint.

    ``AFFINE_GRAM`` constraints must have exact rational coefficients in the
    sampled function values and Gram entries.  ``EXACT_AFFINE_LIFT`` is
    admitted only when the caller also supplies an independently verified
    exact lifting.  All other nonlinear predicates fail closed.
    """

    name: str
    form: TranscriptConstraintForm
    exact_coefficients: bool = True
    exact_lift_verified: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("transcript constraint name cannot be empty")


@dataclass(frozen=True)
class TranscriptInterfaceAdmission:
    """Pre-solver admission decision for a transcript interface."""

    admitted: bool
    reason: str
    rejected_constraints: tuple[str, ...]


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


def validate_transcript_interface(
    constraints: Iterable[TranscriptConstraintSpec],
) -> TranscriptInterfaceAdmission:
    """Admit only exactly represented affine Gram/function-value constraints.

    This check belongs before numerical model construction.  It never drops an
    unsupported predicate: a nonaffine relation, inexact coefficient set, or
    unverified lifting rejects the interface and leaves the continuation decision
    ``UNCERTIFIED``.
    """

    rejected: list[str] = []
    for constraint in constraints:
        affine = constraint.form is TranscriptConstraintForm.AFFINE_GRAM
        lifted = (
            constraint.form is TranscriptConstraintForm.EXACT_AFFINE_LIFT
            and constraint.exact_lift_verified
        )
        if not constraint.exact_coefficients or not (affine or lifted):
            rejected.append(constraint.name)
    names = tuple(rejected)
    if names:
        return TranscriptInterfaceAdmission(
            admitted=False,
            reason=(
                "transcript interface rejected before model construction: "
                "unsupported or nonexact constraint(s): " + ", ".join(names)
            ),
            rejected_constraints=names,
        )
    return TranscriptInterfaceAdmission(
        admitted=True,
        reason="every transcript constraint has an exact affine representation",
        rejected_constraints=(),
    )


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
    ledger.  An independently verified attainable cell that violates the
    requested call reduction returns ``REJECT`` even if the monetary ledger is
    unavailable.  A cell that is bad only because of monetary cost returns
    ``REJECT`` only with a verified ledger; otherwise it is ``UNCERTIFIED``.
    Missing cells, failed verification, or explicitly uncertified cells also
    return ``UNCERTIFIED``.
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

    witnessed_proofs = [
        proof
        for proof in provided.values()
        if proof.independently_verified
        and proof.status is CellProofStatus.ATTAINABLE
    ]
    witnessed = len(witnessed_proofs)
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

    witnessed_call_violation = any(
        proof.candidate_calls
        > proof.baseline_calls - minimum_saved_calls
        for proof in witnessed_proofs
    )
    if witnessed and (cost_ledger_verified or witnessed_call_violation):
        return ProofCarryingDecision(
            outcome=GateOutcome.REJECT,
            reason=(
                "an independently verified call-violating cell is attainable"
                if witnessed_call_violation and not cost_ledger_verified
                else "an independently verified cost-violating cell is attainable"
            ),
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
        reason = (
            f"verified exclusions cover {excluded}/{len(required)} bad cells; "
            "at least one bad cell or the all-in cost ledger is uncertified"
        )
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


def certified_branch_workflow(
    interface_constraints: Iterable[TranscriptConstraintSpec],
    proof_producer: Callable[[], Iterable[CellProof]],
    cost_exact_units: float,
    *,
    minimum_saved_calls: int = 1,
    horizon: int,
    cost_ledger_verified: bool = True,
) -> ProofCarryingDecision:
    """Run the proof producer only after the transcript passes preflight.

    The callback boundary makes the fail-closed path observable: unsupported
    nonaffine input returns ``UNCERTIFIED`` without constructing or solving an
    SDP.  ``REJECT`` remains reserved for an independently verified attainable
    bad cell.
    """

    if cost_exact_units < 0.0:
        raise ValueError("cost_exact_units must be nonnegative")
    if minimum_saved_calls < 0:
        raise ValueError("minimum_saved_calls must be nonnegative")
    if horizon < 0:
        raise ValueError("horizon must be nonnegative")
    admission = validate_transcript_interface(interface_constraints)
    if not admission.admitted:
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
        return ProofCarryingDecision(
            outcome=GateOutcome.UNCERTIFIED,
            reason=admission.reason,
            bad_cell_count=len(required),
            excluded_count=0,
            witnessed_count=0,
            uncertified_count=len(required) + 1,
            cost_exact_units=float(cost_exact_units),
            minimum_saved_calls=minimum_saved_calls,
            horizon=horizon,
        )
    return proof_carrying_gate(
        proof_producer(),
        cost_exact_units,
        minimum_saved_calls=minimum_saved_calls,
        horizon=horizon,
        cost_ledger_verified=cost_ledger_verified,
    )
