# MPC submission form text

## Article type

Full-Length Paper

## Title

C2OGate: Externally Checkable Joint Performance Estimation for Cost-Dominant
Continuation Decisions

## Running title

Verifiable Continuation Decisions

## Author and corresponding author

Jintao Li
NUS (Chongqing) Research Institute, Chongqing, China
e0622340@u.nus.edu

## Abstract

Consider a continuation decision between a baseline state and a paid proposal.
Separate worst-case bounds for their remaining stopping times can combine two
incompatible functions and therefore reject a decision that is safe on every
single compatible function. C2OGate conditions on the observed first-order
transcript, enumerates the joint stopping-time cells of the two fixed-step
gradient continuations, and reduces each cost-violating cell to a Gram
semidefinite program. A numerical producer may fail, but acceptance requires
externally checkable rational dual exclusions for every bad cell; a
standard-library consumer reconstructs all interpolation, stopping, and trace
coefficients from semantic parameters before checking the dual identities.
This gives an exact, dimension-free decision whenever cell exclusion is
complete and returns uncertified otherwise. On the infinite class F_{3/10,1},
a complete H=6 suite excludes all 28 bad cells with 448 exact LDL pivots and
accepts, whereas sharp separately conditioned marginals reject. This
controlled decision reversal is the headline result; exact recovery is
currently demonstrated only through moderate horizons and remains heuristic
success-or-fail.

## Keywords

performance estimation; externally checkable certificate; semidefinite programming;
continuation decision; stopping time; evaluation cost

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

The immutable public release is archived at
<https://doi.org/10.5281/zenodo.21964074>.

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
- Data availability: the licensed UCI WDBC raw benchmark and frozen derived
  payloads are included; raw unofficial SPX rows
  are not redistributed; expected hashes and reconstruction procedure are
  documented; a redistributable synthetic raw-row substitute exercises the
  complete data-to-matrix path.
- Code availability: source, tests, exact verifiers, and build scripts are
  released under the MIT License at <https://github.com/LiGentle/C2OGate> and
  included in the technical-review artifact; the immutable release is at
  <https://doi.org/10.5281/zenodo.21964074>.
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
