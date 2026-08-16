# C2OGate MPC submission package

This directory is the self-contained submission package for *Mathematical
Programming Computation* (MPC). Earlier unpublished OMS- and SIOPT-oriented
manuscripts are superseded by this self-contained version and are not under
review. The MPC manuscript foregrounds exact joint stopping-cell computation,
externally checkable semidefinite certificates, explicit software trust
boundaries, and a technical-review protocol. The public Python API retains a
few historical `proof_carrying_*` names for compatibility; its payloads are
rational SDP dual certificates, not machine-checked proofs.

Public repository: <https://github.com/LiGentle/C2OGate>

Immutable release archive: <https://doi.org/10.5281/zenodo.21964074>

`C2OGate` expands to **certified two-option gate**. The historical directory
name `two_oracle_cost_gate` reflects the motivating implementation; the proved
object is one proposal-versus-baseline continuation decision. Modeling an
arbitrary future cheap-oracle sequence would require a genuine extension.

The present MPC submission snapshot is version 0.9.0.  The public repository
is the development record, while the immutable software, data, certificate,
and manuscript release is archived by Zenodo under DOI
`10.5281/zenodo.21964074`.

## Submission outputs

- `output/pdf/c2ogate_mpc_manuscript.pdf`: upload-ready article.
- `output/pdf/mpc_cover_letter.pdf`: journal-specific cover letter.
- `output/mpc_latex_source.zip`: minimal compilable Springer source.
- `output/c2ogate_mpc_artifact.zip`: software, data, certificate, and test
  archive for the MPC Technical Editor.
- `SUBMISSION_NOTES.md`: submission-form text and upload mapping.

The source is in `paper_mpc/main.tex`. It uses Springer's official `svjour3`
class with the journal-required `smallextended` option and `spmpsci` numeric
bibliography style. The unmodified template archive downloaded from the MPC
author instructions is stored as `paper_mpc/svjour3-latex-package.zip`.

Official template source:

<https://media.springer.com/full/springer-instructions-for-authors-assets/zip/468198_LaTeX_DL_468198_240419.zip>

## Tiered technical review

Python 3.11 or later is required. Install the complete development environment:

    python -m pip install -e '.[pep,certificates,dev]'

Alternatively, create the pinned review environment and activate it:

    conda env create -f environment.yml
    conda activate c2ogate-mpc

Start with the flagship-first smoke route.  It checks the public three-valued
kernel, exact binary64 membership, the frozen external-data payload, and all 28
exact horizon-six bad-cell exclusions without invoking an SDP solver:

    make te-smoke

Then run the complete source, integrity, and tampering checks:

    make check

Finally, replay the complete set of independently checkable certificate objects:

    make verify

Expected summaries:

    VERIFIED: generic nonquadratic R^2 joint-PEP dual suite, natural H0=2, padded audit H=3, 10 cost-violating cells, all upper bounds < 0, 100 positive leading minors
    VERIFIED: natural-H=10 generic joint-PEP dual suite, 66 cost-violating cells, Gram order <= 24, 1584 exact positive LDL pivots, progress=66/66 independently replayable exclusions constructed
    VERIFIED: flagship exact marginals L_x=1, U_y=0, rectangle gate value=0, 4 positive LDL pivots

The third line is the frozen verifier's legacy label; the manuscript calls this
the H=10 proof-production stress suite, not the unified flagship.
    VERIFIED: five natural-H=10 envelopes, 198 independently recovered + 132 transported exact exclusions, 4752 independent positive LDL pivots
    VERIFIED: SCS producer diagnostic, 9/9 exact recoveries, 0 fail-closed outcomes
    VERIFIED: full infinite-class joint-only PEP acceptance, H=3, 10 bad cells, 100 positive LDL pivots, witness pairs=[[2, 1], [1, 0]]
    VERIFIED: natural-H=6 nonzero-radius joint-only PEP acceptance, 28 bad cells, 448 positive LDL pivots, witness pairs=[[1, 0], [2, 1]]
    VERIFIED: natural-H=6 medium-radius joint-only PEP acceptance, delta=7/500, 28 bad cells, 448 positive LDL pivots
    VERIFIED: independent SymPy H6 consumer, 28 cells, 448 exact positive pivots
    VERIFIED: full-class joint-only H=10 exact shift, 66/66 bad cells excluded, witnesses (1,0) and (5,4), rectangle >= 4
    VERIFIED: exact joint-only acceptance, rectangle rejection, pairs=[[3, 2], [1, 0]], formula horizon=26
    VERIFIED: 3 instances, 9 rational SDP dual certificates, 87 exact principal minors
    VERIFIED: ill-conditioned real-SPX certificate, dimension 10, calls 7840->3803, condition lower bound > 1325.96
    VERIFIED: two-dimensional nonquadratic joint PEP acceptance, natural H0=2, padded H=3, exact pair (1,0), 10 cost-violating cells excluded

