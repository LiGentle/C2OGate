#!/usr/bin/env python3
"""Independent PEPit differential checks of the exact padded cell models."""

from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
from typing import Any

import cvxpy as cp
import numpy as np
from PEPit import PEP
from PEPit.functions import SmoothStronglyConvexFunction

from generate_generic_pep_dual_certificate import _build_problem


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "padded_model_crosscheck.json"
SCHEMA = "c2o-padded-model-crosscheck-v1"


SUITES: tuple[dict[str, Any], ...] = (
    {
        "name": "full-class-H3",
        "horizon": 3,
        "cells": ((1, 1), (2, 2), (3, 3)),
        "mu": Fraction(1, 2),
        "smoothness": Fraction(1),
        "step_size": Fraction(1),
        "proposal_step": Fraction(11, 10),
        "proposal_lower": Fraction(27, 50),
        "proposal_upper": Fraction(14, 25),
        "contract_radius": Fraction(1, 100),
        "initial_distance_upper": Fraction(1),
        "tolerance": Fraction(1, 5),
        "trace_bound": Fraction(16),
    },
    {
        "name": "unified-H6",
        "horizon": 6,
        "cells": ((1, 1), (3, 3), (6, 6)),
        "mu": Fraction(3, 10),
        "smoothness": Fraction(1),
        "step_size": Fraction(1),
        "proposal_step": Fraction(11, 10),
        "proposal_lower": Fraction(27, 50),
        "proposal_upper": Fraction(14, 25),
        "contract_radius": Fraction(1, 100),
        "initial_distance_upper": Fraction(9, 5),
        "tolerance": Fraction(7, 25),
        "trace_bound": Fraction(66),
    },
    {
        "name": "stress-H10",
        "horizon": 10,
        "cells": ((1, 1), (5, 5), (10, 10)),
        "mu": Fraction(1, 10),
        "smoothness": Fraction(1),
        "step_size": Fraction(1),
        "proposal_step": Fraction(1),
        "proposal_lower": Fraction(79, 100),
        "proposal_upper": Fraction(81, 100),
        "contract_radius": Fraction(1, 10),
        "initial_distance_upper": Fraction(1),
        "tolerance": Fraction(2, 3),
        "trace_bound": Fraction(49),
    },
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _native_value(cell: tuple[int, int], suite: dict[str, Any]) -> float:
    problem, *_ = _build_problem(
        cell,
        signed_terminal_margin=True,
        horizon=suite["horizon"],
        mu=suite["mu"],
        smoothness=suite["smoothness"],
        step_size=suite["step_size"],
        proposal_step=suite["proposal_step"],
        proposal_lower=suite["proposal_lower"],
        proposal_upper=suite["proposal_upper"],
        contract_radius=suite["contract_radius"],
        initial_distance_upper=suite["initial_distance_upper"],
        tolerance=suite["tolerance"],
        trace_bound=suite["trace_bound"],
    )
    value = problem.solve(
        solver="CLARABEL",
        tol_gap_abs=1.0e-9,
        tol_feas=1.0e-9,
        tol_gap_rel=1.0e-9,
        max_iter=1500,
        verbose=False,
    )
    if problem.status not in {"optimal", "optimal_inaccurate"} or value is None:
        raise RuntimeError(f"native solve failed for {suite['name']} {cell}")
    return float(value)


def _pepit_value(cell: tuple[int, int], suite: dict[str, Any]) -> float:
    baseline_calls, candidate_calls = cell
    horizon = suite["horizon"]
    problem = PEP()
    function = problem.declare_function(
        SmoothStronglyConvexFunction,
        mu=float(suite["mu"]),
        L=float(suite["smoothness"]),
    )
    optimum = function.stationary_point()
    baseline_start = problem.set_initial_point()
    candidate_start = problem.set_initial_point()
    baseline_gradient, _ = function.oracle(baseline_start)
    displacement = candidate_start - baseline_start
    problem.set_initial_condition(
        (baseline_start - optimum) ** 2
        <= float(suite["initial_distance_upper"]) ** 2
    )
    problem.set_initial_condition(
        displacement**2 >= float(suite["proposal_lower"]) ** 2
    )
    problem.set_initial_condition(
        displacement**2 <= float(suite["proposal_upper"]) ** 2
    )
    problem.set_initial_condition(
        (
            displacement
            + float(suite["proposal_step"]) * baseline_gradient
        )
        ** 2
        <= float(suite["contract_radius"]) ** 2
    )

    baseline_gradients = [baseline_gradient]
    point = baseline_start
    for _ in range(horizon):
        point = point - float(suite["step_size"]) * baseline_gradients[-1]
        baseline_gradients.append(function.gradient(point))
    candidate_gradients = []
    point = candidate_start
    for iteration in range(horizon + 1):
        candidate_gradients.append(function.gradient(point))
        if iteration < horizon:
            point = point - float(suite["step_size"]) * candidate_gradients[-1]

    # This is the actual padded exact formula: all H+1 gradients are sampled,
    # and the redundant trace row is present.  The final constant metric is the
    # native margin-upper row written as a PEPit expression.
    trace = sum(
        gradient**2
        for gradient in baseline_gradients + candidate_gradients
    ) + (baseline_start - optimum) ** 2 + displacement**2
    problem.set_initial_condition(trace <= float(suite["trace_bound"]))
    tolerance_squared = float(suite["tolerance"]) ** 2
    for gradient in (
        baseline_gradients[:baseline_calls]
        + candidate_gradients[:candidate_calls]
    ):
        problem.set_performance_metric(gradient**2 - tolerance_squared)
    problem.set_performance_metric(
        tolerance_squared - baseline_gradients[baseline_calls] ** 2
    )
    problem.set_performance_metric(
        tolerance_squared - candidate_gradients[candidate_calls] ** 2
    )
    margin_upper = float(suite["smoothness"]) ** 2 * (
        float(suite["initial_distance_upper"])
        + float(suite["proposal_upper"])
    ) ** 2
    problem.set_performance_metric(
        margin_upper + 0 * baseline_gradients[0] ** 2
    )
    value = problem.solve(
        wrapper="cvxpy",
        solver="CLARABEL",
        verbose=0,
        safe_mode=False,
        tol_gap_abs=1.0e-9,
        tol_feas=1.0e-9,
        tol_gap_rel=1.0e-9,
        max_iter=1500,
    )
    return float(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--tolerance", type=float, default=2.0e-6)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for suite in SUITES:
        for cell in suite["cells"]:
            native = _native_value(cell, suite)
            pepit = _pepit_value(cell, suite)
            difference = abs(native - pepit)
            if difference > args.tolerance:
                raise RuntimeError(
                    f"padded-model mismatch for {suite['name']} {cell}: "
                    f"{native} versus {pepit}"
                )
            rows.append(
                {
                    "suite": suite["name"],
                    "horizon": suite["horizon"],
                    "cell": list(cell),
                    "native_margin": native,
                    "pepit_margin": pepit,
                    "absolute_difference": difference,
                    "trace_bound": str(suite["trace_bound"]),
                    "margin_upper": str(
                        suite["smoothness"] ** 2
                        * (
                            suite["initial_distance_upper"]
                            + suite["proposal_upper"]
                        )
                        ** 2
                    ),
                }
            )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": (
                "independent PEPit 0.5.1 differential check of representative "
                "padded H=3, H=6, and H=10 exact-suite cells"
            ),
            "formula": (
                "both paths sample all H+1 gradients; proposal interval, residual "
                "ball, distance, signed survival/terminal margin, redundant trace, "
                "and redundant margin-upper rows are included"
            ),
            "qualification": (
                "this catches many semantic-to-coefficient builder errors but is "
                "a numerical cross-check, not a formal proof of either builder"
            ),
            "comparison_tolerance": args.tolerance,
        },
        "summary": {
            "suite_count": len(SUITES),
            "cell_count": len(rows),
            "maximum_absolute_difference": max(
                row["absolute_difference"] for row in rows
            ),
            "all_within_tolerance": True,
        },
        "rows": rows,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "clarabel": importlib.metadata.version("clarabel"),
            "pepit": importlib.metadata.version("PEPit"),
            "runner_sha256": _file_hash(Path(__file__)),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "FROZEN: padded PEPit differential, "
        f"{len(rows)} cells / {len(SUITES)} suites, "
        f"max_abs={payload['summary']['maximum_absolute_difference']:.3e}, "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
