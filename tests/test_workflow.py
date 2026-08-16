import pytest

from c2ogate.workflow import (
    CellProof,
    CellProofStatus,
    GateOutcome,
    TranscriptConstraintForm,
    TranscriptConstraintSpec,
    certified_branch_workflow,
    proof_carrying_gate,
    validate_transcript_interface,
)


def _bad_pairs(horizon: int, cost: float, minimum_saved_calls: int = 1):
    return {
        (r, s)
        for r in range(horizon + 1)
        for s in range(horizon + 1)
        if s > r - minimum_saved_calls or cost + s > r
    }


def test_accept_requires_every_verified_exclusion():
    bad = _bad_pairs(2, 0.5)
    proofs = [
        CellProof(r, s, CellProofStatus.EXCLUDED, independently_verified=True)
        for r, s in bad
    ]
    decision = proof_carrying_gate(proofs, 0.5, horizon=2)
    assert decision.outcome is GateOutcome.ACCEPT
    assert decision.excluded_count == len(bad)
    assert decision.uncertified_count == 0


def test_verified_attainable_bad_cell_rejects_immediately():
    proof = CellProof(0, 0, CellProofStatus.ATTAINABLE, True)
    decision = proof_carrying_gate([proof], 0.5, horizon=2)
    assert decision.outcome is GateOutcome.REJECT
    assert decision.witnessed_count == 1


def test_unverified_ledger_distinguishes_call_and_cost_only_witnesses():
    cost_only = proof_carrying_gate(
        [CellProof(1, 1, CellProofStatus.ATTAINABLE, True)],
        0.5,
        minimum_saved_calls=0,
        horizon=1,
        cost_ledger_verified=False,
    )
    assert cost_only.outcome is GateOutcome.UNCERTIFIED
    call_violation = proof_carrying_gate(
        [CellProof(1, 1, CellProofStatus.ATTAINABLE, True)],
        0.5,
        minimum_saved_calls=1,
        horizon=1,
        cost_ledger_verified=False,
    )
    assert call_violation.outcome is GateOutcome.REJECT
    assert "call-violating" in call_violation.reason


@pytest.mark.parametrize(
    "proofs,ledger_verified",
    [
        ([], True),
        ([CellProof(0, 0, CellProofStatus.EXCLUDED, False)], True),
        ([CellProof(0, 0, CellProofStatus.UNCERTIFIED, True)], True),
        ([], False),
    ],
)
def test_missing_unverified_or_unresolved_evidence_is_uncertified(
    proofs, ledger_verified
):
    decision = proof_carrying_gate(
        proofs,
        0.5,
        horizon=1,
        cost_ledger_verified=ledger_verified,
    )
    assert decision.outcome is GateOutcome.UNCERTIFIED
    assert decision.uncertified_count > 0
    assert f"{decision.excluded_count}/{decision.bad_cell_count}" in decision.reason


def test_rejects_duplicate_nonbad_and_out_of_horizon_proofs():
    proof = CellProof(0, 0, CellProofStatus.EXCLUDED, True)
    with pytest.raises(ValueError, match="duplicate"):
        proof_carrying_gate([proof, proof], 0.5, horizon=1)
    with pytest.raises(ValueError, match="not cost-violating"):
        proof_carrying_gate(
            [CellProof(1, 0, CellProofStatus.EXCLUDED, True)],
            0.0,
            minimum_saved_calls=0,
            horizon=1,
        )
    with pytest.raises(ValueError, match="outside"):
        proof_carrying_gate(
            [CellProof(2, 2, CellProofStatus.EXCLUDED, True)],
            0.5,
            horizon=1,
        )


def test_affine_interface_is_admitted_and_exact_lift_must_be_verified():
    admission = validate_transcript_interface(
        [
            TranscriptConstraintSpec(
                "proposal_contract", TranscriptConstraintForm.AFFINE_GRAM
            ),
            TranscriptConstraintSpec(
                "lifted_relation",
                TranscriptConstraintForm.EXACT_AFFINE_LIFT,
                exact_lift_verified=True,
            ),
        ]
    )
    assert admission.admitted
    failed = validate_transcript_interface(
        [
            TranscriptConstraintSpec(
                "unverified_lift", TranscriptConstraintForm.EXACT_AFFINE_LIFT
            )
        ]
    )
    assert not failed.admitted
    assert failed.rejected_constraints == ("unverified_lift",)


def test_nonaffine_interface_fails_closed_before_proof_production():
    producer_called = False

    def producer():
        nonlocal producer_called
        producer_called = True
        raise AssertionError("proof producer must not run")

    decision = certified_branch_workflow(
        [
            TranscriptConstraintSpec(
                "nonlinear_line_search", TranscriptConstraintForm.NONAFFINE
            )
        ],
        producer,
        0.5,
        horizon=2,
    )
    assert decision.outcome is GateOutcome.UNCERTIFIED
    assert not producer_called
    assert decision.excluded_count == 0
    assert "before model construction" in decision.reason
