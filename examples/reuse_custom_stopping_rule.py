"""Minimal consumer-side extension of the C2OGate workflow."""

from c2ogate import (
    CellProof,
    CellProofStatus,
    GateOutcome,
    TranscriptConstraintForm,
    TranscriptConstraintSpec,
    certified_branch_workflow,
)


def run_example():
    """Return a complete horizon-one decision from verified cell results."""

    constraints = [
        TranscriptConstraintSpec(
            "custom_terminal_rule",
            TranscriptConstraintForm.AFFINE_GRAM,
        )
    ]

    def verified_cell_producer():
        return [
            CellProof(r, s, CellProofStatus.EXCLUDED, independently_verified=True)
            for r, s in ((0, 0), (0, 1), (1, 1))
        ]

    return certified_branch_workflow(
        constraints,
        verified_cell_producer,
        cost_exact_units=0.25,
        minimum_saved_calls=1,
        horizon=1,
    )


if __name__ == "__main__":
    result = run_example()
    assert result.outcome is GateOutcome.ACCEPT
    print(result.outcome.value)
