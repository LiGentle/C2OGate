#!/usr/bin/env python3
"""Recover exact duals for ten generic nonquadratic joint-PEP cells."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import cvxpy as cp
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "generic_nonquadratic_pep_dual.json"
VERIFIER = ROOT / "tools" / "verify_generic_nonquadratic_pep_dual.py"
SCHEMA = "c2o-generic-nonquadratic-pep-dual-v2"
BAD_CELLS = [
    (0, 0),
    (0, 1),
    (0, 2),
    (0, 3),
    (1, 1),
    (1, 2),
    (1, 3),
    (2, 2),
    (2, 3),
    (3, 3),
]


Matrix = list[list[Fraction]]


@dataclass(frozen=True)
class LinearConstraint:
    name: str
    matrix: Matrix
    values: list[Fraction]
    margin: Fraction
    rhs: Fraction


def _zero_matrix(size: int) -> Matrix:
    return [[Fraction(0) for _ in range(size)] for _ in range(size)]


def _zero_vector(size: int) -> list[Fraction]:
    return [Fraction(0) for _ in range(size)]


def _symmetric_outer(
    left: list[Fraction], right: list[Fraction]
) -> Matrix:
    return [
        [
            (left[i] * right[j] + right[i] * left[j]) / 2
            for j in range(len(left))
        ]
        for i in range(len(left))
    ]


def _matrix_add(*terms: tuple[Fraction, Matrix]) -> Matrix:
    size = len(terms[0][1])
    return [
        [
            sum((scale * matrix[i][j] for scale, matrix in terms), Fraction(0))
            for j in range(size)
        ]
        for i in range(size)
    ]


def _vector_subtract(
    left: list[Fraction], right: list[Fraction]
) -> list[Fraction]:
    return [a - b for a, b in zip(left, right, strict=True)]


def _basis(size: int, index: int) -> list[Fraction]:
    result = _zero_vector(size)
    result[index] = Fraction(1)
    return result


def _scaled_sum(
    base: list[Fraction], terms: list[tuple[Fraction, list[Fraction]]]
) -> list[Fraction]:
    result = base.copy()
    for scale, vector in terms:
        result = [
            entry + scale * value
            for entry, value in zip(result, vector, strict=True)
        ]
    return result


def _as_float_matrix(matrix: Matrix) -> np.ndarray:
    return np.asarray([[float(value) for value in row] for row in matrix])


def _as_float_vector(vector: list[Fraction]) -> np.ndarray:
    return np.asarray([float(value) for value in vector])


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _determinant(matrix: Matrix) -> Fraction:
    work = [row.copy() for row in matrix]
    determinant = Fraction(1)
    for column in range(len(work)):
        pivot = next(
            (row for row in range(column, len(work)) if work[row][column]), None
        )
        if pivot is None:
            return Fraction(0)
        if pivot != column:
            work[column], work[pivot] = work[pivot], work[column]
            determinant *= -1
        pivot_value = work[column][column]
        determinant *= pivot_value
        for row in range(column + 1, len(work)):
            factor = work[row][column] / pivot_value
            for index in range(column + 1, len(work)):
                work[row][index] -= factor * work[column][index]
    return determinant


def _matrix_to_json(matrix: Matrix) -> list[list[str]]:
    return [[str(value) for value in row] for row in matrix]


def _build_problem(
    cell: tuple[int, int] = (3, 3),
    *,
    signed_terminal_margin: bool = False,
) -> tuple[
    cp.Problem,
    list[LinearConstraint],
    list[LinearConstraint],
    list[cp.Constraint],
    list[cp.Constraint],
]:
    horizon = 3
    baseline_calls, hybrid_calls = cell
    if not (0 <= baseline_calls <= horizon and 0 <= hybrid_calls <= horizon):
        raise ValueError(f"cell outside horizon: {cell}")
    mu = Fraction(9, 10)
    smoothness = Fraction(1)
    step_size = Fraction(1)
    proposal_step = Fraction(1)
    proposal_lower = Fraction(24, 25)
    proposal_upper = Fraction(97, 100)
    contract_radius = Fraction(1, 100)
    initial_distance_upper = Fraction(6, 5)
    tolerance = Fraction(7, 50)

    baseline_size = horizon + 1
    hybrid_size = horizon + 1
    atom_count = baseline_size + hybrid_size + 2
    value_count = baseline_size + hybrid_size + 1
    gram = cp.Variable((atom_count, atom_count), symmetric=True)
    values = cp.Variable(value_count)
    margin = cp.Variable()

    baseline_gradients = [_basis(atom_count, k) for k in range(baseline_size)]
    hybrid_gradients = [
        _basis(atom_count, baseline_size + k) for k in range(hybrid_size)
    ]
    optimum = _basis(atom_count, atom_count - 2)
    proposal = _basis(atom_count, atom_count - 1)
    zero = _zero_vector(atom_count)
    baseline_points = [zero]
    for k in range(1, baseline_size):
        baseline_points.append(
            _scaled_sum(
                zero,
                [(-step_size, gradient) for gradient in baseline_gradients[:k]],
            )
        )
    hybrid_points = [proposal]
    for k in range(1, hybrid_size):
        hybrid_points.append(
            _scaled_sum(
                proposal,
                [(-step_size, gradient) for gradient in hybrid_gradients[:k]],
            )
        )
    points = baseline_points + hybrid_points + [optimum]
    gradients = baseline_gradients + hybrid_gradients + [zero]

    inequalities: list[LinearConstraint] = []
    equalities: list[LinearConstraint] = []

    def add_inequality(
        name: str,
        matrix: Matrix | None = None,
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

    value_anchor = _zero_vector(value_count)
    value_anchor[0] = Fraction(1)
    equalities.append(
        LinearConstraint(
            "value_anchor",
            _zero_matrix(atom_count),
            value_anchor,
            Fraction(0),
            Fraction(0),
        )
    )
    add_inequality(
        "proposal_norm_upper",
        _symmetric_outer(proposal, proposal),
        rhs=proposal_upper**2,
    )
    add_inequality(
        "proposal_norm_lower",
        _matrix_add((-Fraction(1), _symmetric_outer(proposal, proposal))),
        rhs=-(proposal_lower**2),
    )
    add_inequality(
        "initial_distance",
        _symmetric_outer(optimum, optimum),
        rhs=initial_distance_upper**2,
    )
    proposal_residual = _scaled_sum(
        proposal, [(proposal_step, baseline_gradients[0])]
    )
    add_inequality(
        "proposal_contract",
        _symmetric_outer(proposal_residual, proposal_residual),
        rhs=contract_radius**2,
    )
    add_inequality(
        "derived_trace_bound",
        [
            [Fraction(int(i == j)) for j in range(atom_count)]
            for i in range(atom_count)
        ],
        rhs=Fraction(27),
    )

    denominator = 2 * (1 - mu / smoothness)
    for i in range(len(points)):
        for j in range(len(points)):
            if i == j:
                continue
            point_difference = _vector_subtract(points[i], points[j])
            gradient_difference = _vector_subtract(gradients[i], gradients[j])
            matrix = _matrix_add(
                (
                    Fraction(1, 1) / (smoothness * denominator),
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

    tolerance_squared = tolerance**2
    add_inequality(
        "baseline_terminal",
        _symmetric_outer(
            baseline_gradients[baseline_calls], baseline_gradients[baseline_calls]
        ),
        margin_coefficient=(
            Fraction(1) if signed_terminal_margin else Fraction(0)
        ),
        rhs=tolerance_squared,
    )
    add_inequality(
        "hybrid_terminal",
        _symmetric_outer(
            hybrid_gradients[hybrid_calls], hybrid_gradients[hybrid_calls]
        ),
        margin_coefficient=(
            Fraction(1) if signed_terminal_margin else Fraction(0)
        ),
        rhs=tolerance_squared,
    )
    margin_upper = smoothness**2 * (initial_distance_upper + proposal_upper) ** 2
    add_inequality(
        "margin_upper", margin_coefficient=Fraction(1), rhs=margin_upper
    )
    for label, branch in (
        ("baseline", baseline_gradients[:baseline_calls]),
        ("hybrid", hybrid_gradients[:hybrid_calls]),
    ):
        for index, gradient in enumerate(branch):
            add_inequality(
                f"{label}_strict_{index}",
                _matrix_add(
                    (-Fraction(1), _symmetric_outer(gradient, gradient))
                ),
                margin_coefficient=Fraction(1),
                rhs=-tolerance_squared,
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


def _recover_rational_dual(
    inequalities: list[LinearConstraint],
    equalities: list[LinearConstraint],
    numeric_lambdas: np.ndarray,
    numeric_nus: np.ndarray,
) -> tuple[list[Fraction], list[Fraction], Matrix, Fraction]:
    import sympy as sp

    value_count = len(inequalities[0].values)
    row_count = value_count + 1
    columns = [
        [*item.values, item.margin] for item in [*inequalities, *equalities]
    ]
    stationarity = sp.Matrix(
        [
            [sp.Rational(columns[column][row].numerator, columns[column][row].denominator)
             for column in range(len(columns))]
            for row in range(row_count)
        ]
    )
    target = sp.Matrix([*[sp.Rational(0) for _ in range(value_count)], sp.Rational(1)])
    numeric = [*numeric_lambdas.tolist(), *numeric_nus.tolist()]
    rational = [
        Fraction(str(float(value))).limit_denominator(10**6)
        if abs(float(value)) >= 1.0e-10
        else Fraction(0)
        for value in numeric
    ]
    trace_index = next(
        index
        for index, item in enumerate(inequalities)
        if item.name == "derived_trace_bound"
    )
    rational[trace_index] = Fraction(1, 100_000)

    equality_indices = list(range(len(inequalities), len(columns)))
    inequality_indices = sorted(
        (
            index
            for index, value in enumerate(numeric_lambdas)
            if value > 1.0e-6 and index != trace_index
        ),
        key=lambda index: numeric_lambdas[index],
        reverse=True,
    )
    pivots: list[int] = []
    current_rank = 0
    for index in [*equality_indices, *inequality_indices]:
        candidate = stationarity[:, [*pivots, index]]
        rank = candidate.rank()
        if rank > current_rank:
            pivots.append(index)
            current_rank = rank
        if current_rank == row_count:
            break
    if current_rank != row_count:
        raise RuntimeError("could not find a full-rank positive dual correction basis")
    rational_vector = sp.Matrix(
        [sp.Rational(value.numerator, value.denominator) for value in rational]
    )
    residual = stationarity * rational_vector - target
    correction = -stationarity[:, pivots].inv() * residual
    for index, value in zip(pivots, correction, strict=True):
        rational[index] += Fraction(int(value.p), int(value.q))
    lambdas = rational[: len(inequalities)]
    nus = rational[len(inequalities) :]
    if any(value < 0 for value in lambdas):
        negative = [
            (item.name, value)
            for item, value in zip(inequalities, lambdas, strict=True)
            if value < 0
        ]
        raise RuntimeError(f"rational correction made a multiplier negative: {negative}")

    exact_stationarity = [Fraction(0) for _ in range(row_count)]
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        for row, coefficient in enumerate([*item.values, item.margin]):
            exact_stationarity[row] += multiplier * coefficient
    for multiplier, item in zip(nus, equalities, strict=True):
        for row, coefficient in enumerate([*item.values, item.margin]):
            exact_stationarity[row] += multiplier * coefficient
    if exact_stationarity != [*([Fraction(0)] * value_count), Fraction(1)]:
        raise RuntimeError("exact dual stationarity failed")

    size = len(inequalities[0].matrix)
    slack = _zero_matrix(size)
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    for multiplier, item in zip(nus, equalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    leading_minors = [
        _determinant([row[:order] for row in slack[:order]])
        for order in range(1, size + 1)
    ]
    if any(value <= 0 for value in leading_minors):
        raise RuntimeError(
            f"rational dual slack is not positive definite: {leading_minors}"
        )
    dual_objective = sum(
        (multiplier * item.rhs for multiplier, item in zip(lambdas, inequalities, strict=True)),
        Fraction(0),
    ) + sum(
        (multiplier * item.rhs for multiplier, item in zip(nus, equalities, strict=True)),
        Fraction(0),
    )
    if dual_objective >= 0:
        raise RuntimeError(f"dual does not exclude strict attainability: {dual_objective}")
    return lambdas, nus, slack, dual_objective


def _solve_cell(cell: tuple[int, int]) -> dict[str, Any]:
    problem, inequalities, equalities, cvx_inequalities, cvx_equalities = (
        _build_problem(cell, signed_terminal_margin=True)
    )
    value = problem.solve(
        solver="CLARABEL",
        tol_gap_abs=1.0e-10,
        tol_feas=1.0e-10,
        tol_gap_rel=1.0e-10,
        max_iter=1000,
        verbose=False,
    )
    lambdas = np.asarray([item.dual_value for item in cvx_inequalities], dtype=float)
    nus = np.asarray([item.dual_value for item in cvx_equalities], dtype=float)
    value_stationarity = sum(
        multiplier * _as_float_vector(item.values)
        for multiplier, item in zip(lambdas, inequalities, strict=True)
    ) + sum(
        multiplier * _as_float_vector(item.values)
        for multiplier, item in zip(nus, equalities, strict=True)
    )
    margin_stationarity = sum(
        multiplier * float(item.margin)
        for multiplier, item in zip(lambdas, inequalities, strict=True)
    ) + sum(
        multiplier * float(item.margin)
        for multiplier, item in zip(nus, equalities, strict=True)
    )
    slack = sum(
        (
            multiplier * _as_float_matrix(item.matrix)
            for multiplier, item in zip(lambdas, inequalities, strict=True)
        ),
        start=np.zeros_like(_as_float_matrix(inequalities[0].matrix)),
    ) + sum(
        (
            multiplier * _as_float_matrix(item.matrix)
            for multiplier, item in zip(nus, equalities, strict=True)
        ),
        start=np.zeros_like(_as_float_matrix(equalities[0].matrix)),
    )
    objective = sum(
        multiplier * float(item.rhs)
        for multiplier, item in zip(lambdas, inequalities, strict=True)
    ) + sum(
        multiplier * float(item.rhs)
        for multiplier, item in zip(nus, equalities, strict=True)
    )
    rational_lambdas, rational_nus, rational_slack, rational_objective = (
        _recover_rational_dual(inequalities, equalities, lambdas, nus)
    )
    leading_minors = [
        _determinant([row[:order] for row in rational_slack[:order]])
        for order in range(1, len(rational_slack) + 1)
    ]
    print(
        f"cell={cell} status={problem.status} primal={value:.9g} "
        f"dual={objective:.9g} exact={float(rational_objective):.9g} "
        f"stationarity=({np.linalg.norm(value_stationarity):.2e},"
        f"{margin_stationarity:.9g}) eigmin={np.linalg.eigvalsh(slack)[0]:.2e}"
    )
    return {
        "cell": list(cell),
        "primal": {
            "gram_order": len(rational_slack),
            "function_value_count": len(inequalities[0].values),
            "inequality_count": len(inequalities),
            "equality_count": len(equalities),
            "objective": "maximize signed cell-feasibility margin tau",
            "floating_status": problem.status,
            "floating_objective": float(value),
        },
        "dual": {
            "inequality_multipliers": {
                item.name: str(multiplier)
                for item, multiplier in zip(
                    inequalities, rational_lambdas, strict=True
                )
                if multiplier
            },
            "equality_multipliers": {
                item.name: str(multiplier)
                for item, multiplier in zip(
                    equalities, rational_nus, strict=True
                )
                if multiplier
            },
            "slack_matrix": _matrix_to_json(rational_slack),
            "leading_principal_minors": [str(entry) for entry in leading_minors],
            "certified_upper_bound": str(rational_objective),
        },
    }


def main() -> None:
    certificates = [_solve_cell(cell) for cell in BAD_CELLS]
    exact_bounds = [
        Fraction(item["dual"]["certified_upper_bound"]) for item in certificates
    ]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "cells": [list(cell) for cell in BAD_CELLS],
            "horizon": 3,
            "function_class": "F_{9/10,1}",
            "nonquadratic_realization": "f(t)=9*t^2/20+log(cosh(t))/10",
            "proposal_contract": "24/25 <= ||y-x|| <= 97/100 and ||y-x+g_x|| <= 1/100",
            "signed_margin": (
                "terminal squared norms plus tau are at most epsilon^2; "
                "survival squared norms are at least epsilon^2 plus tau"
            ),
            "claim": (
                "all ten cost-violating H=3 cells have signed-feasibility "
                "margin optimum below zero"
            ),
        },
        "parameters": {
            "strong_convexity": "9/10",
            "smoothness": "1",
            "step_size": "1",
            "proposal_step": "1",
            "proposal_norm_lower": "24/25",
            "proposal_norm_upper": "97/100",
            "contract_radius": "1/100",
            "initial_distance_upper": "6/5",
            "tolerance": "7/50",
            "derived_trace_bound": "27",
        },
        "summary": {
            "certificate_count": len(certificates),
            "total_positive_leading_minors": sum(
                len(item["dual"]["leading_principal_minors"])
                for item in certificates
            ),
            "maximum_certified_upper_bound": str(max(exact_bounds)),
        },
        "certificates": certificates,
        "environment": {
            "generator_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(VERIFIER),
            "cvxpy": cp.__version__,
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"EXACT: {len(certificates)} cost-violating cells, "
        f"{payload['summary']['total_positive_leading_minors']} positive leading "
        f"minors, max upper={max(exact_bounds)}, payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