Build the article, source archive, software/data artifact, and cover letter:

    make submission

See `ARTIFACT_EVALUATION.md` for the trusted/untrusted split, command sequence,
expected run times, raw-data limitation, and directory map.
See `REUSABILITY_CONTRACT.md` and `examples/reuse_custom_stopping_rule.py` for
the stable consumer interface and the minimal path for a new stopping rule.

The smoke, full-test, and full-proof tiers are intentionally separate so an MPC
Technical Editor can inspect the central claim before committing to the longer
replay.  The balanced natural-$H=10$ verifier performs exact rational elimination for
every cell and can take several minutes.  The five-envelope family replays all
three independently recovered sources and can take tens of minutes; the two
transported sources are then checked algebraically.  These consumers import
only the Python standard library and do not invoke an SDP solver.

The included `.github/workflows/linux-check.yml` runs `make check` and
`make te-smoke` on Ubuntu x86_64 with Python 3.11. Frozen timings remain the
declared macOS arm64 measurements; a CI pass is a portability check, not a
replacement timing record or a proof assumption.

Replay the unified $H=6$ verifier three times, combine the median charge with
the frozen search-and-recovery time, and rebuild its break-even ledger:

    make h6-certificate-cost-study

The separate `make h10-certificate-cost-study` target measures one full replay
of the larger proof-production stress suite. These machine-specific ledgers
charge both construction and proof consumption
against the remaining $0.6$ exact-call units; it is not part of the
machine-independent acceptance proof.

## Evidence included

- The unified flagship is a natural-$H=6$, nonzero-radius envelope over the
  infinite class `F_{3/10,1}`. All 28 bad cells have independently replayed
  rational duals and 448 positive exact pivots. Two exact quadratic witnesses
  make the sharp marginal rectangle reject at value one while the joint gate
  accepts at zero. Search takes 50.3 seconds and the median of three complete
  exact replays is 30.2 seconds (80.6 seconds all-in).
- A five-envelope natural-$H=10$ family containing 330 verified
  profile-cell exclusions.  Three source envelopes contribute 198
  independently recovered rational duals; two homogeneous transports
  contribute 132 algebraically checked exclusions.  The balanced source
  contains all 66 cost-violating cells,
  66 exact rational dual exclusions, and 1,584 exact positive $LDL^\top$
  pivots, with no structural prescreen. The payload records the ordered
  threshold--regularizer recovery prefix for every cell: 69 attempts contain
  66 successes and three failed attempts, with four of ten configurations
  reached before all cells were certified.
  A separate five-transcript audit covers 142 signed cells across H=3, H=6,
  and H=10. Exact-zero and floating-near-zero counts are both 0/142; 0/46
  accepted UCI/rolling transcripts reuse a zero-boundary suite. A zero
  signed-margin optimum would remain `uncertified` under the current
  strict-negative consumer.
- The proof payload does not contain authoritative primal SDP matrices. The
  standard-library consumer reconstructs every interpolation, transcript,
  stopping, margin, anchor, and trace coefficient from the declared parameters
  with exact `fractions.Fraction` arithmetic before checking stationarity,
  objective, slack, and positive pivots. Producer-side CVXPY assembly is not
  trusted.
- A separate PEPit 0.5.1 builder reconstructs the complete padded formulas,
  including trace and margin-upper rows, on nine representative H=3, H=6, and
  H=10 cells. Its largest objective difference from the native builder is
  2.518e-7. This differential check catches many row/index/sign mistakes but
  is correctly described as numerical rather than formal verification.
- An exact marginal audit of the balanced proof-production stress profile:
  $L_x=1$, $U_y=0$, and
  rectangle gate value zero.  The paper therefore does not attribute strict
  joint-over-marginal value to this profile.  A separate full-class $H=10$
  exact-shift certificate excludes all 66 bad cells in a 121-cell grid and
  uses witnesses $(1,0)$ and $(5,4)$ to prove the marginal rectangle value is
  at least four; the full-class nonzero-radius $H=3$ suite supplies a second,
  non-shift dependence result.
