#!/usr/bin/env python3
"""Compare the C2OGate cell layer with the generic PEPit front end."""

from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.metadata
import json
from math import isfinite
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
SCHEMA = "c2o-pepit-backend-comparison-v2"


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
) -> dict[str, float]:
    build_started = perf_counter()
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
    model_build_seconds = perf_counter() - build_started
    solve_started = perf_counter()
    value = float(
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
    solve_wall_seconds = perf_counter() - solve_started
    solver_numeric_seconds = float(problem.wrapper.prob.solver_stats.solve_time)
    return {
        "value": value,
        "model_build_seconds": model_build_seconds,
        "solve_wall_seconds": solve_wall_seconds,
        "solver_numeric_seconds": solver_numeric_seconds,
    }


def _c2ogate_cell(
    baseline_calls: int,
    hybrid_calls: int,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Run one native cell and capture Clarabel's own numerical time.

    The imported native helper intentionally exposes only model-build and
    solve-call wall times.  This serial benchmark temporarily wraps CVXPY's
    solve method to read the solver-reported kernel time from the same problem;
    fallback is disabled, so exactly one solve is expected.
    """

    numeric_times: list[float] = []
    original_solve = cp.Problem.solve

    def recording_solve(problem: cp.Problem, *args: Any, **kwargs: Any) -> Any:
        value = original_solve(problem, *args, **kwargs)
        numeric = problem.solver_stats.solve_time
        numeric_times.append(float(numeric) if numeric is not None else 0.0)
        return value

    cp.Problem.solve = recording_solve
    try:
        row = _solve_cell((baseline_calls, hybrid_calls, parameters))
    finally:
        cp.Problem.solve = original_solve
    if len(numeric_times) != 1 or not isfinite(numeric_times[0]):
        raise RuntimeError("expected one finite native solver timing")
    return {
        "value": row["strict_margin"],
        "status": row["status"],
        "model_build_seconds": float(row["setup_seconds"]),
        "solve_wall_seconds": float(row["solve_seconds"]),
        "solver_numeric_seconds": numeric_times[0],
    }


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
    model_build_seconds = 0.0
    solve_wall_seconds = 0.0
    solver_numeric_seconds = 0.0
    started = perf_counter()
    for baseline, hybrid in cells:
        if backend == "c2ogate":
            row = _c2ogate_cell(baseline, hybrid, parameters)
            statuses.append(row["status"])
            if row["value"] is not None:
                values.append(float(row["value"]))
        elif backend == "pepit":
            try:
                row = _pepit_cell(baseline, hybrid, parameters)
                values.append(row["value"])
                statuses.append("solved")
            except Exception as error:  # PEPit exposes backend exceptions directly.
                statuses.append(f"error:{type(error).__name__}")
                continue
        else:
            raise ValueError(f"unknown backend: {backend}")
        model_build_seconds += row["model_build_seconds"]
        solve_wall_seconds += row["solve_wall_seconds"]
        solver_numeric_seconds += row["solver_numeric_seconds"]
    wall_seconds = perf_counter() - started
    framework_seconds = max(
        0.0, model_build_seconds + solve_wall_seconds - solver_numeric_seconds
    )
    loop_overhead_seconds = max(
        0.0, wall_seconds - model_build_seconds - solve_wall_seconds
    )
    return {
        "backend": backend,
        "horizon": horizon,
        "bad_cell_count": len(cells),
        "wall_seconds": wall_seconds,
        "model_build_seconds": model_build_seconds,
        "solve_call_seconds": solve_wall_seconds,
        "solver_numeric_seconds": solver_numeric_seconds,
        "framework_and_canonicalization_seconds": framework_seconds,
        "loop_and_measurement_overhead_seconds": loop_overhead_seconds,
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


def _installation_provenance() -> dict[str, Any]:
    distribution = importlib.metadata.distribution("PEPit")
    metadata = distribution.metadata
    installer_file = next(
        (item for item in distribution.files or [] if str(item).endswith("INSTALLER")),
        None,
    )
    installer = (
        distribution.locate_file(installer_file).read_text(encoding="utf-8").strip()
        if installer_file is not None
        else "unrecorded"
    )
    direct_url_present = any(
        str(item).endswith("direct_url.json") for item in distribution.files or []
    )
    return {
        "pinned_requirement": "PEPit==0.5.1",
        "project_optional_extra": "pep",
        "reproduction_command": "uv pip install -e '.[pep]'",
        "installer_metadata": installer,
        "direct_url_metadata_present": direct_url_present,
        "package_home_page": metadata.get("Home-page"),
        "package_download_url": metadata.get("Download-URL"),
        "official_documentation": "https://pepit.readthedocs.io/en/0.5.1/",
        "pypi_release": "https://pypi.org/project/PEPit/0.5.1/",
        "qualification": (
            "the environment metadata records the installer but no direct URL; "
            "the artifact therefore reports the pinned public distribution and "
            "does not infer a package-index mirror"
        ),
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
                    "model_build_seconds": _quantiles(
                        [row["model_build_seconds"] for row in group]
                    ),
                    "solve_call_seconds": _quantiles(
                        [row["solve_call_seconds"] for row in group]
                    ),
                    "solver_numeric_seconds": _quantiles(
                        [row["solver_numeric_seconds"] for row in group]
                    ),
                    "framework_and_canonicalization_seconds": _quantiles(
                        [
                            row["framework_and_canonicalization_seconds"]
                            for row in group
                        ]
                    ),
                    "loop_and_measurement_overhead_seconds": _quantiles(
                        [
                            row["loop_and_measurement_overhead_seconds"]
                            for row in group
                        ]
                    ),
                    "status_counts_by_repeat": [
                        row["status_counts"] for row in group
                    ],
                }
            )
    comparison_to_pepit = []
    for horizon in args.horizons:
        by_backend = {
            row["backend"]: row for row in summary if row["horizon"] == horizon
        }
        native = by_backend["c2ogate"]
        pepit = by_backend["pepit"]
        comparison_to_pepit.append(
            {
                "horizon": horizon,
                "end_to_end_ratio_c2ogate_over_pepit": (
                    native["wall_seconds"]["median"]
                    / pepit["wall_seconds"]["median"]
                ),
                "median_extra_seconds_c2ogate_minus_pepit": {
                    key: native[key]["median"] - pepit[key]["median"]
                    for key in (
                        "wall_seconds",
                        "model_build_seconds",
                        "framework_and_canonicalization_seconds",
                        "solver_numeric_seconds",
                        "loop_and_measurement_overhead_seconds",
                    )
                },
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
            "timing_decomposition": (
                "total wall; Python model construction; solve-call wall; "
                "Clarabel-reported numerical kernel; and the residual "
                "framework/canonicalization time = build + solve-call - kernel"
            ),
            "why_not_build_on_pepit": (
                "PEPit is suitable and faster for floating PEP construction, but "
                "its solver-facing coefficient arrays are not the acceptance "
                "object. C2OGate keeps a small domain-specific exact coefficient "
                "builder so the consumer can reconstruct named rows over Q, reject "
                "unknown or missing rows, and replay rational dual identities "
                "without importing PEPit, CVXPY, or a conic solver. A future PEPit "
                "producer adapter would be compatible if it emitted this schema."
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
            "pepit_installation": _installation_provenance(),
        },
        "summary": summary,
        "comparison_to_pepit": comparison_to_pepit,
        "runs": runs,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
