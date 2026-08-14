#!/usr/bin/env python3
"""Generic H=20 ragged joint-PEP bad-cell enumeration.

Unlike the exact-shift scaling audit, this study assumes only a nonzero
proposal contract radius.  Every cost-violating cell is solved.  A cell uses
only the two trajectory prefixes needed to state its stopping times, rather
than padding both branches to the global horizon.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from math import ceil, log
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import cvxpy as cp
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "generic_pep_scaling_study.json"
SCHEMA = "c2o-generic-ragged-pep-scaling-v1"
CLASSIFICATION_THRESHOLD = 1.0e-5


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inner(matrix: cp.Variable, left: np.ndarray, right: np.ndarray) -> Any:
    return cp.sum(cp.multiply(np.outer(left, right), matrix))


def _solve_cell(task: tuple[int, int, dict[str, float]]) -> dict[str, Any]:
    baseline_calls, hybrid_calls, parameters = task
    strong_convexity = parameters["strong_convexity"]
    smoothness = parameters["smoothness"]
    step_size = parameters["step_size"]
    proposal_step = parameters["proposal_step"]
    proposal_norm = parameters["proposal_norm"]
    contract_radius = parameters["contract_radius"]
    initial_distance_upper = parameters["initial_distance_upper"]
    tolerance = parameters["tolerance"]

    setup_started = perf_counter()
    baseline_size = baseline_calls + 1
    hybrid_size = hybrid_calls + 1
    atom_count = baseline_size + hybrid_size + 2
    gram = cp.Variable((atom_count, atom_count), symmetric=True)
    function_values = cp.Variable(baseline_size + hybrid_size + 1)
    unit = np.eye(atom_count)
    baseline_gradients = [unit[k] for k in range(baseline_size)]
    hybrid_gradients = [unit[baseline_size + k] for k in range(hybrid_size)]
    optimum_point = unit[-2]
    proposal = unit[-1]
    zero = np.zeros(atom_count)

    baseline_points = [zero]
    for k in range(1, baseline_size):
        baseline_points.append(
            -step_size * sum(baseline_gradients[:k], start=zero.copy())
        )
    hybrid_points = [proposal]
    for k in range(1, hybrid_size):
        hybrid_points.append(
            proposal - step_size * sum(hybrid_gradients[:k], start=zero.copy())
        )
    points = baseline_points + hybrid_points + [optimum_point]
    gradients = baseline_gradients + hybrid_gradients + [zero]

    constraints: list[Any] = [
        gram >> 0,
        function_values[0] == 0.0,
        _inner(gram, proposal, proposal) == proposal_norm**2,
        _inner(gram, optimum_point, optimum_point) <= initial_distance_upper**2,
        _inner(
            gram,
            proposal + proposal_step * baseline_gradients[0],
            proposal + proposal_step * baseline_gradients[0],
        )
        <= contract_radius**2,
    ]
    denominator = 2.0 * (1.0 - strong_convexity / smoothness)
    for i in range(len(points)):
        for j in range(len(points)):
            if i == j:
                continue
            point_difference = points[i] - points[j]
            gradient_difference = gradients[i] - gradients[j]
            left = (
                function_values[i]
                - function_values[j]
                - _inner(gram, gradients[j], point_difference)
            )
            right = (
                _inner(gram, gradient_difference, gradient_difference) / smoothness
                + strong_convexity * _inner(gram, point_difference, point_difference)
                - 2.0
                * strong_convexity
                / smoothness
                * _inner(gram, gradient_difference, point_difference)
            ) / denominator
            constraints.append(left >= right)

    threshold_squared = tolerance**2
    constraints.extend(
        [
            _inner(
                gram,
                baseline_gradients[-1],
                baseline_gradients[-1],
            )
            <= threshold_squared,
            _inner(gram, hybrid_gradients[-1], hybrid_gradients[-1])
            <= threshold_squared,
        ]
    )
    strict_gradients = baseline_gradients[:-1] + hybrid_gradients[:-1]
    if strict_gradients:
        margin = cp.Variable()
        constraints.append(
            margin <= smoothness**2 * (initial_distance_upper + proposal_norm) ** 2
        )
        for gradient in strict_gradients:
            constraints.append(
                _inner(gram, gradient, gradient) >= threshold_squared + margin
            )
        objective = cp.Maximize(margin)
    else:
        margin = None
        objective = cp.Maximize(0.0)
    problem = cp.Problem(objective, constraints)
    setup_seconds = perf_counter() - setup_started

    solver = "CLARABEL"
    solve_started = perf_counter()
    try:
        value = problem.solve(
            solver=solver,
            tol_gap_abs=1.0e-8,
            tol_feas=1.0e-8,
            tol_gap_rel=1.0e-8,
            max_iter=500,
            verbose=False,
        )
    except cp.error.SolverError:
        solver = "SCS"
        value = problem.solve(
            solver=solver,
            eps=1.0e-7,
            max_iters=100_000,
            verbose=False,
        )
    solve_seconds = perf_counter() - solve_started
    margin_value = None
    if problem.status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
        margin_value = float(value if margin is not None else 1.0)
    return {
        "baseline_calls": baseline_calls,
        "hybrid_calls": hybrid_calls,
        "call_difference": hybrid_calls - baseline_calls,
        "status": problem.status,
        "strict_margin": margin_value,
        "attainable": bool(
            margin_value is not None and margin_value > CLASSIFICATION_THRESHOLD
        ),
        "numerically_ambiguous": bool(
            margin_value is not None and abs(margin_value) <= CLASSIFICATION_THRESHOLD
        ),
        "solver": solver,
        "gram_order": atom_count,
        "interpolation_point_count": len(points),
        "constraint_count": len(constraints),
        "setup_seconds": setup_seconds,
        "solve_seconds": solve_seconds,
    }


def _parameters(horizon: int) -> dict[str, float]:
    strong_convexity = 0.1
    smoothness = 1.0
    step_size = 1.0
    proposal_step = 1.0
    proposal_norm = 0.4
    contract_radius = 0.08
    initial_distance_upper = 1.0
    candidate_distance_upper = initial_distance_upper + proposal_norm
    contraction = 0.9
    tolerance = smoothness * candidate_distance_upper * contraction ** (horizon - 0.25)
    computed_horizon = ceil(
        log(tolerance / (smoothness * candidate_distance_upper)) / log(contraction)
    )
    if computed_horizon != horizon:
        raise RuntimeError("parameters do not realize the declared horizon")
    return {
        "strong_convexity": strong_convexity,
        "smoothness": smoothness,
        "step_size": step_size,
        "proposal_step": proposal_step,
        "proposal_norm": proposal_norm,
        "contract_radius": contract_radius,
        "initial_distance_upper": initial_distance_upper,
        "candidate_distance_upper": candidate_distance_upper,
        "contraction": contraction,
        "tolerance": tolerance,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.horizon < 1 or args.workers < 1:
        raise ValueError("invalid horizon or worker count")
    parameters = _parameters(args.horizon)
    cost_exact_units = 0.4
    minimum_saved_calls = 1
    threshold = max(cost_exact_units, float(minimum_saved_calls))
    bad_cells = [
        (r, s)
        for r in range(args.horizon + 1)
        for s in range(args.horizon + 1)
        if s - r + threshold > 0.0
    ]
    if args.smoke:
        selected = [(0, 0), (2, 2), (10, 10), (20, 20)]
        bad_cells = [cell for cell in selected if cell in bad_cells]
    tasks = [(r, s, parameters) for r, s in bad_cells]
    started = perf_counter()
    cells: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(_solve_cell, task) for task in tasks]
        for completed, future in enumerate(as_completed(futures), start=1):
            cells.append(future.result())
            if completed % 25 == 0 or completed == len(futures):
                print(f"completed {completed}/{len(futures)} cells", flush=True)
    elapsed_seconds = perf_counter() - started
    cells.sort(key=lambda row: (row["baseline_calls"], row["hybrid_calls"]))
    if args.smoke:
        print(json.dumps(cells, indent=2, sort_keys=True))
        return

    positive = [row for row in cells if row["attainable"]]
    ambiguous = [row for row in cells if row["numerically_ambiguous"]]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "horizon": args.horizon,
            "worker_count": args.workers,
            "nominal_joint_cell_count": (args.horizon + 1) ** 2,
            "bad_cell_rule": "s-r+max(m,c)>0",
            "bad_cell_count": len(bad_cells),
            "minimum_saved_calls": minimum_saved_calls,
            "cost_exact_units": cost_exact_units,
            "classification_threshold": CLASSIFICATION_THRESHOLD,
            "formulation": (
                "cell-specific ragged two-trajectory Gram SDP; no exact-shift identity"
            ),
            "scope": (
                "floating-point scalability audit; ambiguous or negative solver statuses "
                "are not proof certificates"
            ),
        },
        "parameters": parameters,
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__).resolve()),
        },
        "summary": {
            "solved_bad_cell_count": len(cells),
            "positive_margin_bad_cell_count": len(positive),
            "numerically_ambiguous_bad_cell_count": len(ambiguous),
            "maximum_gram_order": max(row["gram_order"] for row in cells),
            "median_gram_order": float(np.median([row["gram_order"] for row in cells])),
            "maximum_constraint_count": max(row["constraint_count"] for row in cells),
            "total_setup_cpu_seconds": sum(row["setup_seconds"] for row in cells),
            "total_solve_cpu_seconds": sum(row["solve_seconds"] for row in cells),
            "wall_seconds": elapsed_seconds,
            "joint_gate_rejects_from_positive_witness": bool(positive),
            "maximum_attainable_call_difference": max(
                (row["call_difference"] for row in positive), default=None
            ),
        },
        "cells": cells,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
