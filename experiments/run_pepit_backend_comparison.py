#!/usr/bin/env python3
"""Compare the C2OGate cell layer with the generic PEPit front end."""

from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any
import warnings

import cvxpy as cp
import numpy as np
from PEPit import PEP
from PEPit.functions import SmoothStronglyConvexFunction

from run_generic_pep_solver_benchmark import _parameters
from run_generic_pep_scaling_study import _solve_cell


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "pepit_backend_comparison.json"
SCHEMA = "c2o-pepit-backend-comparison-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _pepit_cell(
    baseline_calls: int,
    hybrid_calls: int,
    parameters: dict[str, Any],
) -> float:
    problem = PEP()
    function = problem.declare_function(
        SmoothStronglyConvexFunction,
        mu=parameters["strong_convexity"],
        L=parameters["smoothness"],
    )
    optimum = function.stationary_point()
    baseline_start = problem.set_initial_point()
    hybrid_start = problem.set_initial_point()
    baseline_gradient, _ = function.oracle(baseline_start)
    problem.set_initial_condition(
        (baseline_start - optimum) ** 2
        <= parameters["initial_distance_upper"] ** 2
    )
    displacement = hybrid_start - baseline_start
    problem.set_initial_condition(
        displacement**2 == parameters["proposal_norm"] ** 2
    )
    problem.set_initial_condition(
        (displacement + parameters["proposal_step"] * baseline_gradient) ** 2
        <= parameters["contract_radius"] ** 2
    )
    baseline_gradients = [baseline_gradient]
    point = baseline_start
    for _ in range(baseline_calls):
        point = point - parameters["step_size"] * baseline_gradients[-1]
        baseline_gradients.append(function.gradient(point))
    hybrid_gradients = []
    point = hybrid_start
    for index in range(hybrid_calls + 1):
        hybrid_gradients.append(function.gradient(point))
        if index < hybrid_calls:
            point = point - parameters["step_size"] * hybrid_gradients[-1]
    tolerance_squared = parameters["tolerance"] ** 2
    for gradient in baseline_gradients[:-1] + hybrid_gradients[:-1]:
        problem.set_performance_metric(gradient**2 - tolerance_squared)
    problem.set_performance_metric(
        tolerance_squared - baseline_gradients[-1] ** 2
    )
    problem.set_performance_metric(
        tolerance_squared - hybrid_gradients[-1] ** 2
    )
    return float(
        problem.solve(
            wrapper="cvxpy",
            solver="CLARABEL",
            verbose=0,
            safe_mode=False,
            tol_gap_abs=1.0e-8,
            tol_feas=1.0e-8,
            tol_gap_rel=1.0e-8,
            max_iter=500,
        )
    )


def _run_backend(horizon: int, backend: str) -> dict[str, Any]:
    parameters = _parameters(horizon, "CLARABEL")
    parameters["allow_solver_fallback"] = False
    cells = [
        (baseline, hybrid)
        for baseline in range(horizon + 1)
        for hybrid in range(horizon + 1)
        if hybrid >= baseline
    ]
    values: list[float] = []
    statuses: list[str] = []
    started = perf_counter()
    for baseline, hybrid in cells:
        if backend == "c2ogate":
            row = _solve_cell((baseline, hybrid, parameters))
            statuses.append(row["status"])
            if row["strict_margin"] is not None:
                values.append(float(row["strict_margin"]))
        elif backend == "pepit":
            try:
                values.append(_pepit_cell(baseline, hybrid, parameters))
                statuses.append("solved")
            except Exception as error:  # PEPit exposes backend exceptions directly.
                statuses.append(f"error:{type(error).__name__}")
        else:
            raise ValueError(f"unknown backend: {backend}")
    wall_seconds = perf_counter() - started
    return {
        "backend": backend,
        "horizon": horizon,
        "bad_cell_count": len(cells),
        "wall_seconds": wall_seconds,
        "status_counts": {
            status: statuses.count(status) for status in sorted(set(statuses))
        },
        "finite_value_count": len(values),
        "maximum_margin": max(values) if values else None,
    }


def _quantiles(values: list[float]) -> dict[str, float]:
    data = np.asarray(values, dtype=float)
    return {
        "median": float(np.median(data)),
        "q25": float(np.quantile(data, 0.25)),
        "q75": float(np.quantile(data, 0.75)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizons", type=int, nargs="+", default=[2, 6, 10])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    warnings.filterwarnings("ignore", message="Solution may be inaccurate")
    runs: list[dict[str, Any]] = []
    for backend in ("c2ogate", "pepit"):
        for horizon in args.horizons:
            for repeat in range(args.repeats):
                row = _run_backend(horizon, backend)
                row["repeat"] = repeat
                runs.append(row)
                print(
                    f"backend={backend} H={horizon} repeat={repeat + 1}/"
                    f"{args.repeats} wall={row['wall_seconds']:.3f}s",
                    flush=True,
                )
    summary = []
    for backend in ("c2ogate", "pepit"):
        for horizon in args.horizons:
            group = [
                row
                for row in runs
                if row["backend"] == backend and row["horizon"] == horizon
            ]
            summary.append(
                {
                    "backend": backend,
                    "horizon": horizon,
                    "repeat_count": len(group),
                    "bad_cell_count": group[0]["bad_cell_count"],
                    "wall_seconds": _quantiles(
                        [row["wall_seconds"] for row in group]
                    ),
                    "status_counts_by_repeat": [
                        row["status_counts"] for row in group
                    ],
                }
            )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "horizons": args.horizons,
            "repeat_count": args.repeats,
            "solver": "Clarabel through CVXPY",
            "execution": "serial complete bad-cell enumeration for both backends",
            "shared_model": (
                "same function class, two trajectories, proposal equality/contract, "
                "terminal and survival signed-margin metrics"
            ),
            "scope": (
                "PEPit is a generic modeling comparison; C2OGate's claimed increment "
                "is bad-cell generation, fail-closed aggregation, rational recovery, "
                "and independent verification, not a replacement PEP language"
            ),
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "pepit": importlib.metadata.version("PEPit"),
            "clarabel": __import__("clarabel").__version__,
            "runner_sha256": _file_hash(Path(__file__)),
        },
        "summary": summary,
        "runs": runs,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
