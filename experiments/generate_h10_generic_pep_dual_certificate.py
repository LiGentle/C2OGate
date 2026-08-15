#!/usr/bin/env python3
"""Generate exact dual exclusions for a natural-H=10 joint PEP.

The numerical SDP solver is used only to locate candidate multipliers.  Every
reported certificate is rationalized and checked exactly before it is written.
The companion verifier reconstructs the SDP from scratch using only the Python
standard library.
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

from generate_generic_pep_dual_certificate import (
    _build_problem,
    _canonical,
    _file_hash,
    _recover_rational_dual,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "h10_generic_pep_dual.json"
VERIFIER = ROOT / "tools" / "verify_h10_generic_pep_dual.py"
SCHEMA = "c2o-h10-generic-pep-dual-v1"
HORIZON = 10
BAD_CELLS = [
    (baseline, hybrid)
    for baseline in range(HORIZON + 1)
    for hybrid in range(HORIZON + 1)
    if hybrid >= baseline
]
PARAMETERS = {
    "strong_convexity": Fraction(1, 10),
    "smoothness": Fraction(1),
    "step_size": Fraction(1),
    "proposal_step": Fraction(1),
    "proposal_norm_lower": Fraction(79, 100),
    "proposal_norm_upper": Fraction(81, 100),
    "contract_radius": Fraction(1, 10),
    "initial_distance_upper": Fraction(1),
    "tolerance": Fraction(2, 3),
    "derived_trace_bound": Fraction(49),
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
    attempts: list[dict[str, str]] = []
    for regularizer in (Fraction(1, 100_000), Fraction(1, 1_000_000)):
        for threshold in (1.0e-6, 1.0e-8, 1.0e-10, 1.0e-12, 0.0):
            configuration = {
                "regularizer": str(regularizer),
                "active_threshold": f"{threshold:.0e}" if threshold else "0",
            }
            try:
                recovered = _recover_rational_dual(
                    inequalities,
                    equalities,
                    lambdas,
                    nus,
                    active_threshold=threshold,
                    denominator_limit=10**6,
                    trace_regularizer=regularizer,
                )
            except RuntimeError as error:
                attempts.append(
                    {
                        **configuration,
                        "outcome": "failure",
                        "diagnostic": str(error),
                    }
                )
                continue
            attempts.append({**configuration, "outcome": "success"})
            return *recovered, attempts
    diagnostics = "; ".join(
        (
            f"regularizer={item['regularizer']}, "
            f"threshold={item['active_threshold']}: {item['diagnostic']}"
        )
        for item in attempts
    )
    raise RuntimeError(diagnostics)


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
    exact_lambdas, exact_nus, exact_slack, exact_upper, recovery_attempts = _recover(
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
            "positive_leading_principal_minor_count": len(exact_slack),
        },
        "recovery": {
            "ordered_grid_attempts": recovery_attempts,
            "selected_configuration": {
                key: recovery_attempts[-1][key]
                for key in ("regularizer", "active_threshold")
            },
            "producer_guarantee": "heuristic success-or-fail",
        },
    }


def _recovery_grid_summary(certificates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configurations = [
        (str(regularizer), f"{threshold:.0e}" if threshold else "0")
        for regularizer in (Fraction(1, 100_000), Fraction(1, 1_000_000))
        for threshold in (1.0e-6, 1.0e-8, 1.0e-10, 1.0e-12, 0.0)
    ]
    rows: list[dict[str, Any]] = []
    for regularizer, threshold in configurations:
        attempted = 0
        succeeded = 0
        failed = 0
        for certificate in certificates:
            for attempt in certificate["recovery"]["ordered_grid_attempts"]:
                if (
                    attempt["regularizer"] == regularizer
                    and attempt["active_threshold"] == threshold
                ):
                    attempted += 1
                    succeeded += attempt["outcome"] == "success"
                    failed += attempt["outcome"] == "failure"
                    break
        rows.append(
            {
                "regularizer": regularizer,
                "active_threshold": threshold,
                "attempted_cells": attempted,
                "successful_cells": succeeded,
                "failed_cells": failed,
                "not_reached_cells": len(certificates) - attempted,
            }
        )
    return rows


def _parse_cells(raw: list[str]) -> list[tuple[int, int]]:
    if not raw:
        return BAD_CELLS
    cells: list[tuple[int, int]] = []
    for entry in raw:
        baseline, hybrid = (int(value) for value in entry.split(",", maxsplit=1))
        cell = (baseline, hybrid)
        if cell not in BAD_CELLS:
            raise ValueError(f"not a cost-violating H=10 cell: {entry}")
        cells.append(cell)
    return cells


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cell", action="append", default=[])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    cells = _parse_cells(args.cell)
    started = perf_counter()
    certificates: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_solve_cell, cell): cell for cell in cells}
        for completed, future in enumerate(as_completed(futures), start=1):
            certificates.append(future.result())
            print(f"completed={completed}/{len(futures)}", flush=True)
    certificates.sort(key=lambda item: tuple(item["cell"]))
    bounds = [Fraction(item["dual"]["certified_upper_bound"]) for item in certificates]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "cells": [list(cell) for cell in cells],
            "natural_horizon": HORIZON,
            "audit_padding": 0,
            "horizon": HORIZON,
            "function_class": "F_{1/10,1}",
            "bad_cell_rule": "hybrid_calls >= baseline_calls",
            "cost_exact_units": "2/5",
            "minimum_saved_calls": 1,
            "proposal_contract": (
                "79/100 <= ||y-x|| <= 81/100 and "
                "||y-x+grad f(x)|| <= 1/10"
            ),
            "claim": (
                "all 66 cost-violating cells on the natural H=10 grid have "
                "a strictly negative exact rational dual upper bound"
            ),
        },
        "parameters": {key: str(value) for key, value in PARAMETERS.items()},
        "summary": {
            "certificate_count": len(certificates),
            "positive_leading_principal_minor_count": sum(
                item["dual"]["positive_leading_principal_minor_count"]
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
            "recovery_grid": _recovery_grid_summary(certificates),
            "certified_cell_progress": (
                f"{len(certificates)}/{len(cells)} independently replayable "
                "exclusions constructed"
            ),
            "incomplete_recovery_outcome": "uncertified",
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
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"EXACT: natural H=10, {len(certificates)} cells, "
        f"max upper={max(bounds)}, payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
