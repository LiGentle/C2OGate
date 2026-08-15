# C2OGate MPC submission package

This directory is the independent submission package for *Mathematical
Programming Computation* (MPC). The OMS and earlier SIOPT packages are not
modified. The MPC manuscript foregrounds the exact joint stopping-cell
computation, proof-carrying semidefinite certificates, independent verifier,
software trust boundary, and technical-review protocol.

Public repository: <https://github.com/LiGentle/C2OGate>

The present MPC submission snapshot is version 0.6.1.  The public repository
is the development record; no archival DOI is claimed until an immutable
release has actually been deposited and minted by an archive service.

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

## Fast technical review

Python 3.11 or later is required. Install the complete development environment:

    python -m pip install -e '.[pep,certificates,dev]'

Alternatively, create the pinned review environment and activate it:

    conda env create -f environment.yml
    conda activate c2ogate-mpc

Run source and integrity checks:

    make check

Replay the ten independently checkable proof objects:

    make verify

Expected summaries:

    VERIFIED: generic nonquadratic R^2 joint-PEP dual suite, natural H0=2, padded audit H=3, 10 cost-violating cells, all upper bounds < 0, 100 positive leading minors
    VERIFIED: natural-H=10 generic joint-PEP dual suite, 66 cost-violating cells, Gram order <= 24, 1584 exact positive LDL pivots, progress=66/66 independently replayable exclusions constructed
    VERIFIED: flagship exact marginals L_x=1, U_y=0, rectangle gate value=0, 4 positive LDL pivots
    VERIFIED: five natural-H=10 envelopes, 198 independently recovered + 132 transported exact exclusions, 4752 independent positive LDL pivots
    VERIFIED: SCS producer diagnostic, 9/9 exact recoveries, 0 fail-closed outcomes
    VERIFIED: full infinite-class joint-only PEP acceptance, H=3, 10 bad cells, 100 positive LDL pivots, witness pairs=[[2, 1], [1, 0]]
    VERIFIED: exact joint-only acceptance, rectangle rejection, pairs=[[3, 2], [1, 0]], formula horizon=26
    VERIFIED: 3 instances, 9 rational SDP dual certificates, 87 exact principal minors
    VERIFIED: ill-conditioned real-SPX certificate, dimension 10, calls 7840->3803, condition lower bound > 1325.96
    VERIFIED: two-dimensional nonquadratic joint PEP acceptance, natural H0=2, padded H=3, exact pair (1,0), 10 cost-violating cells excluded

Build the article, source archive, software/data artifact, and cover letter:

    make submission

See `ARTIFACT_EVALUATION.md` for the trusted/untrusted split, command sequence,
expected run times, raw-data limitation, and directory map.

The balanced natural-$H=10$ verifier performs exact rational elimination for
every cell and can take several minutes.  The five-envelope family replays all
three independently recovered sources and can take tens of minutes; the two
transported sources are then checked algebraically.  These consumers import
only the Python standard library and do not invoke an SDP solver.

Replay the flagship verifier once, combine that charge with the frozen search
and rational-recovery time, and rebuild the paper's complete break-even ledger:

    make h10-certificate-cost-study

This machine-specific ledger charges both construction and proof consumption
against the remaining $0.6$ exact-call units; it is not part of the
machine-independent acceptance proof.

## Evidence included

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
- The proof payload does not contain authoritative primal SDP matrices. The
  standard-library consumer reconstructs every interpolation, transcript,
  stopping, margin, anchor, and trace coefficient from the declared parameters
  with exact `fractions.Fraction` arithmetic before checking stationarity,
  objective, slack, and positive pivots. Producer-side CVXPY assembly is not
  trusted.
- An exact marginal audit of the balanced flagship: $L_x=1$, $U_y=0$, and
  rectangle gate value zero.  The paper therefore does not attribute strict
  joint-over-marginal value to this profile; the separate full-class $H=3$
  suite supplies that evidence.
- A stratified SCS-to-rational-recovery diagnostic whose successful outputs
  are independently replayed and whose unsuccessful outputs fail closed, plus
  a full-load SymPy rational-arithmetic LDL cross-check of all 1,584
  balanced-source pivots.
- Five complete bad-cell timing and peak-memory runs with Clarabel and SCS,
  plus a same-model comparison with PEPit 0.5.1.  PEPit is faster in this
  benchmark; C2OGate contributes the branch disjunction, fail-closed
  aggregation, exact recovery, and independent proof consumer.
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
- One exact non-shift, nonquadratic acceptance whose realized trajectory spans
  two dimensions. Its formula-derived horizon is H0=2; a one-layer-padded H=3
  audit includes independently replayed rational Gram-SDP duals for all ten
  cost-violating cells and 100 exact positive-minor checks.
- Three rational quadratic instances containing nine exact SDP duals and 87
  exact principal-minor checks.
- A frozen audit over 2,000 transcript-consistent quadratic families.
- A real-SPX positive cost certificate in dimension 10, with exact-call count
  7,840 to 3,803 and common-ledger all-in cost ratio 0.495; the full rational
  quadratic is revealed, so this is a constant-pipeline stress test.
- Measured break-even ledgers for both the ten-cell cross-check and the
  flagship natural-$H=10$ suite; each uses the certificate budget remaining
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
statuses are diagnostic only; the proof-carrying aggregator returns
`uncertified` unless a bad-cell witness or every exclusion is independently
verified. For incomplete coverage it reports the exact `k/n` verified-cell
progress without weakening the acceptance rule. The main proof suite has natural horizon ten and independently
replays every cost-violating cell. Exact generic recovery is currently a
moderate-horizon method, not a scalable long-horizon SDP solver. The smaller
nonquadratic realization and the full-class joint-only suite are independent
cross-checks. The positive real-SPX instance reveals its full rational
quadratic.

The software and supporting research artifact are released under the MIT
License. See `LICENSE` for the complete terms. The raw third-party SPX snapshot
is not part of the licensed repository because it is not redistributed.
