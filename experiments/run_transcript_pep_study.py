#!/usr/bin/env python3
"""Frozen study for transcript-optimal joint performance estimation."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import ceil, log
from pathlib import Path
import platform
import sys
from typing import Any

import cvxpy as cp
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from c2ogate.transcript import StoppingPair, transcript_optimal_gate  # noqa: E402


SCHEMA = "c2o-transcript-pep-study-v2"


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


def _cell_margin(
    baseline_calls: int,
    hybrid_calls: int,
    *,
    horizon: int,
    strong_convexity: float,
    smoothness: float,
    step_size: float,
    proposal_step: float,
    proposal_norm: float,
    contract_radius: float,
    initial_distance_upper: float,
    tolerance: float,
) -> tuple[str, float | None]:
    """Solve one exact stopping-time cell of the joint PEP."""

    if not 0 <= baseline_calls <= horizon or not 0 <= hybrid_calls <= horizon:
        raise ValueError("cell is outside the declared horizon")
    branch_size = horizon + 1
    atom_count = 2 * branch_size + 2
    gram = cp.Variable((atom_count, atom_count), symmetric=True)
    function_values = cp.Variable(2 * branch_size + 1)
    constraints: list[Any] = [gram >> 0]

    unit = np.eye(atom_count)
    baseline_gradients = [unit[k] for k in range(branch_size)]
    hybrid_gradients = [unit[branch_size + k] for k in range(branch_size)]
    optimum_point = unit[-2]
    proposal = unit[-1]
    zero = np.zeros(atom_count)

    baseline_points = [zero]
    for k in range(1, branch_size):
        baseline_points.append(
            -step_size * sum(baseline_gradients[:k], start=zero.copy())
        )
    hybrid_start = proposal
    hybrid_points = [hybrid_start]
    for k in range(1, branch_size):
        hybrid_points.append(
            hybrid_start
            - step_size * sum(hybrid_gradients[:k], start=zero.copy())
        )

    points = baseline_points + hybrid_points + [optimum_point]
    gradients = baseline_gradients + hybrid_gradients + [zero]
    constraints.extend(
        [
            function_values[0] == 0.0,
            _inner(gram, proposal, proposal) == proposal_norm**2,
            _inner(gram, optimum_point, optimum_point)
            <= initial_distance_upper**2,
            _inner(
                gram,
                proposal + proposal_step * baseline_gradients[0],
                proposal + proposal_step * baseline_gradients[0],
            )
            <= contract_radius**2,
        ]
    )

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
                _inner(gram, gradient_difference, gradient_difference)
                / smoothness
                + strong_convexity
                * _inner(gram, point_difference, point_difference)
                - 2.0
                * strong_convexity
                / smoothness
                * _inner(gram, gradient_difference, point_difference)
            ) / denominator
            constraints.append(left >= right)

    threshold_squared = tolerance**2
    strict_gradients = (
        baseline_gradients[:baseline_calls]
        + hybrid_gradients[:hybrid_calls]
    )
    constraints.extend(
        [
            _inner(
                gram,
                baseline_gradients[baseline_calls],
                baseline_gradients[baseline_calls],
            )
            <= threshold_squared,
            _inner(
                gram,
                hybrid_gradients[hybrid_calls],
                hybrid_gradients[hybrid_calls],
            )
            <= threshold_squared,
        ]
    )
    if strict_gradients:
        margin = cp.Variable()
        constraints.append(
            margin
            <= smoothness**2
            * (initial_distance_upper + proposal_norm) ** 2
        )
        for gradient in strict_gradients:
            constraints.append(
                _inner(gram, gradient, gradient)
                >= threshold_squared + margin
            )
        objective = cp.Maximize(margin)
    else:
        margin = None
        objective = cp.Maximize(0.0)

    problem = cp.Problem(objective, constraints)
    try:
        value = problem.solve(
            solver="CLARABEL",
            tol_gap_abs=1.0e-8,
            tol_feas=1.0e-8,
            tol_gap_rel=1.0e-8,
            max_iter=500,
            verbose=False,
        )
    except cp.error.SolverError:
        value = problem.solve(
            solver="SCS",
            eps=1.0e-7,
            max_iters=100_000,
            verbose=False,
        )
    if problem.status in {cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE}:
        return problem.status, None
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
        return problem.status, None
    return problem.status, float(value if margin is not None else 1.0)


def _run_pep_audit() -> dict[str, Any]:
    strong_convexity = 0.5
    smoothness = 1.0
    step_size = 1.0
    proposal_step = step_size
    proposal_norm = 1.0
    contract_radius = 0.0
    initial_distance_upper = 2.0
    tolerance = 0.15
    contraction = max(
        abs(1.0 - step_size * strong_convexity),
        abs(1.0 - step_size * smoothness),
    )
    initial_gradient_upper = smoothness * initial_distance_upper
    candidate_gradient_upper = smoothness * (
        initial_distance_upper + proposal_norm
    )
    horizon = max(
        ceil(log(tolerance / initial_gradient_upper) / log(contraction)),
        ceil(log(tolerance / candidate_gradient_upper) / log(contraction)),
    )
    cells: list[dict[str, Any]] = []
    attainable: list[StoppingPair] = []
    numerical_ambiguous = 0
    for baseline_calls in range(horizon + 1):
        for hybrid_calls in range(horizon + 1):
            status, margin = _cell_margin(
                baseline_calls,
                hybrid_calls,
                horizon=horizon,
                strong_convexity=strong_convexity,
                smoothness=smoothness,
                step_size=step_size,
                proposal_step=proposal_step,
                proposal_norm=proposal_norm,
                contract_radius=contract_radius,
                initial_distance_upper=initial_distance_upper,
                tolerance=tolerance,
            )
            feasible = bool(margin is not None and margin > 1.0e-5)
            if margin is not None and abs(margin) <= 1.0e-5:
                numerical_ambiguous += 1
            if feasible:
                attainable.append(StoppingPair(baseline_calls, hybrid_calls))
            cells.append(
                {
                    "baseline_calls": baseline_calls,
                    "hybrid_calls": hybrid_calls,
                    "status": status,
                    "strict_margin": margin,
                    "attainable": feasible,
                }
            )
    decision = transcript_optimal_gate(attainable, 0.4)
    return {
        "parameters": {
            "strong_convexity": strong_convexity,
            "smoothness": smoothness,
            "step_size": step_size,
            "proposal_step": proposal_step,
            "proposal_norm": proposal_norm,
            "contract_radius": contract_radius,
            "initial_distance_upper": initial_distance_upper,
            "tolerance": tolerance,
            "horizon": horizon,
        },
        "cell_count": len(cells),
        "attainable_pairs": [
            [pair.baseline_calls, pair.hybrid_calls] for pair in attainable
        ],
        "off_shift_attainable_count": sum(
            pair.hybrid_calls != pair.baseline_calls - 1 for pair in attainable
        ),
        "numerically_ambiguous_cell_count": numerical_ambiguous,
        "joint_accept": decision.accept_joint,
        "rectangle_accept": decision.accept_rectangle,
        "worst_joint_difference": decision.worst_joint_call_difference,
        "rectangle_difference": decision.rectangle_call_difference,
        "cells": cells,
    }


def _gradient_calls(
    matrix: np.ndarray,
    linear: np.ndarray,
    start: np.ndarray,
    step_size: float,
    tolerance: float,
) -> int:
    point = start.copy()
    calls = 0
    while np.linalg.norm(matrix @ point - linear) > tolerance:
        point -= step_size * (matrix @ point - linear)
        calls += 1
        if calls > 20_000:
            raise RuntimeError("quadratic trajectory did not terminate")
    return calls


def _run_ensemble_case(
    rng: np.random.Generator,
    case_id: int,
    dimension: int,
    family_size: int,
) -> dict[str, Any]:
    strong_convexity = float(rng.uniform(0.08, 0.35))
    smoothness = 1.0
    step_size = float(rng.uniform(0.65, 1.0))
    proposal_ratio = float(
        1.0 if rng.random() < 0.65 else rng.uniform(0.65, 1.25)
    )
    proposal_step = proposal_ratio * step_size
    tolerance = float(10.0 ** rng.uniform(-7.0, -3.5))
    nominal_gradient = rng.normal(size=dimension)
    nominal_gradient /= np.linalg.norm(nominal_gradient)
    scale = float(10.0 ** rng.uniform(-0.2, 0.8))
    nominal_gradient *= scale
    hybrid_start = -proposal_step * nominal_gradient
    contract_radius = float(
        rng.uniform(0.0, 0.08) * np.linalg.norm(nominal_gradient)
    )
    baseline_start = np.zeros(dimension)
    pairs: set[StoppingPair] = set()
    raw = rng.normal(size=(dimension, dimension))
    basis, _ = np.linalg.qr(raw)
    base_eigenvalues = rng.uniform(
        strong_convexity, smoothness, size=dimension
    )
    uncertainty_fraction = float(10.0 ** rng.uniform(-3.0, 0.0))
    maximum_initial_distance = 0.0
    maximum_contract_error = 0.0
    realized_index = case_id % family_size
    realized_pair: StoppingPair | None = None
    for family_index in range(family_size):
        eigenvalues = np.clip(
            base_eigenvalues
            + rng.normal(size=dimension)
            * 0.15
            * (smoothness - strong_convexity)
            * uncertainty_fraction,
            strong_convexity,
            smoothness,
        )
        matrix = basis @ np.diag(eigenvalues) @ basis.T
        error_direction = rng.normal(size=dimension)
        error_direction /= np.linalg.norm(error_direction)
        error_norm = float(
            rng.uniform(0.0, contract_radius / proposal_step)
        )
        true_gradient = nominal_gradient + error_norm * error_direction
        linear = -true_gradient
        maximum_contract_error = max(
            maximum_contract_error,
            float(np.linalg.norm(hybrid_start + proposal_step * true_gradient)),
        )
        maximum_initial_distance = max(
            maximum_initial_distance,
            float(np.linalg.norm(np.linalg.solve(matrix, linear))),
        )
        baseline_calls = _gradient_calls(
            matrix, linear, baseline_start, step_size, tolerance
        )
        hybrid_calls = _gradient_calls(
            matrix, linear, hybrid_start, step_size, tolerance
        )
        pair = StoppingPair(baseline_calls, hybrid_calls)
        pairs.add(pair)
        if family_index == realized_index:
            realized_pair = pair
    if realized_pair is None:
        raise RuntimeError("the realized family member was not recorded")
    cost = float(rng.uniform(0.05, 1.25))
    decision = transcript_optimal_gate(pairs, cost)
    baseline_cost = float(realized_pair.baseline_calls)
    if baseline_cost <= 0.0:
        raise RuntimeError("cost ratios require a positive realized baseline")
    joint_total_cost = (
        cost + realized_pair.hybrid_calls if decision.accept_joint else baseline_cost
    )
    rectangle_total_cost = (
        cost + realized_pair.hybrid_calls
        if decision.accept_rectangle
        else baseline_cost
    )
    always_total_cost = cost + realized_pair.hybrid_calls
    return {
        "case_id": case_id,
        "dimension": dimension,
        "family_size": family_size,
        "distinct_pair_count": len(pairs),
        "proposal_ratio": proposal_ratio,
        "uncertainty_fraction": uncertainty_fraction,
        "contract_radius": contract_radius,
        "maximum_realized_contract_error": maximum_contract_error,
        "initial_distance_upper": maximum_initial_distance,
        "cost_exact_units": cost,
        "joint_accept": decision.accept_joint,
        "rectangle_accept": decision.accept_rectangle,
        "worst_joint_difference": decision.worst_joint_call_difference,
        "rectangle_difference": decision.rectangle_call_difference,
        "baseline_lower_calls": decision.baseline_lower_calls,
        "hybrid_upper_calls": decision.hybrid_upper_calls,
        "joint_cost_slack": decision.guaranteed_joint_cost_slack,
        "realized_family_index": realized_index,
        "realized_baseline_calls": realized_pair.baseline_calls,
        "realized_hybrid_calls": realized_pair.hybrid_calls,
        "joint_total_cost": joint_total_cost,
        "joint_cost_ratio": joint_total_cost / baseline_cost,
        "rectangle_total_cost": rectangle_total_cost,
        "rectangle_cost_ratio": rectangle_total_cost / baseline_cost,
        "always_total_cost": always_total_cost,
        "always_cost_ratio": always_total_cost / baseline_cost,
        "rectangle_accept_without_joint": bool(
            decision.accept_rectangle and not decision.accept_joint
        ),
        "joint_only_accept": bool(
            decision.accept_joint and not decision.accept_rectangle
        ),
        "accepted_joint_violation": bool(
            decision.accept_joint
            and any(
                pair.hybrid_calls > pair.baseline_calls - 1
                or cost + pair.hybrid_calls > pair.baseline_calls + 1.0e-12
                for pair in pairs
            )
        ),
        "pairs": [
            [pair.baseline_calls, pair.hybrid_calls] for pair in sorted(pairs)
        ],
    }


def _quantiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "q05": float(np.quantile(array, 0.05)),
        "q95": float(np.quantile(array, 0.95)),
    }


def _summarize(records: list[dict[str, Any]], pep: dict[str, Any]) -> dict[str, Any]:
    joint = [row for row in records if row["joint_accept"]]
    rectangle = [row for row in records if row["rectangle_accept"]]
    joint_only = [row for row in records if row["joint_only_accept"]]
    shift = [row for row in records if row["proposal_ratio"] == 1.0]
    return {
        "case_count": len(records),
        "pep_cell_count": pep["cell_count"],
        "pep_attainable_pair_count": len(pep["attainable_pairs"]),
        "pep_off_shift_attainable_count": pep["off_shift_attainable_count"],
        "pep_numerically_ambiguous_cell_count": pep[
            "numerically_ambiguous_cell_count"
        ],
        "pep_joint_accept": pep["joint_accept"],
        "pep_rectangle_accept": pep["rectangle_accept"],
        "joint_accept_count": len(joint),
        "joint_accept_rate": len(joint) / len(records),
        "rectangle_accept_count": len(rectangle),
        "rectangle_accept_rate": len(rectangle) / len(records),
        "joint_only_accept_count": len(joint_only),
        "joint_only_accept_rate": len(joint_only) / len(records),
        "rectangle_accept_without_joint_count": sum(
            row["rectangle_accept_without_joint"] for row in records
        ),
        "accepted_joint_violation_count": sum(
            row["accepted_joint_violation"] for row in records
        ),
        "shift_case_count": len(shift),
        "shift_joint_accept_rate": sum(row["joint_accept"] for row in shift)
        / len(shift),
        "shift_rectangle_accept_rate": sum(
            row["rectangle_accept"] for row in shift
        )
        / len(shift),
        "rectangle_minus_joint_difference": _quantiles(
            [
                row["rectangle_difference"] - row["worst_joint_difference"]
                for row in records
            ]
        ),
        "joint_only_cost_slack": _quantiles(
            [row["joint_cost_slack"] for row in joint_only]
        )
        if joint_only
        else {},
        "joint_policy_cost_ratio": _quantiles(
            [row["joint_cost_ratio"] for row in records]
        ),
        "rectangle_policy_cost_ratio": _quantiles(
            [row["rectangle_cost_ratio"] for row in records]
        ),
        "always_policy_cost_ratio": _quantiles(
            [row["always_cost_ratio"] for row in records]
        ),
        "joint_policy_worse_fraction": float(
            np.mean([row["joint_cost_ratio"] > 1.0 + 1.0e-12 for row in records])
        ),
        "rectangle_policy_worse_fraction": float(
            np.mean(
                [row["rectangle_cost_ratio"] > 1.0 + 1.0e-12 for row in records]
            )
        ),
        "always_policy_worse_fraction": float(
            np.mean([row["always_cost_ratio"] > 1.0 + 1.0e-12 for row in records])
        ),
    }


def _plot(records: list[dict[str, Any]], pep: dict[str, Any], output: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.65))
    cells = pep["cells"]
    horizon = pep["parameters"]["horizon"]
    grid = np.zeros((horizon + 1, horizon + 1))
    for cell in cells:
        grid[cell["hybrid_calls"], cell["baseline_calls"]] = cell["attainable"]
    axes[0].imshow(grid, origin="lower", cmap="Blues", vmin=0.0, vmax=1.0)
    axes[0].set_xlabel("Baseline stopping time")
    axes[0].set_ylabel("Hybrid stopping time")
    axes[0].set_title("Joint PEP cells")
    axes[0].set_xticks(range(horizon + 1))
    axes[0].set_yticks(range(horizon + 1))

    labels = ["Rectangle", "Joint", "Joint only"]
    values = [
        sum(row["rectangle_accept"] for row in records),
        sum(row["joint_accept"] for row in records),
        sum(row["joint_only_accept"] for row in records),
    ]
    axes[1].bar(labels, values, color=["#F58518", "#4C78A8", "#72B7B2"])
    axes[1].set_ylabel("Accepted transcript families")
    axes[1].set_title("Acceptance coverage")
    for index, value in enumerate(values):
        axes[1].text(index, value + 8, str(value), ha="center")

    x_values = [row["worst_joint_difference"] for row in records]
    y_values = [row["rectangle_difference"] for row in records]
    colors = ["#4C78A8" if row["joint_accept"] else "#BAB0AC" for row in records]
    axes[2].scatter(x_values, y_values, c=colors, s=7, alpha=0.45, linewidths=0)
    limit_low = min(x_values + y_values)
    limit_high = max(x_values + y_values)
    axes[2].plot([limit_low, limit_high], [limit_low, limit_high], "k--", lw=1)
    axes[2].set_xlabel("Joint worst call difference")
    axes[2].set_ylabel("Rectangle difference")
    axes[2].set_title("Dependence retained")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("pdf", "png"):
        fig.savefig(output.with_suffix(f".{suffix}"), dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=2000)
    parser.add_argument("--dimension", type=int, default=24)
    parser.add_argument("--family-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260818)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--figure-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()
    if args.cases < 1 or args.dimension < 2 or args.family_size < 2:
        raise ValueError("invalid study dimensions")
    pep = _run_pep_audit()
    rng = np.random.default_rng(args.seed)
    records = [
        _run_ensemble_case(rng, case_id, args.dimension, args.family_size)
        for case_id in range(args.cases)
    ]
    summary = _summarize(records, pep)
    payload = {
        "schema": SCHEMA,
        "declaration": {
            "case_count": args.cases,
            "dimension": args.dimension,
            "family_size": args.family_size,
            "seed": args.seed,
            "pep_class": "L-smooth mu-strongly convex functions",
            "pep_solver": "CVXPY/Clarabel",
            "strict_cell_test": "optimal common margin tau > 1e-5",
            "ensemble_scope": (
                "finite transcript-consistent strongly convex quadratic families"
            ),
        },
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__).resolve()),
            "source_sha256": {
                str(path.relative_to(ROOT)): _file_hash(path)
                for path in sorted((ROOT / "src" / "c2ogate").glob("*.py"))
            },
        },
        "pep_audit": pep,
        "summary": summary,
        "records": records,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = args.output_dir / "transcript_pep_study.json"
    result.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8"
    )
    (args.output_dir / "transcript_pep_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _plot(records, pep, args.figure_dir / "transcript_pep_study")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
