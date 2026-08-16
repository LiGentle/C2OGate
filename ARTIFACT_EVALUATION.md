# C2OGate artifact evaluation guide

## Purpose

The artifact lets an MPC Technical Editor independently check the manuscript's
rational acceptance certificates, reproduce all frozen numerical claims, and
inspect the failure semantics of the public gate. Exact verification is kept
separate from numerical SDP search.

## Requirements

- Python 3.11 or later.
- `pytest` 8.3.5 and `ruff` 0.12.10 for the complete audit.
- NumPy and Matplotlib for synthetic studies.
- NumPy 2.4.6, CVXPY 1.9.2, Clarabel 0.11.1, SCS 3.2.11, PEPit 0.5.1, and
  SymPy 1.14.0 for optional PEP
  regeneration, rational recovery, and backend comparisons.
- A TeX distribution with `latexmk` for manuscript reconstruction.

The principal certificate, backend, and rolling-workload payloads were produced
on macOS arm64 with Python 3.11.15, NumPy 2.4.6, and CVXPY 1.9.2. Ancillary
payloads retain their own environment strings. Platform details and runner
hashes are embedded per payload; timings are descriptive and are not used in
exact acceptance proofs.
The same-model comparison pins `PEPit==0.5.1` through the `pep` optional extra.
Its frozen distribution metadata records installer `uv`, the official
documentation, PyPI release page, GitHub project, and tagged source URL. The
installation contains no `direct_url.json`; accordingly, the artifact does not
infer which configured package-index mirror delivered it.
The repository also contains `.github/workflows/linux-check.yml`, which installs
the pinned extras on Ubuntu x86_64 / Python 3.11 and runs `make check` plus
`make te-smoke`. Frozen macOS timings are not relabeled as Linux results.

## Recommended evaluation sequence

1. Install the review environment:

       python -m pip install -e '.[pep,certificates,dev]'

   Or use the supplied Conda specification:

       conda env create -f environment.yml
       conda activate c2ogate-mpc

2. Run the flagship-first Technical Editor smoke route:

       make te-smoke

   This checks the public decision kernel, exact transcript membership, the
   hash-bound UCI payload, and the complete 28-cell horizon-six rational proof.
   It uses no numerical SDP solver.

3. Run static, unit, integrity, and tampering checks:

       make check

4. Replay the complete exact certificate set without trusting an SDP solver:

       make verify

   This route also runs the medium-radius H6 suite and a nonsharing SymPy H6
   implementation that imports neither the producer nor the standard-library
   verifier modules.

5. Rebuild all manuscript metrics and the article PDF:

       make mpc-paper

6. Optionally regenerate the synthetic and PEP studies:

       make studies

The sequence therefore has three evidential tiers: a short flagship smoke test,
the complete exact replay, and optional numerical regeneration.  The balanced
natural-$H=10$ verifier performs exact rational $LDL^\top$
elimination for 66 order-24 slack matrices and can take several minutes.  The
family consumer replays all three independently recovered sources and can take
tens of minutes; the two transported profiles add only algebraic checks.  It
uses only the Python standard library and never calls an SDP solver.  The
generic horizon-20 regeneration is also a multi-minute optional task; timings
are recorded rather than asserted as portable constants.

To reproduce the unified flagship cost ledger on the review machine, run:

       make h6-certificate-cost-study

The command performs three complete exact replays, adds their median to the
generator's frozen search-and-recovery wall time, and computes prepaid-reuse
thresholds from the remaining 0.6-call budget. `make
h10-certificate-cost-study` separately performs one measured replay of the
larger stress suite; it is not described as a median. Timings are descriptive;
the verifier's exact arithmetic result is the proof.

To regenerate the PEPit timing decomposition, independent padded-model
cross-check, and short-transcript workloads, run:

       make pepit-comparison
       make padded-model-crosscheck
       make rolling-logistic-workload
       make uci-wdbc-benchmark
       make measured-heat-inverse
       make h6-medium-radius-certificate
       make h6-independent-consumer
       make consumer-differential-fuzz
       make h15-scaling-diagnostic

The PEPit payload reports total wall time, Python model construction,
solve-call wall time, Clarabel's numerical kernel time, and the residual
framework/CVXPY canonicalization component. Thus the manuscript's roughly
1.54x figure is explicitly end-to-end rather than a pure front-end claim.

The rolling workload contains 512 proximal-logistic episodes with 40,000
normalized rows, 20 parameters, and a 5% sampled-Hessian reduced-Newton
proposal. A free necessary condition triggers 30 proposal attempts; the H=6
joint proof accepts 18, whereas the exact marginal gate accepts none. Full
candidate and future gradients are held out until the outcome audit. Warm joint
and marginal ratios are 0.965 and 1.003; always-query has mean ratio 0.055 but
43 pointwise overruns. This is a synthetic decision replay.
The prefilter-only comparator accepts all 30 attempts, has ratio 0.939, and has
zero post-hoc overruns; it is explicitly uncertified.