- A stratified SCS-to-rational-recovery diagnostic whose successful outputs
  are independently replayed and whose unsuccessful outputs fail closed, plus
  a full-load SymPy rational-arithmetic LDL cross-check of all 1,584
  balanced-source pivots.
- Five complete bad-cell timing and peak-memory runs with Clarabel and SCS,
  plus a same-model comparison with PEPit 0.5.1.  The reported approximately
  1.96x, 1.77x, and 1.54x gaps at H=2, 6, and 10 are end-to-end, not mislabeled
  front-end numbers: the payload
  separates Python model construction, wrapper/CVXPY canonicalization,
  Clarabel's reported numerical-kernel time, and residual loop overhead.
  PEPit is faster here. C2OGate retains a domain-specific producer because its
  independent exact consumer needs stable named rational rows; a PEPit producer
  adapter now emits the same H=6 schema. Feeding PEPit's Clarabel duals to the
  fixed rational-recovery rule certifies 5/28 cells; the native named-row path
  certifies 28/28. The remaining 23 cells are explicitly `uncertified`.
- Explicit PEPit provenance: the optional `pep` extra pins `PEPit==0.5.1`; the
  frozen environment records installer `uv`, official documentation, PyPI
  release, GitHub home page, and tagged source URL. No `direct_url.json` was
  present, so the payload does not guess which package-index mirror served the
  installation.
- An exact nonzero-radius suite over the full infinite class
  `F_{1/2,1}` in which the joint PEP accepts and sharp independent marginals
  reject. Ten rational duals and 100 exact positive pivots are independently
  replayed; the earlier two-function example remains a regression test.
- A finite-family audit that quantifies false acceptance under deliberately
  optimistic proposal contracts.
- A redistributable 20-row synthetic option panel and frozen rational matrices
  that exercise the same filtering, polynomial-feature, centering, scaling,
  rounding, and sketch map used by the independent SPX verifier.
- Complete structured and generic horizon-20 floating cell enumerations.
- A generic non-shift H=15 ragged diagnostic enumerates 136 bad cells in 104.3
  seconds with maximum Gram order 34 and peak RSS 1255.3 MiB. It is
  `uncertified`. A second implementation reuses one parameterized padded model
  across all cells: peak RSS falls to 422.1 MiB (66.4% lower), while wall time
  rises to 360.6 seconds (3.46x). This is measured model/canonicalization reuse,
  not a shared-dual, chordal, or exact H=15 solution.
- One exact non-shift, nonquadratic acceptance whose realized trajectory spans
  two dimensions. Its formula-derived horizon is H0=2; a one-layer-padded H=3
  audit includes independently replayed rational Gram-SDP duals for all ten
  cost-violating cells and 100 exact positive-minor checks.
- A rolling nonlinear logistic calibration simulation with 512 decisions,
  40,000 normalized records, 20 parameters, and a charged 5% minibatch
  sampled-Hessian reduced-Newton proposal. A free necessary-condition
  prefilter attempts 30 proposals; the exact H=6 joint suite accepts 18
  decisions, rejects 0, and leaves 12 uncertified because the proposal band
  fails. The exact marginal gate
  accepts none. The anchor radius is uniform on a neutral range not selected to
  cross the band. The held-out audit has zero accepted violations. Warm joint
  and marginal ratios are 0.965 and 1.003; the 60-second-oracle cold ratio is
  0.968. Always-query has mean ratio 0.055 but 43 pointwise overruns. All 512
  membership/class decisions are recomputed exactly from binary64 inputs with
  `fractions.Fraction`.
  The closer prefilter-only comparator accepts all 30 attempts, has ratio 0.939,
  and has zero post-hoc overruns; it beats C2OGate in empirical mean cost but
  carries no ex-ante class-wide guarantee.
- An external-data replay on the UCI Wisconsin Diagnostic Breast Cancer data
  (569 rows, 30 features) uses 10% sampled diagonal-Hessian reduced-Newton
  proposals. The joint rule accepts 28 of 45 attempts and the exact marginal
  rule accepts none; the three-valued split is 28 accept, 0 reject, and 17
  uncertified proposal-band failures. Exact rational membership closes the deployment
  arithmetic gap. Row-scan accounting gives a warm ratio of 0.947, whereas
  measured microbenchmark timing gives 1.026; the paper reports both and does
  not claim a production speedup. The official raw file, CC BY 4.0 notice,
  DOI, and SHA-256 provenance are included.
  The prefilter-only comparator accepts all 45 attempts, has row-scan ratio
  0.909 and measured-time ratio 0.989, and has zero post-hoc overruns. This
  adverse comparison is reported in the manuscript rather than suppressed.
