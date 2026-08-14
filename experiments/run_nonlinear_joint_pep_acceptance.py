#!/usr/bin/env python3
"""Direct joint-PEP acceptance on a smooth nonquadratic instance."""

from __future__ import annotations

import argparse
from decimal import Decimal, getcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from c2ogate.transcript import StoppingPair, transcript_optimal_gate  # noqa: E402
from experiments.run_transcript_pep_study import _cell_margin  # noqa: E402
from tools.verify_generic_nonquadratic_pep_dual import (  # noqa: E402
    verify_payload as verify_generic_dual,
)


SCHEMA = "c2o-nonlinear-joint-pep-acceptance-v4"
GENERIC_DUAL = ROOT / "certificates" / "generic_nonquadratic_pep_dual.json"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tanh(value: Decimal) -> Decimal:
    exponential = (Decimal(2) * value).exp()
    return (exponential - 1) / (exponential + 1)


def _gradient(value: Decimal) -> Decimal:
    return Decimal(9) * value / Decimal(10) + _tanh(value) / Decimal(10)


def _norm(values: tuple[Decimal, ...]) -> Decimal:
    return sum((value * value for value in values), Decimal(0)).sqrt()


def _certified_horizon(
    contraction: Fraction,
    smoothness: Fraction,
    distance: Fraction,
    tolerance: Fraction,
) -> int:
    horizon = 0
    residual_bound = smoothness * distance
    while residual_bound > tolerance:
        residual_bound *= contraction
        horizon += 1
    return horizon


