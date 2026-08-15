#!/usr/bin/env python3
"""Generate an independently recovered H=10 envelope profile."""

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
)
from generate_h10_generic_pep_dual_certificate import (
    BAD_CELLS,
    HORIZON,
    _recover,
    _recovery_grid_summary,
)


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools" / "verify_h10_envelope_family.py"
SCHEMA = "c2o-h10-envelope-profile-v1"
PROFILE_PARAMETERS = {
    "candidate_heavy": {
        "strong_convexity": Fraction(1, 10),
        "smoothness": Fraction(1),
        "step_size": Fraction(1),
        "proposal_step": Fraction(1),
        "proposal_norm_lower": Fraction(89, 100),
        "proposal_norm_upper": Fraction(91, 100),
        "contract_radius": Fraction(1, 10),
        "initial_distance_upper": Fraction(9, 10),
        "tolerance": Fraction(2, 3),
        "derived_trace_bound": Fraction(47),
    },
    "tight_contract": {
        "strong_convexity": Fraction(1, 10),
        "smoothness": Fraction(1),
        "step_size": Fraction(1),
        "proposal_step": Fraction(1),
        "proposal_norm_lower": Fraction(79, 100),
        "proposal_norm_upper": Fraction(81, 100),
        "contract_radius": Fraction(2, 25),
        "initial_distance_upper": Fraction(1),
        "tolerance": Fraction(2, 3),
        "derived_trace_bound": Fraction(49),
    },
}


def _problem_kwargs(parameters: dict[str, Fraction]) -> dict[str, Any]:
    return {
        "signed_terminal_margin": True,
        "horizon": HORIZON,
        "mu": parameters["strong_convexity"],
        "smoothness": parameters["smoothness"],
        "step_size": parameters["step_size"],
        "proposal_step": parameters["proposal_step"],
        "proposal_lower": parameters["proposal_norm_lower"],
        "proposal_upper": parameters["proposal_norm_upper"],
        "contract_radius": parameters["contract_radius"],
        "initial_distance_upper": parameters["initial_distance_upper"],
        "tolerance": parameters["tolerance"],
        "trace_bound": parameters["derived_trace_bound"],
    }


def _solve_cell(
    profile: str,
    parameters: dict[str, Fraction],
    cell: tuple[int, int],
) -> dict[str, Any]:
    started = perf_counter()
    problem, inequalities, equalities, cvx_inequalities, cvx_equalities = (
        _build_problem(cell, **_problem_kwargs(parameters))
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
    exact_lambdas, exact_nus, exact_slack, exact_upper, attempts = _recover(
        inequalities, equalities, lambdas, nus
    )
    if exact_upper >= 0:
        raise RuntimeError(f"{profile} cell {cell} has nonnegative exact upper bound")
    elapsed = perf_counter() - started
    print(
        f"profile={profile} cell={cell} status={problem.status} "
        f"floating={floating_value:.8g} exact={float(exact_upper):.8g} "
        f"seconds={elapsed:.3f}",
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
            "ordered_grid_attempts": attempts,
            "selected_configuration": {
                key: attempts[-1][key]
                for key in ("regularizer", "active_threshold")
            },
            "producer_guarantee": "heuristic success-or-fail",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=sorted(PROFILE_PARAMETERS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    profile = args.profile
    parameters = PROFILE_PARAMETERS[profile]
    output = args.output or ROOT / "certificates" / f"h10_{profile}_pep_dual.json"
    started = perf_counter()
    certificates: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_solve_cell, profile, parameters, cell): cell
            for cell in BAD_CELLS
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            certificates.append(future.result())
            print(f"profile={profile} completed={completed}/{len(futures)}", flush=True)
    certificates.sort(key=lambda item: tuple(item["cell"]))
    bounds = [Fraction(item["dual"]["certified_upper_bound"]) for item in certificates]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "profile": profile,
            "cells": [list(cell) for cell in BAD_CELLS],
            "natural_horizon": HORIZON,
            "audit_padding": 0,
            "horizon": HORIZON,
            "function_class": "F_{1/10,1}",
            "bad_cell_rule": "hybrid_calls >= baseline_calls",
            "cost_exact_units": "2/5",
            "minimum_saved_calls": 1,
            "source_kind": "independent Clarabel recovery",
        },
        "parameters": {key: str(value) for key, value in parameters.items()},
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
                f"{len(certificates)}/{len(BAD_CELLS)} independently replayable "
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
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"EXACT: profile={profile}, H=10, 66 cells, max upper={max(bounds)}, "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
