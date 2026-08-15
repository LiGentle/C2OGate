#!/usr/bin/env python3
"""Generate an exact marginal certificate for the flagship H=10 envelope."""

from __future__ import annotations

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
    LinearConstraint,
    _as_float_matrix,
    _as_float_vector,
    _basis,
    _canonical,
    _file_hash,
    _matrix_add,
    _positive_ldl_pivots,
    _recover_rational_dual,
    _scaled_sum,
    _symmetric_outer,
    _vector_subtract,
    _zero_matrix,
    _zero_vector,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "h10_marginal_pep_dual.json"
VERIFIER = ROOT / "tools" / "verify_h10_marginal_pep_dual.py"
SCHEMA = "c2o-h10-marginal-pep-dual-v1"
PARAMETERS = {
    "strong_convexity": Fraction(1, 10),
    "smoothness": Fraction(1),
    "proposal_norm_lower": Fraction(79, 100),
    "proposal_norm_upper": Fraction(81, 100),
    "contract_radius": Fraction(1, 10),
    "initial_distance_upper": Fraction(1),
    "tolerance": Fraction(2, 3),
    "derived_trace_bound": Fraction(6),
}


def _build_problem() -> tuple[
    cp.Problem,
    list[LinearConstraint],
    list[LinearConstraint],
    list[cp.Constraint],
    list[cp.Constraint],
]:
    atom_count = 4
    value_count = 3
    gram = cp.Variable((atom_count, atom_count), symmetric=True)
    values = cp.Variable(value_count)
    margin = cp.Variable()
    gradient_x = _basis(atom_count, 0)
    gradient_y = _basis(atom_count, 1)
    optimum = _basis(atom_count, 2)
    proposal = _basis(atom_count, 3)
    zero = _zero_vector(atom_count)
    points = [zero, proposal, optimum]
    gradients = [gradient_x, gradient_y, zero]
    inequalities: list[LinearConstraint] = []
    equalities: list[LinearConstraint] = []

    def add_inequality(
        name: str,
        matrix: list[list[Fraction]] | None = None,
        value_vector: list[Fraction] | None = None,
        margin_coefficient: Fraction = Fraction(0),
        rhs: Fraction = Fraction(0),
    ) -> None:
        inequalities.append(
            LinearConstraint(
                name,
                matrix if matrix is not None else _zero_matrix(atom_count),
                value_vector if value_vector is not None else _zero_vector(value_count),
                margin_coefficient,
                rhs,
            )
        )

    anchor = _zero_vector(value_count)
    anchor[0] = 1
    equalities.append(
        LinearConstraint(
            "value_anchor",
            _zero_matrix(atom_count),
            anchor,
            Fraction(0),
            Fraction(0),
        )
    )
    add_inequality(
        "proposal_norm_upper",
        _symmetric_outer(proposal, proposal),
        rhs=PARAMETERS["proposal_norm_upper"] ** 2,
    )
    add_inequality(
        "proposal_norm_lower",
        _matrix_add((-Fraction(1), _symmetric_outer(proposal, proposal))),
        rhs=-(PARAMETERS["proposal_norm_lower"] ** 2),
    )
    add_inequality(
        "initial_distance",
        _symmetric_outer(optimum, optimum),
        rhs=PARAMETERS["initial_distance_upper"] ** 2,
    )
    residual = _scaled_sum(proposal, [(Fraction(1), gradient_x)])
    add_inequality(
        "proposal_contract",
        _symmetric_outer(residual, residual),
        rhs=PARAMETERS["contract_radius"] ** 2,
    )
    add_inequality(
        "derived_trace_bound",
        [[Fraction(int(i == j)) for j in range(atom_count)] for i in range(atom_count)],
        rhs=PARAMETERS["derived_trace_bound"],
    )
    mu = PARAMETERS["strong_convexity"]
    smoothness = PARAMETERS["smoothness"]
    denominator = 2 * (1 - mu / smoothness)
    for i in range(len(points)):
        for j in range(len(points)):
            if i == j:
                continue
            point_difference = _vector_subtract(points[i], points[j])
            gradient_difference = _vector_subtract(gradients[i], gradients[j])
            matrix = _matrix_add(
                (
                    Fraction(1) / (smoothness * denominator),
                    _symmetric_outer(gradient_difference, gradient_difference),
                ),
                (
                    mu / denominator,
                    _symmetric_outer(point_difference, point_difference),
                ),
                (
                    -2 * mu / (smoothness * denominator),
                    _symmetric_outer(gradient_difference, point_difference),
                ),
                (Fraction(1), _symmetric_outer(gradients[j], point_difference)),
            )
            value_vector = _zero_vector(value_count)
            value_vector[i] -= 1
            value_vector[j] += 1
            add_inequality(f"interpolation_{i}_{j}", matrix, value_vector)
    add_inequality(
        "objective_link",
        _matrix_add((-Fraction(1), _symmetric_outer(gradient_y, gradient_y))),
        margin_coefficient=Fraction(1),
        rhs=-(PARAMETERS["tolerance"] ** 2),
    )

    cvx_inequalities: list[cp.Constraint] = []
    for item in inequalities:
        expression = (
            cp.sum(cp.multiply(_as_float_matrix(item.matrix), gram))
            + _as_float_vector(item.values) @ values
            + float(item.margin) * margin
        )
        cvx_inequalities.append(expression <= float(item.rhs))
    cvx_equalities: list[cp.Constraint] = []
    for item in equalities:
        expression = (
            cp.sum(cp.multiply(_as_float_matrix(item.matrix), gram))
            + _as_float_vector(item.values) @ values
            + float(item.margin) * margin
        )
        cvx_equalities.append(expression == float(item.rhs))
    problem = cp.Problem(
        cp.Maximize(margin),
        [gram >> 0, *cvx_inequalities, *cvx_equalities],
    )
    return problem, inequalities, equalities, cvx_inequalities, cvx_equalities


