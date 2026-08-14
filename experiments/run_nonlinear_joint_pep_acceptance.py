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


SCHEMA = "c2o-nonlinear-joint-pep-acceptance-v1"


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


def _actual_trajectory() -> dict[str, str | int]:
    getcontext().prec = 100
    x = Decimal(1)
    residual = Decimal(1) / Decimal(100)
    gradient_x = _gradient(x)
    y = x - gradient_x + residual
    gradient_y = _gradient(y)
    x_one = x - gradient_x
    gradient_x_one = _gradient(x_one)
    tolerance = Decimal(7) / Decimal(50)
    if not (abs(gradient_x) > tolerance):
        raise RuntimeError("baseline must be nonterminal at the transcript point")
    if not (abs(gradient_x_one) < tolerance and abs(gradient_y) < tolerance):
        raise RuntimeError("both one-step and candidate terminal checks must be strict")
    return {
        "x": str(x),
        "gradient_x": str(gradient_x),
        "candidate_y": str(y),
        "candidate_residual": str(y - (x - gradient_x)),
        "gradient_y": str(gradient_y),
        "baseline_x_one": str(x_one),
        "gradient_x_one": str(gradient_x_one),
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

    proposal_norm = abs(float(Decimal(actual["candidate_y"]) - Decimal(1)))
    cells: list[dict[str, Any]] = []
    numerical_attainable: list[StoppingPair] = []
    horizon = 2
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
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": (
            "A non-shift, nonquadratic realized instance is accepted by the "
            "joint PEP gate. Exact rational contraction bounds, not floating "
            "solver statuses, exclude every cost-violating cell."
        ),
        "function": {
            "formula": "f(t)=9*t^2/20+log(cosh(t))/10",
            "gradient": "f'(t)=9*t/10+tanh(t)/10",
            "hessian": "f''(t)=9/10+sech(t)^2/10",
            "third_derivative": "f'''(t)=-sech(t)^2*tanh(t)/5",
            "nonquadratic_witness": "f'''(1)<0",
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
        "FROZEN: nonlinear joint PEP acceptance, cells 9, exact pair (1,0), "
        f"payload {payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