- Three rational quadratic instances containing nine exact SDP duals and 87
  exact principal-minor checks.
- A frozen audit over 2,000 transcript-consistent quadratic families.
- A real-SPX positive cost certificate in dimension 10, with exact-call count
  7,840 to 3,803 and common-ledger all-in cost ratio 0.495; the full rational
  quadratic is revealed, so this is a constant-pipeline stress test.
- Measured break-even ledgers for the ten-cell cross-check, the unified
  natural-$H=6$ flagship, and the natural-$H=10$ stress suite; each uses the certificate budget remaining
  after proposal and non-certificate costs.  A 27-configuration SPX
  sensitivity grid covers ridge, sketch stride, and tolerance.
- Frozen canonical JSON payloads, source hashes, verifier hashes, and rehashed
  adversarial modifications.

## Regeneration

The synthetic and performance-estimation studies can be regenerated with:

    make studies

The additional producer and independent-backend diagnostics introduced for
the multi-envelope audit are explicit because they are substantially slower:

    make h10-marginal-certificate
    make h10-envelope-family
    make scs-recovery-diagnostic
    make sympy-exact-crosscheck
    make pepit-comparison
    make padded-model-crosscheck
    make rolling-logistic-workload
    make uci-wdbc-benchmark
    make measured-heat-inverse
    make h6-medium-radius-certificate
    make h6-independent-consumer
    make consumer-differential-fuzz
    make h15-scaling-diagnostic
    make batched-parameterized-scaling
    make pepit-verified-baseline
    make joint-marginal-comparison
    make signed-boundary-audit

The two market-data regeneration targets are optional:

    make real-spx-study
    make real-spx-positive-study
    make spx-sensitivity-study

They require the external unofficial SPX snapshot whose hashes are recorded in
the frozen payloads. The snapshot is not redistributed. A clean archive can
still replay every frozen proof, run all tests, and rebuild the paper without
that snapshot. The redistributable raw-row substitute is regenerated by
`make synthetic-data-fixture`; it tests the complete data-to-matrix path but
does not purport to reproduce the unavailable snapshot's empirical content.

## Scope and license

This is research code supporting the submitted manuscript, not a general PEP
modeling language or production optimizer. Generic long-horizon floating
statuses are diagnostic only; the certificate aggregator returns
`uncertified` unless a bad-cell witness or every exclusion is independently
verified. For incomplete coverage it reports the exact `k/n` verified-cell
progress without weakening the acceptance rule. The unified proof suite has
natural horizon six and independently replays every cost-violating cell. Exact generic recovery is currently a
moderate-horizon method, not a scalable long-horizon SDP solver. The smaller
nonquadratic realization and the nonzero-radius full-class joint-only suite are
independent cross-checks.  The separate exact-shift horizon-ten audit uses a
one-line analytic structural certificate rather than rational SDP recovery and
is not presented as the computational flagship. Unsupported nonaffine transcript relations fail the
public interface before proof production and return `uncertified`; they are
never silently dropped. The UCI benchmark is real external data but not a
clinical or production claim; the rolling workload is synthetic. Both make
genuine short-transcript decisions, use safeguarded curvature-dependent
reduced-Newton proposals, and perform exact rational envelope membership.
Candidate and future full-data gradients enter only the post-decision audit.
The two prefilter-only comparators are empirically cheaper and have zero
observed overruns on their frozen samples; the artifact therefore claims
certified pointwise safety infrastructure, not superior average selection or a
measured universal speedup. A measured periodic heat-inverse study supplies a
positive risk-adjusted ledger: the gate protects 32 underresolved proposals
and is economical after 56 compatible decisions under the explicit failed-
saving penalty, or after 671 compatible decisions against the unpenalized
baseline. Below both measured thresholds the unchanged baseline is preferred.
The positive real-SPX instance reveals its full
rational quadratic.

The software and supporting research artifact are released under the MIT
License. See `LICENSE` for the complete terms. The UCI WDBC data are
included under CC BY 4.0 with DOI 10.24432/C5DW2B and raw-file SHA-256
`d606af411f3e5be8a317a5a8b652b425aaf0ff38ca683d5327ffff94c3695f4a`.
The raw third-party SPX
snapshot is not part of the licensed repository because it is not
redistributed.
