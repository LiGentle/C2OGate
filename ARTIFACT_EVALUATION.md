# C2OGate artifact evaluation guide

## Purpose

The artifact lets an MPC Technical Editor independently check the manuscript's
proof-carrying acceptance evidence, reproduce all frozen numerical claims, and
inspect the failure semantics of the public gate. Exact verification is kept
separate from numerical SDP search.

## Requirements

- Python 3.11 or later.
- `pytest` 8.3.5 and `ruff` 0.12.10 for the complete audit.
- NumPy and Matplotlib for synthetic studies.
- CVXPY 1.9.2, Clarabel, SCS, PEPit 0.5.1, and SymPy 1.14.0 for optional PEP
  regeneration, rational recovery, and backend comparisons.
- A TeX distribution with `latexmk` for manuscript reconstruction.

The frozen PEP runs were produced on macOS arm64 with Python 3.13.5, NumPy
2.5.2, and CVXPY 1.9.2. Platform details and runner hashes are embedded in the
payloads; timings are descriptive and are not used in exact acceptance proofs.

## Recommended evaluation sequence

1. Install the review environment:

       python -m pip install -e '.[pep,certificates,dev]'

   Or use the supplied Conda specification:

       conda env create -f environment.yml
       conda activate c2ogate-mpc

2. Run static, unit, integrity, and tampering checks:

       make check

3. Replay the seven exact proof objects without trusting an SDP solver:

       make verify

4. Rebuild all manuscript metrics and the article PDF:

       make mpc-paper

5. Optionally regenerate the synthetic and PEP studies:

       make studies

The natural-$H=10$ verifier performs exact rational $LDL^\top$ elimination for
66 order-24 slack matrices and can take several minutes.  It uses only the
Python standard library and never calls an SDP solver.  The generic horizon-20
regeneration is also a multi-minute optional task; timings are recorded rather
than asserted as portable constants.

To reproduce the flagship cost ledger on the review machine, run:

       make h10-certificate-cost-study

The command performs one complete exact replay, adds it to the generator's
frozen search-and-recovery wall time, and computes prepaid-reuse thresholds
from the remaining $0.6$-call certificate budget.  This timing is descriptive;
the verifier's exact arithmetic result is the proof.

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

The public aggregate also reports proof progress. If exact recovery or replay
excludes only `k` of `n` required bad cells, the outcome is `uncertified` and
the reason contains `verified exclusions cover k/n bad cells`. This is useful
operational telemetry, not a partial-acceptance rule.

The generic horizon-20 floating audit is therefore diagnostic and has
proof-carrying outcome `uncertified`.  The flagship natural-horizon-ten suite
contains independently replayed rational duals for all 66 cost-violating
generic cells and 1,584 exact positive $LDL^\top$ pivots.  The separate
payload records, for every cell, the prefix actually visited in the fixed
two-regularizer by five-threshold recovery grid. These records measure the
heuristic producer; they are not inputs to the mathematical acceptance proof.
The frozen run makes 69 attempts: 65 cells succeed at the first configuration,
one succeeds at the fourth after three failed attempts, and six configurations
are never reached. The final independently replayable coverage is 66/66.
The separate
full-class joint-only suite excludes ten bad cells over the infinite
$\mathcal F_{1/2,1}$ transcript class, checks 100 positive exact pivots, and
proves that sharp independent marginals reject.  The separate
two-dimensional nonquadratic payload has formula-derived horizon H0=2; its
one-layer-padded horizon-three audit remains an independent realization
cross-check.

## Exact Gram assembly record

Let `v_1,...,v_p` denote the vector atoms and let `a(z)` be the coefficient
vector satisfying `z = sum_l a_l(z) v_l`. The implementation uses

    <u,v> = a(u)^T G a(v),
    ||u-v||^2 = (a(u)-a(v))^T G (a(u)-a(v)),

with `a(x)=0` and

    a(x_k) = -alpha sum_{t<k} a(g_t^x),
    a(y_k) = a(y) - alpha sum_{t<k} a(g_t^y).

Consequently every interpolation, distance, contract, and stopping row is
affine in `G`. For example, the proposal contract is
`(a(y)+gamma a(g_0^x))^T G (a(y)+gamma a(g_0^x)) <= delta^2`.
The independent consumers reconstruct these coefficients instead of trusting
stored matrices.

## Ancillary policy accounting

These audits were moved from the article because they concern mean-cost
policies rather than the joint class-wide certificate. For one deterministic
member of each 40-member finite proxy family, the policy ratios are:

| Policy | Mean ratio | Median ratio | Worse than baseline |
|---|---:|---:|---:|
| Exact only | 1.000 | 1.000 | 0.0% |
| Joint certificate | 0.995 | 1.000 | 0.0% |
| Four-bin certificate | 0.997 | 1.000 | 0.0% |
| Two-bin certificate | 0.998 | 1.000 | 0.0% |
| Rectangular certificate | 0.999 | 1.000 | 0.0% |
| Always query | 0.993 | 0.994 | 24.1% |

The comparison treats the pair-set certificate as already prepaid and hence
does not bypass the manuscript's zero-credit obstruction. In the separate
2,000-case dimension-64 safety--mean audit, the certified marginal gate accepts
349 cases (17.4%), has mean ratio 0.939, and is never worse than the baseline.
Always query has mean ratio 0.729 but is worse than the exact baseline in 2.6%
of cases. Thus deterministic dominance is a tail-safety specification rather
than an estimator of the mean-optimal policy.

## Directory map

- `src/c2ogate/`: transcript, cost, certificate, and aggregation code.
- `experiments/`: frozen-study generators and manuscript-metric builder.
- `tools/`: independent standard-library verifiers.
- `tests/`: unit, integrity, and rehashed-tampering tests.
- `results/`: frozen canonical JSON study records.
- `certificates/`: exact rational SDP dual payload.
- `figures/`: manuscript figures regenerated from the finite-family and
  repeated backend audits.
- `data/`: redistributable synthetic raw option rows used to test the complete
  filter-to-rational-matrix transformation.
- `environment.yml`: Conda specification for the complete review environment.

## Raw market-data limitation

The unofficial SPX option-chain snapshot is not redistributed. Its CSV and
metadata hashes are recorded in the real-data payloads. The frozen rational
matrices, call counts, cost ledger, and verifier inputs needed for the article
are included. If the source snapshot is supplied to the positive verifier with
`--source-root`, the verifier independently reconstructs and matches the
data-to-matrix map.  A 20-row synthetic substitute is redistributed and
exercises that same independent map against frozen rational outputs, so a
clean checkout tests the implementation path without claiming to recreate the
unavailable market observations.