def main() -> None:
    started = perf_counter()
    problem, inequalities, equalities, cvx_inequalities, cvx_equalities = (
        _build_problem()
    )
    floating_value = problem.solve(
        solver="CLARABEL",
        tol_gap_abs=1.0e-11,
        tol_feas=1.0e-11,
        tol_gap_rel=1.0e-11,
        max_iter=1500,
        verbose=False,
    )
    numeric_lambdas = np.asarray(
        [constraint.dual_value for constraint in cvx_inequalities], dtype=float
    )
    numeric_nus = np.asarray(
        [constraint.dual_value for constraint in cvx_equalities], dtype=float
    )
    attempts: list[dict[str, Any]] = []
    recovered = None
    for regularizer in (Fraction(1, 100_000), Fraction(1, 1_000_000)):
        for threshold in (1.0e-6, 1.0e-8, 1.0e-10, 1.0e-12, 0.0):
            try:
                recovered = _recover_rational_dual(
                    inequalities,
                    equalities,
                    numeric_lambdas,
                    numeric_nus,
                    active_threshold=threshold,
                    denominator_limit=10**6,
                    trace_regularizer=regularizer,
                )
            except RuntimeError as error:
                attempts.append(
                    {
                        "regularizer": str(regularizer),
                        "active_threshold": f"{threshold:.0e}" if threshold else "0",
                        "outcome": "failure",
                        "diagnostic": str(error),
                    }
                )
                continue
            attempts.append(
                {
                    "regularizer": str(regularizer),
                    "active_threshold": f"{threshold:.0e}" if threshold else "0",
                    "outcome": "success",
                }
            )
            break
        if recovered is not None:
            break
    if recovered is None:
        diagnostics = "; ".join(
            str(attempt.get("diagnostic", "unknown failure"))
            for attempt in attempts
        )
        raise RuntimeError(f"marginal rational recovery failed: {diagnostics}")
    lambdas, nus, slack, exact_margin_upper = recovered
    exact_gradient_upper = exact_margin_upper + PARAMETERS["tolerance"] ** 2
    if exact_margin_upper >= 0:
        raise RuntimeError("marginal certificate does not prove immediate termination")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": "flagship natural-H=10 transcript envelope",
            "objective": "maximize ||grad f(y)||^2 over the full transcript class",
            "conclusion": (
                "U_y=0 and L_x=1 exactly; the marginal rectangle gate value is 0"
            ),
        },
        "parameters": {key: str(value) for key, value in PARAMETERS.items()},
        "certificate": {
            "primal": {
                "gram_order": len(slack),
                "function_value_count": len(inequalities[0].values),
                "inequality_count": len(inequalities),
                "equality_count": len(equalities),
                "floating_status": problem.status,
                "floating_objective": float(floating_value),
            },
            "dual": {
                "inequality_multipliers": {
                    item.name: str(multiplier)
                    for item, multiplier in zip(inequalities, lambdas, strict=True)
                    if multiplier
                },
                "equality_multipliers": {
                    item.name: str(multiplier)
                    for item, multiplier in zip(equalities, nus, strict=True)
                    if multiplier
                },
                "certified_margin_upper_bound": str(exact_margin_upper),
                "certified_gradient_squared_upper_bound": str(exact_gradient_upper),
                "positive_ldl_pivot_count": len(_positive_ldl_pivots(slack)),
            },
            "recovery": {
                "ordered_grid_attempts": attempts,
                "producer_guarantee": "heuristic success-or-fail",
            },
        },
        "exact_consequences": {
            "baseline_initial_gradient_lower_bound": str(
                PARAMETERS["proposal_norm_lower"] - PARAMETERS["contract_radius"]
            ),
            "baseline_marginal_lower": 1,
            "candidate_marginal_upper": 0,
            "rectangle_call_difference": -1,
            "rectangle_gate_value_with_max_cost_one": 0,
            "attaining_quadratic_witness": "f(t)=(t-4/5)^2/2, x=0, y=4/5",
        },
        "summary": {
            "generation_seconds": perf_counter() - started,
            "recovery_attempt_count": len(attempts),
            "recovery_failure_count": sum(
                attempt["outcome"] == "failure" for attempt in attempts
            ),
        },
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
        "EXACT: flagship marginal certificate, "
        f"||grad f(y)||^2 <= {exact_gradient_upper} < 4/9, "
        "rectangle gate value = 0"
    )


if __name__ == "__main__":
    main()
