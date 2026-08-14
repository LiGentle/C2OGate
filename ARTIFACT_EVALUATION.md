# C2OGate artifact evaluation guide

## Purpose

The artifact lets an MPC Technical Editor independently check the manuscript's
proof-carrying acceptance evidence, reproduce all frozen numerical claims, and
inspect the failure semantics of the public gate. Exact verification is kept
separate from numerical SDP search.

## Requirements

- Python 3.11 or later.
- `pytest` and `ruff` for the complete audit.
- NumPy and Matplotlib for synthetic studies.
- CVXPY 1.7 or later and Clarabel for optional PEP regeneration.
- A TeX distribution with `latexmk` for manuscript reconstruction.

The frozen PEP runs were produced on macOS arm64 with Python 3.13.5, NumPy
2.5.2, and CVXPY 1.9.2. Platform details and runner hashes are embedded in the
payloads; timings are descriptive and are not used in exact acceptance proofs.

## Recommended evaluation sequence

1. Install the review environment:

       python -m pip install -e '.[pep,certificates]' pytest ruff

2. Run static, unit, integrity, and tampering checks:

       make check

3. Replay the four exact proof objects without trusting an SDP solver:

       make verify

4. Rebuild all manuscript metrics and the article PDF:

       make mpc-paper

5. Optionally regenerate the synthetic and PEP studies:

       make studies

The `make verify` target should finish quickly. The generic horizon-20
regeneration is the dominant optional task; its frozen reference run took
approximately 354 seconds on the recorded environment.

## Trust boundary

Acceptance trusts:

- the declared transcript and function-class constants;
- the small `proof_carrying_gate` aggregation kernel;
- exact structural inequalities or independently replayed proof objects;
- the complete normalized cost ledger.

Acceptance does not trust:

- a solver's `infeasible` or `inaccurate` status by itself;
- the high-precision rational-certificate generator;
- wall-clock measurements;
- an unverified or missing cell record.

An independently verified attainable bad cell returns `reject`. Every other
unresolved condition returns `uncertified`, never `accept`.

The generic horizon-20 floating audit is therefore diagnostic and has
proof-carrying outcome `uncertified`. The separate horizon-three payload
contains independently replayed rational duals for all ten cost-violating
generic cells and 100 exact positive leading-minor checks.

## Directory map

- `src/c2ogate/`: transcript, cost, certificate, and aggregation code.
- `experiments/`: frozen-study generators and manuscript-metric builder.
- `tools/`: independent standard-library verifiers.
- `tests/`: unit, integrity, and rehashed-tampering tests.
- `results/`: frozen canonical JSON study records.
- `certificates/`: exact rational SDP dual payload.
- `figures/`: manuscript figure regenerated from the finite-family audit.

## Raw market-data limitation

The unofficial SPX option-chain snapshot is not redistributed. Its CSV and
metadata hashes are recorded in the real-data payloads. The frozen rational
matrices, call counts, cost ledger, and verifier inputs needed for the article
are included. If the source snapshot is supplied to the positive verifier with
`--source-root`, the verifier independently reconstructs and matches the
data-to-matrix map.
