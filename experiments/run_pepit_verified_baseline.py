#!/usr/bin/env python3
"""PEPit-front-end baseline followed by exact rational verification.

PEPit constructs and solves every H=6 signed stopping-cell model.  This adapter
maps PEPit's high-level constraint duals to the named exact rows used by the
C2OGate certificate schema.  Rational recovery remains success-or-fail; the
ordinary stdlib H=6 consumer subsequently rebuilds all rows from parameters.
"""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import sys
from time import perf_counter
from typing import Any

import importlib.metadata
import numpy as np
from PEPit import PEP
from PEPit.functions import SmoothStronglyConvexFunction

import generate_full_class_joint_only_pep_dual_certificate as exact_model
import generate_h6_joint_only_pep_dual_certificate as h6


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "pepit_verified_baseline.json"
VERIFIER = ROOT / "tools" / "verify_pepit_h6_baseline.py"
POINT_PAIR = re.compile(r"Point_(\d+), Point_(\d+)")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _build_and_solve(cell: tuple[int, int]) -> tuple[PEP, float]:
    baseline_calls, candidate_calls = cell
    parameters = h6.PARAMETERS
    horizon = h6.HORIZON
    problem = PEP()
    function = problem.declare_function(
        SmoothStronglyConvexFunction,
        mu=float(parameters["strong_convexity"]),
        L=float(parameters["smoothness"]),
    )
    optimum = function.stationary_point()
    baseline_start = problem.set_initial_point()
    candidate_start = problem.set_initial_point()
    baseline_gradient, _ = function.oracle(baseline_start)
    displacement = candidate_start - baseline_start
    problem.set_initial_condition(
        (baseline_start - optimum) ** 2
        <= float(parameters["initial_distance_upper"]) ** 2
    )
    problem.set_initial_condition(
        displacement**2 >= float(parameters["proposal_norm_lower"]) ** 2
    )
    problem.set_initial_condition(
        displacement**2 <= float(parameters["proposal_norm_upper"]) ** 2
    )
    problem.set_initial_condition(
        (
            displacement
            + float(parameters["proposal_step"]) * baseline_gradient
        )
        ** 2
        <= float(parameters["contract_radius"]) ** 2
    )

    baseline_gradients = [baseline_gradient]
    point = baseline_start
    for _ in range(horizon):
        point = point - float(parameters["step_size"]) * baseline_gradients[-1]
        baseline_gradients.append(function.gradient(point))
    candidate_gradients = []
    point = candidate_start
    for index in range(horizon + 1):
        candidate_gradients.append(function.gradient(point))
        if index < horizon:
            point = point - float(parameters["step_size"]) * candidate_gradients[-1]

    trace = sum(
        gradient**2
        for gradient in baseline_gradients + candidate_gradients
    ) + (baseline_start - optimum) ** 2 + displacement**2
    problem.set_initial_condition(trace <= float(parameters["derived_trace_bound"]))
    tolerance_squared = float(parameters["tolerance"]) ** 2
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
    margin_upper = float(parameters["smoothness"]) ** 2 * (
        float(parameters["initial_distance_upper"])
        + float(parameters["proposal_norm_upper"])
    ) ** 2
    problem.set_performance_metric(margin_upper + 0 * baseline_gradients[0] ** 2)
    value = problem.solve(
        wrapper="cvxpy",
        solver="CLARABEL",
        verbose=0,
        safe_mode=False,
        tol_gap_abs=1.0e-10,
        tol_feas=1.0e-10,
        tol_gap_rel=1.0e-10,
        max_iter=1500,
    )
    return problem, float(value)


def _dual_seed(
    problem: PEP,
    cell: tuple[int, int],
    inequalities: list[Any],
) -> np.ndarray:
    """Map PEPit's semantic constraint order to C2OGate's named rows."""

    baseline_calls, candidate_calls = cell
    prepared = problem._list_of_prepared_constraints
    performance_count = baseline_calls + candidate_calls + 3
    performance = prepared[:performance_count]
    initial = prepared[performance_count : performance_count + 5]
    interpolation = prepared[performance_count + 5 :]
    if len(interpolation) != (2 * h6.HORIZON + 3) * (2 * h6.HORIZON + 2):
        raise RuntimeError("unexpected PEPit interpolation-row count")

    named: dict[str, float] = {}
    cursor = 0
    for index in range(baseline_calls):
        named[f"baseline_strict_{index}"] = float(performance[cursor].eval_dual())
        cursor += 1
    for index in range(candidate_calls):
        named[f"hybrid_strict_{index}"] = float(performance[cursor].eval_dual())
        cursor += 1
    for name in ("baseline_terminal", "hybrid_terminal", "margin_upper"):
        named[name] = float(performance[cursor].eval_dual())
        cursor += 1

    # PEPit receives these conditions as distance, lower, upper, residual, trace.
    for name, constraint in zip(
        (
            "initial_distance",
            "proposal_norm_lower",
            "proposal_norm_upper",
            "proposal_contract",
            "derived_trace_bound",
        ),
        initial,
        strict=True,
    ):
        named[name] = float(constraint.eval_dual())
    for constraint in interpolation:
        match = POINT_PAIR.search(constraint.get_name())
        if match is None:
            raise RuntimeError(f"unrecognized PEPit row {constraint.get_name()!r}")
        named[f"interpolation_{match.group(1)}_{match.group(2)}"] = float(
            constraint.eval_dual()
        )

    missing = {item.name for item in inequalities} - set(named)
    extra = set(named) - {item.name for item in inequalities}
    if missing or extra:
        raise RuntimeError(f"PEPit/native row mismatch: missing={missing}, extra={extra}")
    return np.asarray([named[item.name] for item in inequalities], dtype=float)


