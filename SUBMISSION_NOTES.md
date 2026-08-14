# MPC submission form text

## Article type

Full-Length Paper

## Title

C2OGate: Proof-Carrying Joint Performance Estimation for Two-Oracle Cost
Certification

## Running title

Proof-Carrying Two-Oracle Cost Certification

## Author and corresponding author

Jintao Li
NUS (Chongqing) Research Institute, Chongqing, China
e0622340@u.nus.edu

## Abstract

We present C2OGate, a proof-carrying method for deciding
whether a secondary-oracle candidate reduces all-in expensive-oracle cost
relative to an unchanged baseline. Conditioned on a first-order transcript,
the method couples both continuations on the same unknown function, enumerates
their joint stopping-time cells, and represents each cell over smooth strongly
convex functions by a dimension-free Gram SDP. It accepts only after
independently verified exclusion of every cost-violating cell; a verified
attainable bad cell rejects, and unresolved numerical evidence returns
uncertified. We prove the finite reduction, its fixed-dimension rank
qualification, the maximality of the resulting robust gate, and an unbounded
gap for independent marginal call bounds even on one-dimensional quadratics.
In a non-shift, nonquadratic H=3 instance, all ten cost-violating cells are
excluded by exact rational SDP duals; a standard-library verifier reconstructs
every SDP and checks 100 positive leading principal minors. A generic H=20
audit solves 231 bad-cell SDPs but remains uncertified, delimiting the current
scalability of exact dual recovery. Measured certificate cost is charged
explicitly and is self-financing only for sufficiently expensive calls or
offline reuse.

## Keywords

performance estimation; proof-carrying computation; semidefinite programming;
multifidelity optimization; stopping time; evaluation cost

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
  documented.
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
