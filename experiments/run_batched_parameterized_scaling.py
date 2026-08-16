#!/usr/bin/env python3
"""Benchmark one parameterized padded PEP reused across stopping cells.

The numerical SDP remains outside the acceptance boundary.  This experiment
implements a concrete scaling mechanism: build and canonicalize one padded
problem, change only exact cell-selector parameters, and warm-start consecutive
solves.  It compares the resulting margins with the existing ragged builder on
selected cells and freezes wall time and peak RSS at H=15.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import resource
import sys
from time import perf_counter
from typing import Any

import cvxpy as cp
import numpy as np

from run_generic_pep_scaling_study import _solve_cell
from run_generic_pep_solver_benchmark import _parameters


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "batched_parameterized_scaling.json"
SCHEMA = "c2o-batched-parameterized-scaling-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _peak_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value / (1024.0**2) if sys.platform == "darwin" else value / 1024.0


def _inner(gram: cp.Variable, left: np.ndarray, right: np.ndarray) -> Any:
    return cp.sum(cp.multiply(np.outer(left, right), gram))


def _build_parameterized_problem(horizon: int, parameters: dict[str, Any]):
    branch_size = horizon + 1
    atom_count = 2 * branch_size + 2
    value_count = 2 * branch_size + 1
    gram = cp.Variable((atom_count, atom_count), symmetric=True)
    values = cp.Variable(value_count)
    margin = cp.Variable()
    baseline_terminal = cp.Parameter(branch_size, nonneg=True)
    hybrid_terminal = cp.Parameter(branch_size, nonneg=True)
    baseline_survival = cp.Parameter(branch_size, nonneg=True)
    hybrid_survival = cp.Parameter(branch_size, nonneg=True)

    unit = np.eye(atom_count)
    baseline_gradients = [unit[index] for index in range(branch_size)]
    hybrid_gradients = [unit[branch_size + index] for index in range(branch_size)]
    optimum = unit[-2]
    proposal = unit[-1]
    zero = np.zeros(atom_count)
    step = parameters["step_size"]
    baseline_points = [zero]
    hybrid_points = [proposal]
    for index in range(1, branch_size):
        baseline_points.append(
            -step * sum(baseline_gradients[:index], start=zero.copy())
        )
        hybrid_points.append(
            proposal
            - step * sum(hybrid_gradients[:index], start=zero.copy())
        )
    points = [*baseline_points, *hybrid_points, optimum]
    gradients = [*baseline_gradients, *hybrid_gradients, zero]

    mu = parameters["strong_convexity"]
    smoothness = parameters["smoothness"]
    proposal_step = parameters["proposal_step"]
    proposal_norm = parameters["proposal_norm"]
    contract_radius = parameters["contract_radius"]
    distance = parameters["initial_distance_upper"]
    tolerance_squared = parameters["tolerance"] ** 2
    gradient_bound = smoothness**2 * (distance + proposal_norm) ** 2
    trace_bound = (
        2 * branch_size * gradient_bound + distance**2 + proposal_norm**2
    )
    deactivate = tolerance_squared + gradient_bound

    constraints: list[Any] = [
        gram >> 0,
        values[0] == 0.0,
        _inner(gram, proposal, proposal) == proposal_norm**2,
        _inner(gram, optimum, optimum) <= distance**2,
        _inner(
            gram,
            proposal + proposal_step * baseline_gradients[0],
            proposal + proposal_step * baseline_gradients[0],
        )
        <= contract_radius**2,
        cp.trace(gram) <= trace_bound,
        margin <= gradient_bound,
    ]
    denominator = 2.0 * (1.0 - mu / smoothness)
    for i, point_i in enumerate(points):
        for j, point_j in enumerate(points):
            if i == j:
                continue
            dx = point_i - point_j
            dg = gradients[i] - gradients[j]
            left = values[i] - values[j] - _inner(gram, gradients[j], dx)
            right = (
                _inner(gram, dg, dg) / smoothness
                + mu * _inner(gram, dx, dx)
                - 2.0 * mu / smoothness * _inner(gram, dg, dx)
            ) / denominator
            constraints.append(left >= right)

    baseline_norms = cp.hstack(
        [_inner(gram, gradient, gradient) for gradient in baseline_gradients]
    )
    hybrid_norms = cp.hstack(
        [_inner(gram, gradient, gradient) for gradient in hybrid_gradients]
    )
    constraints.extend(
        [
            baseline_terminal @ baseline_norms <= tolerance_squared - margin,
            hybrid_terminal @ hybrid_norms <= tolerance_squared - margin,
            baseline_norms
            >= tolerance_squared
            + margin
            - deactivate * (1.0 - baseline_survival),
            hybrid_norms
            >= tolerance_squared
            + margin
            - deactivate * (1.0 - hybrid_survival),
        ]
    )
    problem = cp.Problem(cp.Maximize(margin), constraints)
    selectors = (
        baseline_terminal,
        hybrid_terminal,
        baseline_survival,
        hybrid_survival,
    )
    metadata = {
        "atom_count": atom_count,
        "value_count": value_count,
        "constraint_count": len(constraints),
        "trace_bound": trace_bound,
        "deactivation_constant": deactivate,
        "is_dpp": bool(problem.is_dpp()),
    }
    return problem, selectors, metadata


def _set_cell(selectors: tuple[Any, ...], horizon: int, cell: tuple[int, int]):
    baseline_calls, hybrid_calls = cell
    branch_size = horizon + 1
    baseline_terminal = np.zeros(branch_size)
    hybrid_terminal = np.zeros(branch_size)
    baseline_survival = np.zeros(branch_size)
    hybrid_survival = np.zeros(branch_size)
    baseline_terminal[baseline_calls] = 1.0
    hybrid_terminal[hybrid_calls] = 1.0
    baseline_survival[:baseline_calls] = 1.0
    hybrid_survival[:hybrid_calls] = 1.0
    for parameter, value in zip(
        selectors,
        (
            baseline_terminal,
            hybrid_terminal,
            baseline_survival,
            hybrid_survival,
        ),
        strict=True,
    ):
        parameter.value = value


def _solve(horizon: int) -> dict[str, Any]:
    parameters = _parameters(horizon, "CLARABEL")
    cells = [
        (baseline, hybrid)
        for baseline in range(horizon + 1)
        for hybrid in range(horizon + 1)
        if hybrid >= baseline
    ]
    build_started = perf_counter()
    problem, selectors, metadata = _build_parameterized_problem(horizon, parameters)
    build_seconds = perf_counter() - build_started
    rows = []
    started = perf_counter()
    for index, cell in enumerate(cells):
        _set_cell(selectors, horizon, cell)
        value = problem.solve(
            solver="CLARABEL",
            tol_gap_abs=1.0e-8,
            tol_feas=1.0e-8,
            tol_gap_rel=1.0e-8,
            max_iter=500,
            warm_start=index > 0,
            verbose=False,
        )
        rows.append(
            {
                "cell": list(cell),
                "status": problem.status,
                "margin": None if value is None else float(value),
                "solver_seconds": float(problem.solver_stats.solve_time or 0.0),
            }
        )
    wall_seconds = perf_counter() - started
    peak_rss = _peak_rss_mib()

    sample_cells = sorted({cells[0], cells[len(cells) // 2], cells[-1]})
    comparisons = []
    by_cell = {tuple(row["cell"]): row for row in rows}
    for cell in sample_cells:
        ragged = _solve_cell((cell[0], cell[1], parameters))
        batched_margin = by_cell[cell]["margin"]
        ragged_margin = ragged["strict_margin"]
        comparisons.append(
            {
                "cell": list(cell),
                "batched_margin": batched_margin,
                "ragged_margin": ragged_margin,
                "absolute_difference": abs(batched_margin - ragged_margin),
            }
        )
    return {
        "horizon": horizon,
        "cell_count": len(cells),
        "build_seconds": build_seconds,
        "enumeration_wall_seconds": wall_seconds,
        "summed_solver_seconds": sum(row["solver_seconds"] for row in rows),
        "peak_rss_mib": peak_rss,
        "status_counts": {
            status: sum(row["status"] == status for row in rows)
            for status in sorted({row["status"] for row in rows})
        },
        "metadata": metadata,
        "sample_crosscheck": comparisons,
        "maximum_sample_margin_difference": max(
            row["absolute_difference"] for row in comparisons
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=15)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = _solve(args.horizon)
    ragged_path = ROOT / "results" / "h15_scaling_diagnostic.json"
    ragged = json.loads(ragged_path.read_text(encoding="utf-8"))["run"]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": (
                "floating scaling evidence; neither solver status nor warm-start "
                "state is an acceptance certificate"
            ),
            "implemented_mechanism": (
                "one DPP parameterized padded model reuses canonicalization and "
                "warm-start state across every stopping cell"
            ),
        },
        "batched": result,
        "ragged_frozen_comparator": {
            "wall_seconds": ragged["wall_seconds"],
            "peak_rss_mib": ragged["peak_rss_mib"],
            "worker_count": ragged["worker_count"],
            "cell_count": ragged["bad_cell_count"],
        },
        "ratios": {
            "batched_over_ragged_wall": (
                result["enumeration_wall_seconds"] / ragged["wall_seconds"]
            ),
            "batched_over_ragged_peak_rss": (
                result["peak_rss_mib"] / ragged["peak_rss_mib"]
            ),
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "clarabel": __import__("clarabel").__version__,
            "runner_sha256": _file_hash(Path(__file__)),
            "ragged_payload_sha256": _file_hash(ragged_path),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "FROZEN: parameterized batched H="
        f"{args.horizon}, cells={result['cell_count']}, "
        f"wall={result['enumeration_wall_seconds']:.1f}s, "
        f"rss={result['peak_rss_mib']:.1f}MiB, "
        f"wall_ratio={payload['ratios']['batched_over_ragged_wall']:.3f}, "
        f"rss_ratio={payload['ratios']['batched_over_ragged_peak_rss']:.3f}"
    )


if __name__ == "__main__":
    main()
