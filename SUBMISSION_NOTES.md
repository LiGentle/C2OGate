# MPC submission form text

## Article type

Full-Length Paper

## Title

C2OGate: Proof-Carrying Joint Performance Estimation for Certified Branch
Decisions

## Running title

Proof-Carrying Branch Certification

## Author and corresponding author

Jintao Li
NUS (Chongqing) Research Institute, Chongqing, China
e0622340@u.nus.edu

## Abstract

We present C2OGate, a proof-carrying method for deciding between two
continuations after an external mechanism supplies a candidate and an
auditable error-and-cost contract. Conditioned on a first-order transcript,
the method couples fixed-step gradient descent from both starts on the same
unknown smooth strongly convex function and represents every cost-violating
joint stopping-time cell by a dimension-free Gram SDP. Acceptance requires
independently verified exclusion of every bad cell; counterexamples reject,
and incomplete evidence returns uncertified. The consumer rebuilds every SDP
coefficient from the declared parameters in exact rational arithmetic before
checking the supplied dual. We prove the finite reduction,
its fixed-dimension rank qualification, transcript-relative maximality, and
the possible loss from replacing the joint set by independent marginals. Five
natural-H=10 envelopes yield 330 exact bad-cell exclusions: 198 are
independently recovered across three source envelopes and 132 follow by
checked homogeneous transport. The flagship profile has Gram order at most 24
and 1,584 exact positive LDL pivots; an independent SymPy rational-arithmetic
check confirms all 1,584 exact pivots. Its exact marginal rectangle
also accepts, at boundary value zero. A separate nonzero-radius example over
the full smooth strongly convex class with mu=1/2 and L=1 is accepted only by
the joint PEP. Rational certificate construction remains heuristic
success-or-fail; only independent verification and resulting decisions are
guaranteed, and the generic H=20 enumeration remains uncertified. The
deployment ledger separately charges proof construction, envelope acquisition,
and verification. In a synthetic rolling nonlinear logistic workload, the
frozen H=10 proof accepts 48 of 256 decisions using only short transcripts;
post-decision full-model evaluation finds zero accepted violations and a
prepaid-proof cost ratio of 0.863 after charging every 5% minibatch proposal.

## Keywords

performance estimation; proof-carrying computation; semidefinite programming;
certified branch decision; stopping time; evaluation cost

## MSC 2020

90C25; 90C22; 65K05; 68Q25

## Suggested subject area

Continuous optimization / computational optimization. The paper's closest
methodological communities are performance estimation, semidefinite
optimization, exact verification, and multifidelity optimization.

## Upload mapping

1. Main manuscript PDF: `output/pdf/c2ogate_mpc_manuscript.pdf`.
2. Cover letter: `output/pdf/mpc_cover_letter.pdf`.
3. Editable LaTeX source: `output/mpc_latex_source.zip`.
4. Software/data file for Technical Editor review:
   `output/c2ogate_mpc_artifact.zip`.

The software/data archive should be classified as software, data, code, or
ancillary material for technical review, according to the form's available
file type. It should not be described as an optional narrative supplement: MPC
normally evaluates software and/or data together with the paper. If the form
accepts only a repository URL, upload the same archive to a persistent private
or public review repository and provide the access link.

## Required declarations included in the manuscript

- Funding: no funds, grants, or other support.
- Competing interests: none.
- Author contributions: all roles performed by Jintao Li.
- Data availability: frozen derived payloads included; raw unofficial SPX rows
  are not redistributed; expected hashes and reconstruction procedure are
  documented; a redistributable synthetic raw-row substitute exercises the
  complete data-to-matrix path.
- Code availability: source, tests, exact verifiers, and build scripts are
  released under the MIT License at <https://github.com/LiGentle/C2OGate> and
  included in the technical-review artifact.
- Generative AI: OpenAI Codex assisted with software development,
  computational checking, and drafting; the author reviewed and accepts full
  responsibility.

## Final pre-submission checks

- Confirm that the manuscript is not under consideration elsewhere.
- Select at least five qualified, unconflicted reviewer suggestions if the
  submission system requests them.
- Public MIT repository confirmed: <https://github.com/LiGentle/C2OGate>.
- Keep the software/data archive separate from the main article PDF so that it
  can be routed to the Technical Editor.
