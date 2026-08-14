# C2OGate MPC submission package

This directory is the independent submission package for *Mathematical
Programming Computation* (MPC). The OMS and earlier SIOPT packages are not
modified. The MPC manuscript foregrounds the exact joint stopping-cell
computation, proof-carrying semidefinite certificates, independent verifier,
software trust boundary, and technical-review protocol.

Public repository: <https://github.com/LiGentle/C2OGate>

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

    python -m pip install -e '.[pep,certificates]' pytest ruff

Run source and integrity checks:

    make check

Replay the four independently checkable acceptance artifacts:

    make verify

Expected summaries:

    VERIFIED: generic nonquadratic H=3 joint-PEP dual, cell (3, 3), upper bound < 0, 10 positive leading minors
    VERIFIED: 3 instances, 9 rational SDP dual certificates, 87 exact principal minors
    VERIFIED: ill-conditioned real-SPX certificate, dimension 10, calls 7840->3803, condition lower bound > 1325.96
    VERIFIED: nonquadratic joint PEP acceptance, exact pair (1,0), 10 cost-violating cells excluded

Build the article, source archive, software/data artifact, and cover letter:

    make submission

See `ARTIFACT_EVALUATION.md` for the trusted/untrusted split, command sequence,
expected run times, raw-data limitation, and directory map.

## Evidence included

- Complete structured and generic horizon-20 cell enumerations.
- One exact non-shift, nonquadratic horizon-three acceptance over the declared
  function class, including a recovered rational Gram-SDP dual for cell
  `(3,3)` and exact contraction exclusions for the other bad cells.
- Three rational quadratic instances containing nine exact SDP duals and 87
  exact principal-minor checks.
- A frozen audit over 2,000 transcript-consistent quadratic families.
- A real-SPX positive cost certificate in dimension 10, with exact-call count
  7,840 to 3,803 and common-ledger all-in cost ratio 0.495; the full rational
  quadratic is revealed, so this is a constant-pipeline stress test.
- A measured generic-certificate break-even ledger and a 27-configuration SPX
  sensitivity grid over ridge, sketch stride, and tolerance.
- Frozen canonical JSON payloads, source hashes, verifier hashes, and rehashed
  adversarial modifications.

## Regeneration

The synthetic and performance-estimation studies can be regenerated with:

    make studies

The two market-data regeneration targets are optional:

    make real-spx-study
    make real-spx-positive-study
    make spx-sensitivity-study

They require the external unofficial SPX snapshot whose hashes are recorded in
the frozen payloads. The snapshot is not redistributed. A clean archive can
still replay every frozen proof, run all tests, and rebuild the paper without
that snapshot.

## Scope and license

This is research code supporting the submitted manuscript, not a general PEP
modeling language or production optimizer. Generic long-horizon floating
statuses are diagnostic only; the proof-carrying aggregator returns
`uncertified` unless a bad-cell witness or every exclusion is independently
verified. The nonquadratic accepted instance has horizon three and includes
one recovered generic Gram-SDP dual. The positive real-SPX instance reveals
its full rational quadratic.

The software and supporting research artifact are released under the MIT
License. See `LICENSE` for the complete terms. The raw third-party SPX snapshot
is not part of the licensed repository because it is not redistributed.