def _solve_cell(cell: tuple[int, int]) -> dict[str, Any]:
    started = perf_counter()
    h6._configure_base()
    problem, inequalities, equalities, *_ = exact_model._build_problem(
        cell, **exact_model._problem_kwargs()
    )
    pepit_problem, floating_value = _build_and_solve(cell)
    lambdas = _dual_seed(pepit_problem, cell, inequalities)
    # PEPit leaves the additive function-value origin free, whereas the exact
    # schema anchors f(x_0)=0.  Recover the corresponding equality multiplier
    # from value stationarity; this is a coordinate choice, not a fitted row.
    value_residual = sum(
        multiplier * np.asarray([float(value) for value in item.values])
        for multiplier, item in zip(lambdas, inequalities, strict=True)
    )
    nus = np.asarray([-value_residual[0]], dtype=float)
    recovered = exact_model._recover_rational_dual(
        inequalities,
        equalities,
        lambdas,
        nus,
        active_threshold=1.0e-10,
        denominator_limit=10**6,
        trace_regularizer=Fraction(1, 100_000),
    )
    recovery = {
        "active_threshold": 1.0e-10,
        "denominator_limit": 10**6,
        "trace_regularizer": "1/100000",
    }
    exact_lambdas, exact_nus, exact_slack, exact_upper = recovered
    if exact_upper >= 0:
        raise RuntimeError(f"PEPit baseline failed to exclude {cell}")
    return {
        "cell": list(cell),
        "primal": {
            "gram_order": len(exact_slack),
            "function_value_count": len(inequalities[0].values),
            "inequality_count": len(inequalities),
            "equality_count": len(equalities),
            "objective": "maximize signed cell-feasibility margin tau",
            "floating_status": "PEPit/Clarabel solved",
            "floating_objective": floating_value,
            "generation_seconds": perf_counter() - started,
        },
        "recovery": recovery,
        "dual": {
            "inequality_multipliers": {
                item.name: str(multiplier)
                for item, multiplier in zip(inequalities, exact_lambdas, strict=True)
                if multiplier
            },
            "equality_multipliers": {
                item.name: str(multiplier)
                for item, multiplier in zip(equalities, exact_nus, strict=True)
                if multiplier
            },
            "certified_upper_bound": str(exact_upper),
            "positive_ldl_pivot_count": len(exact_slack),
        },
    }


def main() -> None:
    started = perf_counter()
    certificates: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    # PEPit stores leaf counters globally.  The baseline is deliberately serial
    # so that it uses PEPit's public reset semantics rather than private locks.
    for cell in h6.BAD_CELLS:
        cell_started = perf_counter()
        try:
            certificate = _solve_cell(cell)
            certificates.append(certificate)
            rows.append(
                {
                    "cell": list(cell),
                    "outcome": "verified",
                    "floating_objective": certificate["primal"]["floating_objective"],
                    "wall_seconds": perf_counter() - cell_started,
                }
            )
        except RuntimeError as error:
            rows.append(
                {
                    "cell": list(cell),
                    "outcome": "uncertified",
                    "failure_stage": "rational recovery",
                    "failure_category": str(error).split(":", maxsplit=1)[0],
                    "wall_seconds": perf_counter() - cell_started,
                }
            )
    certificates.sort(key=lambda item: tuple(item["cell"]))
    exact_bounds = [
        Fraction(item["dual"]["certified_upper_bound"])
        for item in certificates
    ]
    native = json.loads(
        (ROOT / "certificates" / "h6_joint_only_pep_dual.json").read_text(
            encoding="utf-8"
        )
    )
    payload: dict[str, Any] = {
        "schema": "c2o-pepit-verified-baseline-v1",
        "declaration": {
            **native["declaration"],
            "producer": (
                "PEPit 0.5.1 semantic front end and Clarabel duals, followed by "
                "the frozen success-or-fail rational recovery grid"
            ),
            "baseline_role": (
                "generic verified-pipeline comparator; acceptance is still decided "
                "only by the parameter-level stdlib consumer"
            ),
        },
        "parameters": native["parameters"],
        "witnesses": native["witnesses"],
        "marginal_certificate": native["marginal_certificate"],
        "joint_certificate": native["joint_certificate"],
        "summary": {
            "certificate_count": len(certificates),
            "uncertified_cell_count": len(h6.BAD_CELLS) - len(certificates),
            "attempted_cell_count": len(h6.BAD_CELLS),
            "generation_wall_seconds": perf_counter() - started,
            "maximum_certified_upper_bound": (
                str(max(exact_bounds)) if exact_bounds else None
            ),
            "maximum_gram_order": 16,
            "maximum_inequality_count": 230,
            "positive_ldl_pivot_count": sum(item["dual"]["positive_ldl_pivot_count"] for item in certificates),
        },
        "rows": rows,
        "certificates": certificates,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "pepit": importlib.metadata.version("PEPit"),
            "generator_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(VERIFIER),
            "native_comparator_payload_sha256": native["payload_sha256"],
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "EXACT: PEPit-front-end baseline, "
        f"{len(certificates)}/{len(h6.BAD_CELLS)} H=6 cells recovered, "
        f"wall={payload['summary']['generation_wall_seconds']:.2f}s"
    )


if __name__ == "__main__":
    main()
