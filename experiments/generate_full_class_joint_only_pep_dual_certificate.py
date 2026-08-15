#!/usr/bin/env python3
"""Recover exact duals for an infinite-class joint-only C2OGate instance."""

from __future__ import annotations

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

from generate_generic_pep_dual_certificate import (
    _build_problem,
    _canonical,
    _file_hash,
    _recover_rational_dual,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "full_class_joint_only_pep_dual.json"
VERIFIER = ROOT / "tools" / "verify_full_class_joint_only_pep_dual.py"
SCHEMA = "c2o-full-class-joint-only-pep-dual-v1"
HORIZON = 3
BAD_CELLS = [
    (baseline, candidate)
    for baseline in range(HORIZON + 1)
    for candidate in range(HORIZON + 1)
    if candidate >= baseline
]
PARAMETERS = {
    "strong_convexity": Fraction(1, 2),
    "smoothness": Fraction(1),
    "step_size": Fraction(1),
    "proposal_step": Fraction(11, 10),
    "proposal_norm_lower": Fraction(27, 50),
    "proposal_norm_upper": Fraction(14, 25),
    "contract_radius": Fraction(1, 100),
    "initial_distance_upper": Fraction(1),
    "tolerance": Fraction(1, 5),
    "derived_trace_bound": Fraction(16),
}


def _problem_kwargs() -> dict[str, Any]:
    return {
        "signed_terminal_margin": True,
        "horizon": HORIZON,
        "mu": PARAMETERS["strong_convexity"],
        "smoothness": PARAMETERS["smoothness"],
        "step_size": PARAMETERS["step_size"],
        "proposal_step": PARAMETERS["proposal_step"],
        "proposal_lower": PARAMETERS["proposal_norm_lower"],
        "proposal_upper": PARAMETERS["proposal_norm_upper"],
        "contract_radius": PARAMETERS["contract_radius"],
        "initial_distance_upper": PARAMETERS["initial_distance_upper"],
        "tolerance": PARAMETERS["tolerance"],
        "trace_bound": PARAMETERS["derived_trace_bound"],
    }


def _recover(inequalities, equalities, lambdas, nus):
    failures: list[str] = []
    for regularizer in (
        Fraction(1, 100_000),
        Fraction(1, 1_000_000),
        Fraction(1, 10_000_000),
    ):
        for threshold in (1.0e-6, 1.0e-8, 1.0e-10, 1.0e-12, 0.0):
            try:
                return _recover_rational_dual(
                    inequalities,
                    equalities,
                    lambdas,
                    nus,
                    active_threshold=threshold,
                    denominator_limit=10**6,
                    trace_regularizer=regularizer,
                )
            except RuntimeError as error:
                failures.append(
                    f"regularizer={regularizer}, threshold={threshold}: {error}"
                )
    raise RuntimeError("; ".join(failures))


def _solve_cell(cell: tuple[int, int]) -> dict[str, Any]:
    started = perf_counter()
    problem, inequalities, equalities, cvx_inequalities, cvx_equalities = (
        _build_problem(cell, **_problem_kwargs())
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
    exact_lambdas, exact_nus, exact_slack, exact_upper = _recover(
        inequalities, equalities, lambdas, nus
    )
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
    tolerance = PARAMETERS["tolerance"]
    while abs(gradient) > tolerance:
        gradient *= 1 - curvature
        calls += 1
    return calls


def _witnesses() -> list[dict[str, Any]]:
    gradient = Fraction(1, 2)
    proposal = -Fraction(11, 20)
    witnesses = []
    for curvature in (Fraction(1, 2), Fraction(1)):
        candidate_gradient = gradient + curvature * proposal
        witnesses.append(
            {
                "curvature": str(curvature),
                "function": f"f(t)=({curvature})*t^2/2+t/2",
                "current_gradient": str(gradient),
                "candidate": str(proposal),
                "candidate_gradient": str(candidate_gradient),
                "baseline_calls": _stopping_time(curvature, gradient),
                "candidate_calls": _stopping_time(
                    curvature, candidate_gradient
                ),
            }
        )
    return witnesses


def _contract_radius_sensitivity() -> list[dict[str, Any]]:
    """Return a floating diagnostic; exact acceptance uses only the dual suite."""

    records: list[dict[str, Any]] = []
    for radius in (
        Fraction(0),
        Fraction(1, 200),
        Fraction(1, 100),
        Fraction(3, 200),
        Fraction(1, 50),
        Fraction(3, 100),
        Fraction(1, 20),
    ):
        values: list[tuple[tuple[int, int], float]] = []
        for cell in BAD_CELLS:
            kwargs = _problem_kwargs()
            kwargs["contract_radius"] = radius
            problem, *_ = _build_problem(cell, **kwargs)
            value = problem.solve(
                solver="CLARABEL",
                tol_gap_abs=1.0e-9,
                tol_feas=1.0e-9,
                tol_gap_rel=1.0e-9,
                max_iter=1000,
                verbose=False,
            )
            values.append((cell, float(value)))
        worst_cell, maximum = max(values, key=lambda item: item[1])
        records.append(
            {
                "contract_radius": str(radius),
                "maximum_floating_signed_margin": maximum,
                "negative_bad_cell_count": sum(value < 0 for _, value in values),
                "worst_cell": list(worst_cell),
            }
        )
    return records


def main() -> None:
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
    witnesses = _witnesses()
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "cells": [list(cell) for cell in BAD_CELLS],
            "horizon": HORIZON,
            "function_class": "full infinite class F_{1/2,1} consistent with the transcript",
            "bad_cell_rule": "candidate_calls >= baseline_calls",
            "cost_exact_units": "2/5",
            "minimum_saved_calls": 1,
            "claim": (
                "the joint PEP accepts the complete transcript-conditioned "
                "class while exact independent marginal bounds reject"
            ),
        },
        "parameters": {key: str(value) for key, value in PARAMETERS.items()},
        "witnesses": witnesses,
        "marginal_certificate": {
            "current_gradient_lower": "53/110",
            "current_gradient_upper": "57/110",
            "proposal_step_contraction": "9/20",
            "candidate_gradient_upper": "107/440",
            "one_step_candidate_gradient_upper": "107/880",
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
        "diagnostic_contract_radius_sensitivity": (
            _contract_radius_sensitivity()
        ),
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
            "verifier_sha256": _file_hash(VERIFIER) if VERIFIER.exists() else None,
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "EXACT: full-class joint-only H=3 PEP suite, "
        f"{len(certificates)} cells, max upper={max(bounds)}, "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
