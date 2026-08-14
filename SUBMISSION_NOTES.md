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

We present C2OGate, an exact computational method for deciding whether a
candidate produced by a secondary oracle can be certified to reduce all-in
calls to an expensive oracle relative to an unchanged baseline. The method
conditions on observed first-order data, couples baseline and candidate
continuations on the same unknown function, enumerates their joint
stopping-time cells, and reduces each cell over smooth strongly convex
functions to a dimension-free semidefinite program. Acceptance is
proof-carrying: structural screeners or independently checked dual certificates
must exclude every cost-violating cell, while a verified attainable cell
rejects and any unresolved numerical status returns uncertified. This design
isolates numerical optimization from the trusted verifier and charges proposal,
solution, certificate, verification, and rejected work in a common cost ledger.
We prove an exact finite-horizon reduction and show that replacing the joint
object by independent marginal call bounds can be arbitrarily conservative
even within one-dimensional quadratics. The implementation provides hash-bound
inputs, rational certificates, standard-library verifiers, and adversarial
integrity tests. Experiments include complete horizon-20 cell enumerations, a
nonquadratic acceptance, nine exact rational dual certificates, an audit over
2,000 transcript-consistent quadratic families, and a real-SPX cost instance
reducing 7,840 baseline calls to 3,803 hybrid calls with an all-in ratio of
0.492. The guarantee remains conditional on the declared transcript, function
class, oracle contract, and costs; unresolved cells never support acceptance.

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
