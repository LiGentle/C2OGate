#!/usr/bin/env python3
"""Frozen timing audit for joint-cell and exact-shift PEP enumeration."""

from __future__ import annotations

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_transcript_pep_study import _run_pep_audit  # noqa: E402


SCHEMA = "c2o-pep-scaling-study-v1"
OUTPUT = ROOT / "results" / "pep_scaling_study.json"


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


def _reduced_shift_cell(
    stopping_time: int,
    *,
    strong_convexity: float,
    smoothness: float,
    step_size: float,
    initial_distance_upper: float,
    initial_gradient_norm: float,
    tolerance: float,
) -> dict[str, Any]:
    """Solve the one-trajectory PEP left by an exact one-step shift identity."""

    if stopping_time < 1:
        raise ValueError("the reduced cell has a positive stopping time")
    setup_started = perf_counter()
    gradient_count = stopping_time + 1
    atom_count = gradient_count + 1
    unit = np.eye(atom_count)
    gradients = [unit[k] for k in range(gradient_count)]
    optimum = unit[-1]
    zero = np.zeros(atom_count)
    points = [zero]
    for k in range(1, gradient_count):
        points.append(-step_size * sum(gradients[:k], start=zero.copy()))
    points.append(optimum)
    gradients_with_optimum = gradients + [zero]
    function_values = cp.Variable(len(points))
    gram = cp.Variable((atom_count, atom_count), symmetric=True)
    constraints: list[Any] = [
        gram >> 0,
        function_values[0] == 0.0,
        _inner(gram, gradients[0], gradients[0]) == initial_gradient_norm**2,
        _inner(gram, optimum, optimum) <= initial_distance_upper**2,
    ]
    denominator = 2.0 * (1.0 - strong_convexity / smoothness)
    for i in range(len(points)):
        for j in range(len(points)):
            if i == j:
                continue
            point_difference = points[i] - points[j]
            gradient_difference = gradients_with_optimum[i] - gradients_with_optimum[j]
            left = (
                function_values[i]
                - function_values[j]
                - _inner(gram, gradients_with_optimum[j], point_difference)
            )
            right = (
                _inner(gram, gradient_difference, gradient_difference) / smoothness
                + strong_convexity
                * _inner(gram, point_difference, point_difference)
                - 2.0
                * strong_convexity
                / smoothness
                * _inner(gram, gradient_difference, point_difference)
            ) / denominator
            constraints.append(left >= right)

    threshold_squared = tolerance**2
    margin = cp.Variable()
    constraints.extend(
        [
            _inner(gram, gradients[-1], gradients[-1]) <= threshold_squared,
            margin <= smoothness**2 * initial_distance_upper**2,
        ]
    )
    for gradient in gradients[:-1]:
        constraints.append(
            _inner(gram, gradient, gradient) >= threshold_squared + margin
        )
    problem = cp.Problem(cp.Maximize(margin), constraints)
    setup_seconds = perf_counter() - setup_started
    solve_started = perf_counter()
    solver = "CLARABEL"
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
        margin_value = float(value)
    return {
        "baseline_calls": stopping_time,
        "hybrid_calls": stopping_time - 1,
        "status": problem.status,
        "strict_margin": margin_value,
        "solver": solver,
        "gram_order": atom_count,
        "interpolation_point_count": len(points),
        "constraint_count": len(constraints),
        "setup_seconds": setup_seconds,
        "solve_seconds": solve_seconds,
    }


def _run_reduced_horizon(horizon: int) -> dict[str, Any]:
    strong_convexity = 0.1
    smoothness = 1.0
    step_size = 1.0
    initial_distance_upper = 1.0
    initial_gradient_norm = 0.8
    contraction = 0.9
    tolerance = (
        smoothness * initial_distance_upper * contraction ** (horizon - 0.25)
    )
    computed_horizon = ceil(
        log(tolerance / (smoothness * initial_distance_upper)) / log(contraction)
    )
    if computed_horizon != horizon or tolerance >= initial_gradient_norm:
        raise RuntimeError("scaling parameters do not realize the declared horizon")
    started = perf_counter()
    cells = [
        _reduced_shift_cell(
            stopping_time,
            strong_convexity=strong_convexity,
            smoothness=smoothness,
            step_size=step_size,
            initial_distance_upper=initial_distance_upper,
            initial_gradient_norm=initial_gradient_norm,
            tolerance=tolerance,
        )
        for stopping_time in range(1, horizon + 1)
    ]
    elapsed = perf_counter() - started
    positive = [
        cell
        for cell in cells
        if cell["strict_margin"] is not None and cell["strict_margin"] > 1.0e-5
    ]
    ambiguous = [
        cell
        for cell in cells
        if cell["strict_margin"] is not None
        and abs(cell["strict_margin"]) <= 1.0e-5
    ]
    nominal = (horizon + 1) ** 2
    return {
        "formulation": "exact-shift reduced one-trajectory PEP",
        "horizon": horizon,
        "nominal_joint_cell_count": nominal,
        "structurally_excluded_cell_count": nominal - horizon,
        "solved_sdp_cell_count": horizon,
        "positive_margin_cell_count": len(positive),
        "numerically_ambiguous_cell_count": len(ambiguous),
        "maximum_gram_order": max(cell["gram_order"] for cell in cells),
        "total_setup_seconds": sum(cell["setup_seconds"] for cell in cells),
        "total_solve_seconds": sum(cell["solve_seconds"] for cell in cells),
        "elapsed_seconds": elapsed,
        "parameters": {
            "strong_convexity": strong_convexity,
            "smoothness": smoothness,
            "step_size": step_size,
            "initial_distance_upper": initial_distance_upper,
            "initial_gradient_norm": initial_gradient_norm,
            "tolerance": tolerance,
            "contraction": contraction,
        },
        "cells": cells,
    }


def main() -> None:
    dense_started = perf_counter()
    dense = _run_pep_audit()
    dense_elapsed = perf_counter() - dense_started
    dense_reference = {
        "formulation": "dense two-trajectory joint PEP",
        "horizon": dense["parameters"]["horizon"],
        "nominal_joint_cell_count": dense["cell_count"],
        "structurally_excluded_cell_count": 0,
        "solved_sdp_cell_count": dense["cell_count"],
        "positive_margin_cell_count": len(dense["attainable_pairs"]),
        "numerically_ambiguous_cell_count": dense[
            "numerically_ambiguous_cell_count"
        ],
        "maximum_gram_order": 2 * (dense["parameters"]["horizon"] + 1) + 2,
        "elapsed_seconds": dense_elapsed,
    }
    reduced = [_run_reduced_horizon(horizon) for horizon in (10, 15, 20)]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "classification_threshold": 1.0e-5,
            "exact_prescreen": (
                "y=x-alpha*g(x) implies s=r-1 whenever ||g(x)|| exceeds tolerance"
            ),
            "scope": (
                "the H>=20 result is structure-exploiting and is not a generic dense-PEP "
                "scalability claim"
            ),
        },
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__).resolve()),
            "dense_runner_sha256": _file_hash(
                ROOT / "experiments" / "run_transcript_pep_study.py"
            ),
        },
        "dense_reference": dense_reference,
        "reduced_horizons": reduced,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8"
    )
    summary = {
        "dense_reference": dense_reference,
        "reduced_horizons": [
            {key: value for key, value in row.items() if key not in {"cells", "parameters"}}
            for row in reduced
        ],
        "payload_sha256": payload["payload_sha256"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