def _actual_trajectory() -> dict[str, Any]:
    getcontext().prec = 100
    x = (Decimal("0.9"), Decimal("0.4"))
    residual = (Decimal("0.003"), Decimal("-0.004"))
    gradient_x = tuple(_gradient(value) for value in x)
    x_one = tuple(
        value - gradient
        for value, gradient in zip(x, gradient_x, strict=True)
    )
    y = tuple(
        value + perturbation
        for value, perturbation in zip(x_one, residual, strict=True)
    )
    gradient_y = tuple(_gradient(value) for value in y)
    gradient_x_one = tuple(_gradient(value) for value in x_one)
    tolerance = Decimal(7) / Decimal(50)
    if not (_norm(gradient_x) > tolerance):
        raise RuntimeError("baseline must be nonterminal at the transcript point")
    if not (_norm(gradient_x_one) < tolerance and _norm(gradient_y) < tolerance):
        raise RuntimeError("both one-step and candidate terminal checks must be strict")
    proposal = tuple(
        candidate - current for candidate, current in zip(y, x, strict=True)
    )
    if not (Decimal("0.96") <= _norm(proposal) <= Decimal("0.97")):
        raise RuntimeError("realized proposal must lie inside the rational envelope")
    span_determinant = x[0] * x_one[1] - x[1] * x_one[0]
    if not span_determinant < Decimal("-0.005"):
        raise RuntimeError("realized trajectory must have a two-dimensional span")
    return {
        "dimension": 2,
        "x": [str(value) for value in x],
        "gradient_x": [str(value) for value in gradient_x],
        "candidate_y": [str(value) for value in y],
        "candidate_residual": [str(value) for value in residual],
        "candidate_residual_norm": str(_norm(residual)),
        "proposal_norm": str(_norm(proposal)),
        "gradient_y": [str(value) for value in gradient_y],
        "baseline_x_one": [str(value) for value in x_one],
        "gradient_x_one": [str(value) for value in gradient_x_one],
        "trajectory_span_determinant": str(span_determinant),
        "baseline_calls": 1,
        "hybrid_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "nonlinear_joint_pep_acceptance.json",
    )
    args = parser.parse_args()

    actual = _actual_trajectory()
    mu = Fraction(9, 10)
    smoothness = Fraction(1)
    tolerance = Fraction(7, 50)
    residual = Fraction(1, 100)
    proposal_lower = Fraction(24, 25)
    proposal_upper = Fraction(97, 100)
    current_gradient_lower = proposal_lower - residual
    current_gradient_upper = proposal_upper + residual
    contraction = (smoothness - mu) / smoothness
    baseline_one_upper = smoothness * contraction * current_gradient_upper / mu
    candidate_gradient_upper = baseline_one_upper + smoothness * residual

    proposal_norm = float(Decimal(actual["proposal_norm"]))
    cells: list[dict[str, Any]] = []
    numerical_attainable: list[StoppingPair] = []
    natural_horizon = _certified_horizon(
        contraction,
        smoothness,
        Fraction(6, 5) + proposal_upper,
        tolerance,
    )
    audit_padding = 1
    horizon = natural_horizon + audit_padding
    if natural_horizon != 2 or horizon != 3:
        raise RuntimeError("unexpected formula-derived or padded horizon")
    for baseline_calls in range(horizon + 1):
        for hybrid_calls in range(horizon + 1):
            status, margin = _cell_margin(
                baseline_calls,
                hybrid_calls,
                horizon=horizon,
                strong_convexity=float(mu),
                smoothness=float(smoothness),
                step_size=1.0,
                proposal_step=1.0,
                proposal_norm=proposal_norm,
                contract_radius=float(residual),
                initial_distance_upper=1.2,
                tolerance=float(tolerance),
            )
            positive = margin is not None and margin > 1.0e-5
            if positive:
                numerical_attainable.append(StoppingPair(baseline_calls, hybrid_calls))
            cells.append(
                {
                    "baseline_calls": baseline_calls,
                    "hybrid_calls": hybrid_calls,
                    "status": status,
                    "strict_margin": margin,
                    "positive_margin": positive,
                }
            )

    exact_pairs = [StoppingPair(1, 0)]
    cost = Fraction(1, 2)
    minimum_saved_calls = 1
    decision = transcript_optimal_gate(
        exact_pairs, float(cost), minimum_saved_calls=minimum_saved_calls
    )
    if numerical_attainable != exact_pairs or not decision.accept_joint:
        raise RuntimeError("PEP enumeration and exact certificate must agree")

    bad_cells = [
        [r, s]
        for r in range(horizon + 1)
        for s in range(horizon + 1)
        if Fraction(s - r) + max(Fraction(minimum_saved_calls), cost) > 0
    ]
    generic_dual_payload = json.loads(GENERIC_DUAL.read_text(encoding="utf-8"))
    generic_dual_result = verify_generic_dual(generic_dual_payload, root=ROOT)
    generic_dual_cells = generic_dual_result["cells"]
    if generic_dual_cells != bad_cells:
        raise RuntimeError("the recovered generic dual suite must exclude every bad cell")
    if (
        generic_dual_result["realization_dimension"] != 2
        or generic_dual_result["natural_horizon"] != natural_horizon
        or generic_dual_result["audit_horizon"] != horizon
    ):
        raise RuntimeError("generic dual suite realization or horizon mismatch")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": (
            "A genuinely two-dimensional, non-shift, nonquadratic realized "
            "instance has formula-derived horizon H0=2. A one-layer padded H=3 "
            "joint PEP audit is accepted: ten recovered rational Gram-SDP duals "
            "exclude all cost-violating cells, while contraction bounds separately "
            "validate the realized stopping pair."
        ),
        "function": {
            "formula": "f(z)=9*||z||^2/20+sum_i log(cosh(z_i))/10 in R^2",
            "gradient": "grad_i f(z)=9*z_i/10+tanh(z_i)/10",
            "hessian": "H_ii(z)=9/10+sech(z_i)^2/10, H_ij=0 for i!=j",
            "third_derivative": "partial_iii f(z)=-sech(z_i)^2*tanh(z_i)/5",
            "nonquadratic_witness": "partial_111 f(x)<0",
        },
        "parameters": {
            "strong_convexity": str(mu),
            "smoothness": str(smoothness),
            "step_size": "1",
            "tolerance": str(tolerance),
            "proposal_residual_upper": str(residual),
            "proposal_norm_lower": str(proposal_lower),
            "proposal_norm_upper": str(proposal_upper),
            "initial_distance_upper": "6/5",
            "natural_horizon": natural_horizon,
            "audit_padding": audit_padding,
            "horizon": horizon,
            "cost_exact_units": str(cost),
            "minimum_saved_calls": minimum_saved_calls,
        },
        "actual_instance": actual,
        "exact_certificate": {
            "current_gradient_lower": str(current_gradient_lower),
            "current_gradient_upper": str(current_gradient_upper),
            "gradient_step_contraction": str(contraction),
            "baseline_gradient_after_one_upper": str(baseline_one_upper),
            "candidate_gradient_upper": str(candidate_gradient_upper),
            "strict_pair": [1, 0],
            "cost_violating_cells": bad_cells,
            "excluded_cost_violating_cell_count": len(bad_cells),
            "analytic_excluded_cells": [],
            "generic_dual_excluded_cells": generic_dual_cells,
            "generic_dual_certificate_count": generic_dual_result[
                "certificate_count"
            ],
            "generic_dual_positive_leading_minors": generic_dual_result[
                "positive_leading_minors"
            ],
            "generic_dual_payload_sha256": generic_dual_result["payload_sha256"],
        },
        "pep_enumeration": {
            "cell_count": len(cells),
            "positive_margin_pairs": [
                [pair.baseline_calls, pair.hybrid_calls]
                for pair in numerical_attainable
            ],
            "cells": cells,
        },
        "gate": {
            "joint_accept": decision.accept_joint,
            "rectangle_accept": decision.accept_rectangle,
            "worst_joint_call_difference": decision.worst_joint_call_difference,
            "rectangle_call_difference": decision.rectangle_call_difference,
            "certificate_value": decision.transcript_certificate_value,
            "declared_all_in_cost_ratio": float(cost),
        },
        "environment": {
            "python": platform.python_version(),
            "runner_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(
                ROOT / "tools" / "verify_nonlinear_joint_pep_acceptance.py"
            ),
            "generic_dual_file_sha256": _file_hash(GENERIC_DUAL),
            "source_sha256": {
                "src/c2ogate/transcript.py": _file_hash(
                    ROOT / "src" / "c2ogate" / "transcript.py"
                ),
                "experiments/run_transcript_pep_study.py": _file_hash(
                    ROOT / "experiments" / "run_transcript_pep_study.py"
                ),
            },
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "FROZEN: two-dimensional nonlinear joint PEP acceptance, natural H0=2, "
        "padded cells 16, exact pair (1,0), "
        f"payload {payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