The external UCI WDBC benchmark has 569 rows and 30 features. A 10% sampled
diagonal-Hessian producer makes 45 attempts and the joint gate accepts 28; the
marginal gate accepts none. The row-scan warm ratio is 0.947, while measured
small-data timing gives 1.026, so the artifact does not label it a production
speedup. The official dataset file is vendored with CC BY 4.0, DOI, and hash
provenance. Both short-transcript runners use exact
`fractions.Fraction` comparisons for all proposal, residual, distance, row-norm,
and class predicates.
The prefilter-only comparator accepts all 45 attempts, has row-scan ratio 0.909,
measured-time ratio 0.989, and zero post-hoc overruns. Its stronger empirical
mean is not promoted to a class-wide guarantee.

The measured heat-inverse runner times a 640-by-640, 120-step periodic forward
solve and its adjoint as the exact oracle, and an 80-by-80, three-step pair as
the cheap oracle. The frozen median exact cost is 0.241 seconds. Across 64
alternating-mode episodes the certificate accepts 32 resolved proposals,
rejects 0, and leaves 32 underresolved proposals uncertified. The full search-
and-replay charge is 334.3 exact-call units. With the declared 12-unit penalty
for a failed pointwise saving, the cold gate/prefilter ratio is 0.881 and the
reuse threshold is 56 compatible episodes. Against the unpenalized baseline,
the measured reuse threshold is 671 episodes.

The padded-model cross-check independently constructs three representative
cells from each of the H=3, H=6, and H=10 exact suites in PEPit 0.5.1,
including full padding, trace, and margin-upper rows. The largest native--PEPit
objective difference is 2.518e-7. The H=15 diagnostic enumerates 136 generic
bad cells in 104.3 seconds and peaks at 1255.3 MiB; it remains
`uncertified`. The parameterized DPP variant reuses one canonical model across
all cells, reducing peak RSS to 422.1 MiB while increasing wall time to 360.6
seconds. A PEPit/Clarabel-to-rational adapter certifies 5/28 H6 cells; the other
23 remain uncertified and every recovered dual is replayed exactly.

## Trust boundary

Acceptance trusts:

- the declared transcript and function-class constants;
- the small `proof_carrying_gate` aggregation kernel;
- exact structural inequalities or independently replayed proof objects;
- the complete normalized cost ledger.

Before any proof producer is invoked, `validate_transcript_interface` admits
only constraints with exact affine Gram/function-value coefficients or an
independently verified exact affine lifting. `certified_branch_workflow`
returns `uncertified` without calling its producer callback for a nonaffine
predicate, an inexact coefficient set, or an unverified lift. This is an input
interface rejection, not the `reject` decision reserved for a verified bad
cell or ledger failure. The corresponding unit test asserts that the producer
callback is never entered.

Acceptance does not trust:

- a solver's `infeasible` or `inaccurate` status by itself;
- producer-side CVXPY coefficient arrays or stored solver matrices;
- the high-precision rational-certificate generator;
- wall-clock measurements;
- an unverified or missing cell record.

The shared-core standard-library consumers do reuse verifier utilities; their
independence is from the numerical producer and solver, not from one another.
The trust root includes their smaller mapping from mathematical semantics to
rational coefficient rows and is not machine-formalized. Two additional
checks reduce this common-mode risk. First, a nonsharing SymPy implementation
reconstructs every H6 row and all 448 positive pivots without importing the
producer, the standard-library coefficient builder, or its LDL routine.
Second, deterministic differential fuzzing compares 1,956,318 exact scalar
coefficients across 32 randomly drawn legal parameter/cell instances. A
separate PEPit implementation also checks nine complete padded H=3/6/10 cells
numerically. These are independent software cross-checks, not a formal proof
of the interpolation theorem.

| Mathematical source | Reconstructed rows/check |
|---|---|
| Gradient-descent recursion | Both affine trajectory coefficient maps and atom counts |
| Smooth strongly convex interpolation theorem | Every ordered-pair Gram/function-value row and row count |
| Transcript interface | Distance, proposal norm/residual, value anchor, exact right sides |
| Stopping-cell theorem | Survival, terminal, signed-margin rows and cell indices |
| Redundant-bound lemma | Trace and margin-upper bounds from declared parameters |
| Conic weak duality | Multiplier signs, stationarity, objective, slack, exact positive LDL pivots |

An independently verified attainable bad cell returns `reject`. Every other
unresolved condition returns `uncertified`, never `accept`.
If the monetary ledger flag is unverified, an attainable cell that already
violates the integer call-saving requirement may still return `reject`; a cell
that is bad only through the monetary inequality returns `uncertified`. Unit
tests cover both branches.

The public aggregate also reports proof progress. If exact recovery or replay
excludes only `k` of `n` required bad cells, the outcome is `uncertified` and
the reason contains `verified exclusions cover k/n bad cells`. This is useful
operational telemetry, not a partial-acceptance rule.

