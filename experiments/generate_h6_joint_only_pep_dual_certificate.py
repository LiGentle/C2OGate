#!/usr/bin/env python3
"""Recover exact duals for a natural-H=6 nonzero-radius joint-only gate.

The floating producer reuses the generic signed-cell builder.  The companion
stdlib verifier reconstructs the coefficient rows independently from the
declared rational parameters.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import cvxpy as cp
import numpy as np

import generate_full_class_joint_only_pep_dual_certificate as base
from generate_generic_pep_dual_certificate import _canonical, _file_hash


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "h6_joint_only_pep_dual.json"
VERIFIER = ROOT / "tools" / "verify_h6_joint_only_pep_dual.py"
SCHEMA = "c2o-h6-joint-only-pep-dual-v1"
HORIZON = 6
BAD_CELLS = [
    (baseline, candidate)
    for baseline in range(HORIZON + 1)
    for candidate in range(HORIZON + 1)
    if candidate >= baseline
]
PARAMETERS = {
    "strong_convexity": Fraction(3, 10),
    "smoothness": Fraction(1),
    "step_size": Fraction(1),
    "proposal_step": Fraction(11, 10),
    "proposal_norm_lower": Fraction(27, 50),
    "proposal_norm_upper": Fraction(14, 25),
    "contract_radius": Fraction(1, 100),
    "initial_distance_upper": Fraction(9, 5),
    "tolerance": Fraction(7, 25),
    "derived_trace_bound": Fraction(66),
}


def _configure_base() -> None:
    base.HORIZON = HORIZON
    base.BAD_CELLS = BAD_CELLS
    base.PARAMETERS = PARAMETERS


def _recover_h6(inequalities, equalities, lambdas, nus):
    """Try a frozen recovery grid; every returned object is verified exactly."""

    failures: list[str] = []
    named_index = {item.name: index for index, item in enumerate(inequalities)}
    for regularizer in (
        Fraction(1, 100_000),
        Fraction(1, 1_000_000),
        Fraction(1, 10_000_000),
    ):
        for threshold in (1.0e-6, 1.0e-8, 1.0e-10, 1.0e-12, 0.0):
            try:
                recovered = base._recover_rational_dual(
                    inequalities,
                    equalities,
                    lambdas,
                    nus,
                    active_threshold=threshold,
                    denominator_limit=10**6,
                    trace_regularizer=regularizer,
                )
                return recovered, {
                    "pivot_repair": "none",
                    "trace_regularizer": str(regularizer),
                    "active_threshold": threshold,
                }
            except RuntimeError as error:
                failures.append(
                    f"regularizer={regularizer}, threshold={threshold}: {error}"
                )

    # Thin but strictly negative cells at larger contract radii need a smaller
    # artificial trace multiplier and a finer rational grid.  This remains a
    # discovery heuristic: the consumer checks the resulting object exactly.
    for regularizer in (
        Fraction(1, 100_000_000),
        Fraction(1, 1_000_000_000),
        Fraction(1, 10_000_000_000),
    ):
        for threshold in (1.0e-8, 1.0e-10, 1.0e-12, 1.0e-14, 0.0):
            try:
                recovered = base._recover_rational_dual(
                    inequalities,
                    equalities,
                    lambdas,
                    nus,
                    active_threshold=threshold,
                    denominator_limit=10**8,
                    trace_regularizer=regularizer,
                )
                return recovered, {
                    "pivot_repair": "none",
                    "trace_regularizer": str(regularizer),
                    "active_threshold": threshold,
                    "denominator_limit": 10**8,
                }
            except RuntimeError as error:
                failures.append(
                    "fine recovery, "
                    f"regularizer={regularizer}, threshold={threshold}: {error}"
                )

    # On two late cells the numerical correction basis makes one multiplier
    # slightly negative.  The following frozen pivot replacement supplies a
    # different full-rank basis; it is a producer heuristic only, and the
    # resulting multipliers, stationarity, objective, and slack are all checked
    # independently by the consumer.
    adjusted = lambdas.copy()
    adjusted[named_index["interpolation_12_13"]] = 5.0e-7
    adjusted[named_index["interpolation_13_12"]] = 1.1e-6
    for regularizer in (
        Fraction(1, 100_000),
        Fraction(1, 1_000_000),
        Fraction(1, 10_000_000),
    ):
        try:
            recovered = base._recover_rational_dual(
                inequalities,
                equalities,
                adjusted,
                nus,
                active_threshold=1.0e-6,
                denominator_limit=10**6,
                trace_regularizer=regularizer,
            )
            return recovered, {
                "pivot_repair": "replace interpolation_12_13 by interpolation_13_12",
                "trace_regularizer": str(regularizer),
                "active_threshold": 1.0e-6,
            }
        except RuntimeError as error:
            failures.append(f"pivot repair, regularizer={regularizer}: {error}")
    raise RuntimeError("; ".join(failures))


def _solve_cell(cell: tuple[int, int]) -> dict[str, Any]:
    _configure_base()
    started = perf_counter()
    problem, inequalities, equalities, cvx_inequalities, cvx_equalities = (
        base._build_problem(cell, **base._problem_kwargs())
    )
    floating_value = problem.solve(
        solver="CLARABEL",
        tol_gap_abs=1.0e-10,
        tol_feas=1.0e-10,
        tol_gap_rel=1.0e-10,
        max_iter=1500,
        verbose=False,
    )
    lambdas = np.asarray(
        [constraint.dual_value for constraint in cvx_inequalities], dtype=float
    )
    nus = np.asarray(
        [constraint.dual_value for constraint in cvx_equalities], dtype=float
    )
    recovered, recovery = _recover_h6(
        inequalities, equalities, lambdas, nus
    )
    exact_lambdas, exact_nus, exact_slack, exact_upper = recovered
    if exact_upper >= 0:
        raise RuntimeError(f"cell {cell} has nonnegative exact upper bound")
    elapsed = perf_counter() - started
    print(
        f"cell={cell} status={problem.status} floating={floating_value:.8g} "
        f"exact={float(exact_upper):.8g} seconds={elapsed:.3f}",
        flush=True,
    )
    return {
        "cell": list(cell),
        "primal": {
            "gram_order": len(exact_slack),
            "function_value_count": len(inequalities[0].values),
            "inequality_count": len(inequalities),
            "equality_count": len(equalities),
            "objective": "maximize signed cell-feasibility margin tau",
            "floating_status": problem.status,
            "floating_objective": float(floating_value),
            "generation_seconds": elapsed,
        },
        "recovery": recovery,
        "dual": {
            "inequality_multipliers": {
                item.name: str(multiplier)
                for item, multiplier in zip(
                    inequalities, exact_lambdas, strict=True
                )
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


def _stopping_time(curvature: Fraction, gradient: Fraction) -> int:
    calls = 0
    while abs(gradient) > PARAMETERS["tolerance"]:
        gradient *= 1 - curvature
        calls += 1
    return calls


def _witnesses() -> list[dict[str, Any]]:
    declarations = (
        (Fraction(1), Fraction(1, 2), -Fraction(11, 20)),
        (Fraction(3, 10), Fraction(1, 2), -Fraction(27, 50)),
    )
    witnesses: list[dict[str, Any]] = []
    for curvature, gradient, candidate in declarations:
        candidate_gradient = gradient + curvature * candidate
        witnesses.append(
            {
                "curvature": str(curvature),
                "current_gradient": str(gradient),
                "candidate": str(candidate),
                "proposal_residual": str(
                    candidate + PARAMETERS["proposal_step"] * gradient
                ),
                "candidate_gradient": str(candidate_gradient),
                "baseline_calls": _stopping_time(curvature, gradient),
                "candidate_calls": _stopping_time(curvature, candidate_gradient),
            }
        )
    return witnesses


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract-radius", type=Fraction, default=Fraction(1, 100)
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--schema", default=SCHEMA)
    parser.add_argument("--verifier", type=Path, default=VERIFIER)
    args = parser.parse_args()
    PARAMETERS["contract_radius"] = args.contract_radius
    _configure_base()
    started = perf_counter()
    certificates: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_solve_cell, cell): cell for cell in BAD_CELLS}
        for completed, future in enumerate(as_completed(futures), start=1):
            certificates.append(future.result())
            print(f"completed={completed}/{len(futures)}", flush=True)
    certificates.sort(key=lambda item: tuple(item["cell"]))
    bounds = [
        Fraction(item["dual"]["certified_upper_bound"])
        for item in certificates
    ]
    payload: dict[str, Any] = {
        "schema": args.schema,
        "declaration": {
            "cells": [list(cell) for cell in BAD_CELLS],
            "horizon": HORIZON,
            "function_class": (
                "full infinite class F_{3/10,1} consistent with the transcript"
            ),
            "bad_cell_rule": "candidate_calls >= baseline_calls",
            "cost_exact_units": "2/5",
            "minimum_saved_calls": 1,
            "claim": (
                "at natural H=6 and a declared nonzero proposal radius, the joint PEP "
                "accepts while exact independent marginals reject"
            ),
        },
        "parameters": {key: str(value) for key, value in PARAMETERS.items()},
        "witnesses": _witnesses(),
        "marginal_certificate": {
            "current_gradient_lower": str(
                (PARAMETERS["proposal_norm_lower"] - PARAMETERS["contract_radius"])
                / PARAMETERS["proposal_step"]
            ),
            "current_gradient_upper": str(
                (PARAMETERS["proposal_norm_upper"] + PARAMETERS["contract_radius"])
                / PARAMETERS["proposal_step"]
            ),
            "proposal_step_contraction": str(
                max(
                    abs(
                        1
                        - PARAMETERS["proposal_step"]
                        * PARAMETERS["strong_convexity"]
                    ),
                    abs(
                        1
                        - PARAMETERS["proposal_step"]
                        * PARAMETERS["smoothness"]
                    ),
                )
            ),
            "candidate_gradient_upper": str(
                max(
                    abs(
                        1
                        - PARAMETERS["proposal_step"]
                        * PARAMETERS["strong_convexity"]
                    ),
                    abs(
                        1
                        - PARAMETERS["proposal_step"]
                        * PARAMETERS["smoothness"]
                    ),
                )
                * (
                    PARAMETERS["proposal_norm_upper"]
                    + PARAMETERS["contract_radius"]
                )
                / PARAMETERS["proposal_step"]
                + PARAMETERS["smoothness"] * PARAMETERS["contract_radius"]
            ),
            "one_step_candidate_gradient_upper": str(
                (1 - PARAMETERS["strong_convexity"])
                * (
                    max(
                        abs(
                            1
                            - PARAMETERS["proposal_step"]
                            * PARAMETERS["strong_convexity"]
                        ),
                        abs(
                            1
                            - PARAMETERS["proposal_step"]
                            * PARAMETERS["smoothness"]
                        ),
                    )
                    * (
                        PARAMETERS["proposal_norm_upper"]
                        + PARAMETERS["contract_radius"]
                    )
                    / PARAMETERS["proposal_step"]
                    + PARAMETERS["smoothness"]
                    * PARAMETERS["contract_radius"]
                )
            ),
            "baseline_lower_calls": 1,
            "candidate_upper_calls": 1,
            "rectangle_call_difference": 0,
            "rectangle_certificate_value": "1",
        },
        "joint_certificate": {
            "worst_call_difference": -1,
            "certificate_value": "0",
            "joint_accept": True,
            "rectangle_accept": False,
        },
        "summary": {
            "certificate_count": len(certificates),
            "positive_ldl_pivot_count": sum(
                item["dual"]["positive_ldl_pivot_count"]
                for item in certificates
            ),
            "maximum_certified_upper_bound": str(max(bounds)),
            "maximum_gram_order": max(
                item["primal"]["gram_order"] for item in certificates
            ),
            "maximum_inequality_count": max(
                item["primal"]["inequality_count"] for item in certificates
            ),
            "generation_wall_seconds": perf_counter() - started,
        },
        "certificates": certificates,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "clarabel": __import__("clarabel").__version__,
            "generator_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": (
                _file_hash(args.verifier) if args.verifier.exists() else None
            ),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "EXACT: natural-H=6 nonzero-radius joint-only PEP suite, "
        f"{len(certificates)} cells, max upper={max(bounds)}, "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
