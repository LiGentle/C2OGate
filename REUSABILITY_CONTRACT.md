# C2OGate reusability contract

C2OGate separates a branch decision from the numerical method used to search
for certificates.  The stable public boundary is deliberately small:

- `TranscriptConstraintSpec` declares every transcript relation before model
  construction. Only exact affine Gram/function-value rows, or an exact lift
  verified by the caller, are admitted.
- A problem-specific enumerator determines the finite horizon and every
  cost-violating stopping pair.
- A producer returns one `CellProof` per required pair. The producer may use
  any solver, but a solver status is not a verified exclusion.
- `certified_branch_workflow` validates the interface and passes verified cell
  results to the solver-independent three-valued aggregator.
- The ledger supplies all proposal, search, verification, and rejected-work
  costs in exact-oracle units.

The current rational SDP consumer implements fixed-step gradient descent on
smooth strongly convex functions. A different stopping rule for that same
continuation can reuse the interpolation rows, exact arithmetic, hashing, and
aggregator after supplying new exact terminal/survival rows. A new function
class or continuation map needs a new semantic coefficient builder and an
independent verifier. It must use a new schema name; relabeling an existing
payload is not supported.

## Minimal extension path

1. Prove a finite horizon for the intended stopping rule.
2. Express every transcript and stopping predicate as exact named affine rows.
3. Enumerate all pairs violating the call-saving or monetary requirement.
4. Emit a `CellProof` only after the problem-specific consumer has replayed
   the certificate against coefficients reconstructed from semantic inputs.
5. Call `certified_branch_workflow` with the complete ledger.

The executable example in `examples/reuse_custom_stopping_rule.py` shows the
last two steps without importing CVXPY or a solver. In a real extension, its
small `verified_cell_producer` callback is replaced by the new exact consumer.

```python
from c2ogate import (
    CellProof,
    CellProofStatus,
    TranscriptConstraintForm,
    TranscriptConstraintSpec,
    certified_branch_workflow,
)

constraints = [
    TranscriptConstraintSpec(
        "custom_terminal_rule",
        TranscriptConstraintForm.AFFINE_GRAM,
    )
]

def verified_cell_producer():
    # Horizon 1, one-call saving, and cost 1/4 require these three cells.
    return [
        CellProof(r, s, CellProofStatus.EXCLUDED, independently_verified=True)
        for r, s in ((0, 0), (0, 1), (1, 1))
    ]

decision = certified_branch_workflow(
    constraints,
    verified_cell_producer,
    cost_exact_units=0.25,
    minimum_saved_calls=1,
    horizon=1,
)
assert decision.outcome.value == "accept"
```

Unsupported syntax fails closed before the producer is called:

```python
unsupported = [
    TranscriptConstraintSpec(
        "nonlinear_line_search",
        TranscriptConstraintForm.NONAFFINE,
    )
]
decision = certified_branch_workflow(
    unsupported,
    lambda: (_ for _ in ()).throw(RuntimeError("must not run")),
    cost_exact_units=0.25,
    horizon=1,
)
assert decision.outcome.value == "uncertified"
```

This contract promises stable decision and failure semantics, not automatic
scaling beyond the verified moderate-horizon envelope.