The generic horizon-15 and horizon-20 floating audits are therefore diagnostic and have
certificate outcome `uncertified`. The unified natural-H=6 suite supplies
the central positive result: 28 independently recovered nonzero-radius duals,
448 exact positive pivots, and witness pairs `(1,0)` and `(2,1)` prove joint
acceptance while the sharp marginal rectangle rejects at value one.
The strict-negative signed consumer is incomplete at an exact zero optimum.
No such boundary occurs in the cross-suite audit: exact-zero and numerical
near-zero counts are both 0/142 across five H=3/H=6/H=10 transcripts. Among 46
accepted UCI/rolling transcripts, zero reuse a zero-boundary suite.

The proof-production
natural-horizon-ten suite
contains independently replayed rational duals for all 66 cost-violating
generic cells and 1,584 exact positive $LDL^\top$ pivots.  The separate
payload records, for every cell, the prefix actually visited in the fixed
two-regularizer by five-threshold recovery grid. These records measure the
heuristic producer; they are not inputs to the mathematical acceptance proof.
The frozen run makes 69 attempts: 65 cells succeed at the first configuration,
one succeeds at the fourth after three failed attempts, and six configurations
are never reached. The final independently replayable coverage is 66/66.
An exact `fractions.Fraction` unit test checks the manuscript's nonempty-class
witness `f(t)=t^2/2+(4/5)t`, `x=0`, `y=-4/5`. The payload's different 80-digit
Decimal witness is retained only as an ancillary numerical cross-check and is
not used for acceptance.
Two further source envelopes repeat all 66 recoveries independently. For each
of two homogeneous transports the consumer first replays the source dual, then
checks exact parameter scaling, the unchanged horizon, a valid scaled trace
bound, and the strictly negative square-scaled objective. Target stationarity
is not rebuilt; its invariance follows from the degree-two homogeneous row map.
This yields five envelopes and
330 verified profile-cell exclusions.  The balanced proof-production
profile's separately
verified marginals give $L_x=1$, $U_y=0$, so its rectangle gate also accepts at
value zero.  Strict dependence value at the same horizon is established by a
separate full-class exact-shift certificate: exact arithmetic checks the
121-cell grid, all 66 structural bad-cell exclusions, witness pairs $(1,0)$
and $(5,4)$, and a marginal-rectangle value of at least four.  A stratified
SCS recovery diagnostic tests producer
portability without treating solver status as proof.  A separate SymPy
matrix pass recomputes all 1,584 balanced-source LDL pivots over the rationals;
the standard-library consumer remains the trusted
acceptance boundary.
The separate nonzero-radius H=3 suite excludes ten bad cells over the infinite
$\mathcal F_{1/2,1}$ transcript class, checks 100 positive exact pivots, and
proves that sharp independent marginals reject.  The separate
two-dimensional nonquadratic payload has formula-derived horizon H0=2; its
one-layer-padded horizon-three audit remains an independent realization
cross-check.
The rolling and UCI logistic workloads reuse the independently verified H=6 suite.
Each attempted record must pass the proposal-norm, residual, and
strong-monotonicity distance checks; its future stopping pair is retained only
as held-out evaluation data. The ledgers charge every attempted sketch,
including rejected proposals, and report prepaid and cold-start scenarios.
Envelope membership and class bounds are recomputed exactly from each stored
binary64 input by converting it to a rational number and comparing exact
squared norms. Upstream measurement and preprocessing uncertainty is not
covered.

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
The proof payload contains no authoritative primal coefficient matrices. From
the declared parameters and cell label, each independent consumer rebuilds
all interpolation, transcript, contract, stopping, margin, anchor, and trace
rows using only `fractions.Fraction`. It rejects unknown multiplier names,
wrong row counts, and parameter mismatches before checking stationarity, the
dual objective, or the slack matrix. Consequently the producer-side modeling
layer is outside the trusted boundary; the smaller verifier-side
semantic-to-coefficient builder is part of the trusted kernel. This checks the
instantiated finite SDP and does not claim a machine formalization of the
interpolation theorem.

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
- `data/`: the licensed UCI WDBC benchmark and redistributable synthetic raw
  option rows used to test the complete filter-to-rational-matrix
  transformation.
- `environment.yml`: Conda specification for the complete review environment.

## Data provenance and raw market-data limitation

The UCI WDBC raw file is redistributed under CC BY 4.0, with its official DOI
and SHA-256 recorded in `data/uci_wdbc/README.md`. The unofficial SPX
option-chain snapshot is not redistributed. Its CSV and
metadata hashes are recorded in the real-data payloads. The frozen rational
matrices, call counts, cost ledger, and verifier inputs needed for the article
are included. If the source snapshot is supplied to the positive verifier with
`--source-root`, the verifier independently reconstructs and matches the
data-to-matrix map.  A 20-row synthetic substitute is redistributed and
exercises that same independent map against frozen rational outputs, so a
clean checkout tests the implementation path without claiming to recreate the
unavailable market observations.
