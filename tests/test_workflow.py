import pytest

from c2ogate.workflow import (
    CellProof,
    CellProofStatus,
    GateOutcome,
    proof_carrying_gate,
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
