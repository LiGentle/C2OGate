#!/usr/bin/env python3
"""Test rational dual recovery from SCS on stratified H=10 cells."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import cvxpy as cp
import numpy as np

from generate_generic_pep_dual_certificate import _build_problem, _canonical, _file_hash
from generate_h10_generic_pep_dual_certificate import (
    PARAMETERS,
    _problem_kwargs,
    _recover,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "scs_recovery_diagnostic.json"
VERIFIER = ROOT / "tools" / "verify_scs_recovery_diagnostic.py"
SCHEMA = "c2o-scs-recovery-diagnostic-v1"
CELLS = [(0, 0), (0, 5), (0, 10), (3, 3), (3, 7), (5, 5), (5, 10), (8, 8), (10, 10)]


def _run_cell(cell: tuple[int, int]) -> dict[str, Any]:
    started = perf_counter()
    problem, inequalities, equalities, cvx_inequalities, cvx_equalities = (
        _build_problem(cell, **_problem_kwargs())
    )
    floating_value = problem.solve(
        solver="SCS",
        eps=1.0e-7,
        max_iters=200_000,
        verbose=False,
    )
    row: dict[str, Any] = {
        "cell": list(cell),
        "floating_status": problem.status,
        "floating_objective": (
            None if floating_value is None else float(floating_value)
        ),
    }
    try:
        lambdas = np.asarray(
            [constraint.dual_value for constraint in cvx_inequalities], dtype=float
        )
        nus = np.asarray(
            [constraint.dual_value for constraint in cvx_equalities], dtype=float
        )
        exact_lambdas, exact_nus, exact_slack, exact_upper, attempts = _recover(
            inequalities, equalities, lambdas, nus
        )
    except (RuntimeError, TypeError, ValueError) as error:
        row.update(
            {
                "recovery_outcome": "failure",
                "diagnostic": f"{type(error).__name__}: {error}",
                "seconds": perf_counter() - started,
            }
        )
        return row
    row.update(
        {
            "recovery_outcome": "success",
            "seconds": perf_counter() - started,
            "certificate": {
                "cell": list(cell),
                "primal": {
                    "gram_order": len(exact_slack),
                    "function_value_count": len(inequalities[0].values),
                    "inequality_count": len(inequalities),
                    "equality_count": len(equalities),
                    "objective": "maximize signed cell-feasibility margin tau",
                    "floating_status": problem.status,
                    "floating_objective": float(floating_value),
                    "generation_seconds": perf_counter() - started,
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
                        for item, multiplier in zip(
                            equalities, exact_nus, strict=True
                        )
                        if multiplier
                    },
                    "certified_upper_bound": str(exact_upper),
                    "positive_leading_principal_minor_count": len(exact_slack),
                },
                "recovery": {
                    "ordered_grid_attempts": attempts,
                    "selected_configuration": {
                        key: attempts[-1][key]
                        for key in ("regularizer", "active_threshold")
                    },
                    "producer_guarantee": "heuristic success-or-fail",
                },
            },
        }
    )
    return row


def main() -> None:
    rows = []
    started = perf_counter()
    for cell in CELLS:
        row = _run_cell(cell)
        rows.append(row)
        print(
            f"cell={cell} status={row['floating_status']} "
            f"recovery={row['recovery_outcome']}",
            flush=True,
        )
    successes = [row for row in rows if row["recovery_outcome"] == "success"]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": "nine stratified cells from the flagship natural-H=10 suite",
            "solver": "SCS",
            "solver_tolerance": "1e-7",
            "solver_iteration_limit": 200000,
            "role": (
                "producer portability diagnostic only; failed recovery is "
                "fail-closed and no SCS status is used as acceptance evidence"
            ),
            "cells": [list(cell) for cell in CELLS],
        },
        "parameters": {key: str(value) for key, value in PARAMETERS.items()},
        "summary": {
            "cell_count": len(rows),
            "recovery_success_count": len(successes),
            "recovery_failure_count": len(rows) - len(successes),
            "exact_positive_ldl_pivot_count": 24 * len(successes),
            "wall_seconds": perf_counter() - started,
        },
        "rows": rows,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "scs": __import__("scs").__version__,
            "runner_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(VERIFIER),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"FROZEN: SCS recovery {len(successes)}/{len(rows)} stratified cells; "
        "all failures remain uncertified"
    )


if __name__ == "__main__":
    main()
