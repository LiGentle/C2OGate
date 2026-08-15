#!/usr/bin/env python3
"""Independent exact verifier for the natural-H=10 joint-PEP dual suite.

This program imports only Python-standard-library code.  It reconstructs every
linear coefficient of the 66 Gram SDPs, checks dual stationarity and signs,
forms each rational slack matrix, proves positive definiteness by exact LDL^T
elimination, and checks that every dual objective is strictly negative.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, getcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from verify_generic_nonquadratic_pep_dual import (
    LinearConstraint,
    _basis,
    _canonical,
    _file_hash,
    _matrix_add,
    _scaled_sum,
    _symmetric_outer,
    _vector_subtract,
    _zero_matrix,
    _zero_vector,
)


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
RECOVERY_GRID = [
    (str(regularizer), f"{threshold:.0e}" if threshold else "0")
    for regularizer in (Fraction(1, 100_000), Fraction(1, 1_000_000))
    for threshold in (1.0e-6, 1.0e-8, 1.0e-10, 1.0e-12, 0.0)
]
Matrix = list[list[Fraction]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _build_constraints(
    cell: tuple[int, int],
) -> tuple[list[LinearConstraint], list[LinearConstraint]]:
    baseline_calls, hybrid_calls = cell
    _require(cell in BAD_CELLS, "certificate cell")
    mu = PARAMETERS["strong_convexity"]
    smoothness = PARAMETERS["smoothness"]
    step_size = PARAMETERS["step_size"]
    proposal_step = PARAMETERS["proposal_step"]
    proposal_lower = PARAMETERS["proposal_norm_lower"]
    proposal_upper = PARAMETERS["proposal_norm_upper"]
    contract_radius = PARAMETERS["contract_radius"]
    initial_distance_upper = PARAMETERS["initial_distance_upper"]
    tolerance = PARAMETERS["tolerance"]
    trace_bound = PARAMETERS["derived_trace_bound"]
    branch_size = HORIZON + 1
    atom_count = 2 * branch_size + 2
    value_count = 2 * branch_size + 1
    baseline_gradients = [_basis(atom_count, k) for k in range(branch_size)]
    hybrid_gradients = [
        _basis(atom_count, branch_size + k) for k in range(branch_size)
    ]
    optimum = _basis(atom_count, atom_count - 2)
    proposal = _basis(atom_count, atom_count - 1)
    zero = _zero_vector(atom_count)
    baseline_points = [zero]
    for k in range(1, branch_size):
        baseline_points.append(
            _scaled_sum(
                zero,
                [(-step_size, gradient) for gradient in baseline_gradients[:k]],
            )
        )
    hybrid_points = [proposal]
    for k in range(1, branch_size):
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
        values: list[Fraction] | None = None,
        margin: Fraction = Fraction(0),
        rhs: Fraction = Fraction(0),
    ) -> None:
        inequalities.append(
            LinearConstraint(
                name,
                matrix if matrix is not None else _zero_matrix(atom_count),
                values if values is not None else _zero_vector(value_count),
                margin,
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
    residual = _scaled_sum(proposal, [(proposal_step, baseline_gradients[0])])
    add_inequality(
        "proposal_contract",
        _symmetric_outer(residual, residual),
        rhs=contract_radius**2,
    )
    add_inequality(
        "derived_trace_bound",
        [
            [Fraction(int(row == column)) for column in range(atom_count)]
            for row in range(atom_count)
        ],
        rhs=trace_bound,
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
            values = _zero_vector(value_count)
            values[i] -= 1
            values[j] += 1
            add_inequality(f"interpolation_{i}_{j}", matrix, values)
    tolerance_squared = tolerance**2
    add_inequality(
        "baseline_terminal",
        _symmetric_outer(
            baseline_gradients[baseline_calls], baseline_gradients[baseline_calls]
        ),
        margin=Fraction(1),
        rhs=tolerance_squared,
    )
    add_inequality(
        "hybrid_terminal",
        _symmetric_outer(
            hybrid_gradients[hybrid_calls], hybrid_gradients[hybrid_calls]
        ),
        margin=Fraction(1),
        rhs=tolerance_squared,
    )
    add_inequality(
        "margin_upper",
        margin=Fraction(1),
        rhs=smoothness**2 * (initial_distance_upper + proposal_upper) ** 2,
    )
    for label, branch in (
        ("baseline", baseline_gradients[:baseline_calls]),
        ("hybrid", hybrid_gradients[:hybrid_calls]),
    ):
        for index, gradient in enumerate(branch):
            add_inequality(
                f"{label}_strict_{index}",
                _matrix_add((-Fraction(1), _symmetric_outer(gradient, gradient))),
                margin=Fraction(1),
                rhs=-tolerance_squared,
            )
    return inequalities, equalities


def _positive_ldl_pivots(matrix: Matrix) -> list[Fraction]:
    size = len(matrix)
    lower = _zero_matrix(size)
    pivots: list[Fraction] = []
    for column in range(size):
        pivot = matrix[column][column] - sum(
            (
                lower[column][index] ** 2 * pivots[index]
                for index in range(column)
            ),
            Fraction(0),
        )
        _require(pivot > 0, f"slack LDL pivot {column + 1}")
        pivots.append(pivot)
        lower[column][column] = Fraction(1)
        for row in range(column + 1, size):
            numerator = matrix[row][column] - sum(
                (
                    lower[row][index]
                    * lower[column][index]
                    * pivots[index]
                    for index in range(column)
                ),
                Fraction(0),
            )
            lower[row][column] = numerator / pivot
    return pivots


def _verify_certificate(certificate: dict[str, Any]) -> tuple[Fraction, int]:
    cell = tuple(certificate["cell"])
    inequalities, equalities = _build_constraints(cell)
    primal = certificate["primal"]
    _require(primal["gram_order"] == 24, "Gram order")
    _require(primal["function_value_count"] == 23, "function-value count")
    _require(primal["inequality_count"] == len(inequalities), "inequality count")
    _require(primal["equality_count"] == len(equalities) == 1, "equality count")
    _require(
        primal["objective"] == "maximize signed cell-feasibility margin tau",
        "objective",
    )
    dual = certificate["dual"]
    raw_lambdas = dual["inequality_multipliers"]
    raw_nus = dual["equality_multipliers"]
    _require(
        set(raw_lambdas) <= {item.name for item in inequalities},
        "unknown inequality multiplier",
    )
    _require(
        set(raw_nus) <= {item.name for item in equalities},
        "unknown equality multiplier",
    )
    lambdas = [Fraction(raw_lambdas.get(item.name, "0")) for item in inequalities]
    nus = [Fraction(raw_nus.get(item.name, "0")) for item in equalities]
    _require(all(multiplier >= 0 for multiplier in lambdas), "multiplier sign")
    stationarity = [Fraction(0) for _ in range(24)]
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    for multiplier, item in zip(nus, equalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    _require(stationarity == [*([Fraction(0)] * 23), Fraction(1)], "stationarity")
    slack = _zero_matrix(24)
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    for multiplier, item in zip(nus, equalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    _require(slack == [list(row) for row in zip(*slack, strict=True)], "slack symmetry")
    pivots = _positive_ldl_pivots(slack)
    _require(
        dual["positive_leading_principal_minor_count"] == len(pivots) == 24,
        "positive-pivot count",
    )
    objective = sum(
        (
            multiplier * item.rhs
            for multiplier, item in zip(lambdas, inequalities, strict=True)
        ),
        Fraction(0),
    ) + sum(
        (
            multiplier * item.rhs
            for multiplier, item in zip(nus, equalities, strict=True)
        ),
        Fraction(0),
    )
    _require(objective == Fraction(dual["certified_upper_bound"]), "dual objective")
    _require(objective < 0, "strict cell exclusion")
    recovery = certificate["recovery"]
    attempts = recovery["ordered_grid_attempts"]
    _require(1 <= len(attempts) <= len(RECOVERY_GRID), "recovery attempt count")
    observed_grid = [
        (item["regularizer"], item["active_threshold"]) for item in attempts
    ]
    _require(observed_grid == RECOVERY_GRID[: len(attempts)], "recovery grid order")
    _require(
        all(item["outcome"] == "failure" for item in attempts[:-1]),
        "pre-success recovery outcomes",
    )
    _require(attempts[-1]["outcome"] == "success", "selected recovery outcome")
    _require(
        recovery["selected_configuration"]
        == {
            "regularizer": attempts[-1]["regularizer"],
            "active_threshold": attempts[-1]["active_threshold"],
        },
        "selected recovery configuration",
    )
    _require(
        recovery["producer_guarantee"] == "heuristic success-or-fail",
        "producer guarantee",
    )
    return objective, len(pivots)


def _expected_recovery_grid(certificates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for regularizer, threshold in RECOVERY_GRID:
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


def _tanh(value: Decimal) -> Decimal:
    exponential = (Decimal(2) * value).exp()
    return (exponential - 1) / (exponential + 1)


def _verify_nonempty_nonlinear_class() -> None:
    getcontext().prec = 80
    point = (Decimal("0.9"), Decimal("0.4"))
    gradient = tuple(
        Decimal("0.1") * value + Decimal("0.9") * _tanh(value)
        for value in point
    )
    gradient_norm = sum(value * value for value in gradient).sqrt()
    proposal = tuple(-Decimal("0.8") * value / gradient_norm for value in gradient)
    proposal_norm = sum(value * value for value in proposal).sqrt()
    residual_norm = sum(
        (proposal_value + gradient_value) ** 2
        for proposal_value, gradient_value in zip(proposal, gradient, strict=True)
    ).sqrt()
    point_norm = sum(value * value for value in point).sqrt()
    _require(Decimal("0.79") <= proposal_norm <= Decimal("0.81"), "realization proposal")
    _require(residual_norm <= Decimal("0.1"), "realization contract")
    _require(point_norm <= Decimal("1"), "realization distance")
    third_derivative = -Decimal("1.8") * (
        Decimal(1) - _tanh(point[0]) ** 2
    ) * _tanh(point[0])
    _require(third_derivative < 0, "nonquadratic realization")


def verify_payload(
    payload: dict[str, Any],
    *,
    root: Path | None = None,
    progress: bool = False,
) -> dict[str, Any]:
    recorded_hash = payload.get("payload_sha256")
    unsigned = dict(payload)
    unsigned.pop("payload_sha256", None)
    _require(recorded_hash == sha256(_canonical(unsigned)).hexdigest(), "payload hash")
    _require(payload.get("schema") == SCHEMA, "schema")
    declaration = payload["declaration"]
    _require(declaration["cells"] == [list(cell) for cell in BAD_CELLS], "cell set")
    _require(declaration["natural_horizon"] == HORIZON, "natural horizon")
    _require(declaration["audit_padding"] == 0, "audit padding")
    _require(declaration["horizon"] == HORIZON, "horizon")
    _require(declaration["bad_cell_rule"] == "hybrid_calls >= baseline_calls", "bad-cell rule")
    _require(declaration["cost_exact_units"] == "2/5", "certificate cost")
    _require(declaration["minimum_saved_calls"] == 1, "minimum saving")
    _require(
        payload["parameters"] == {key: str(value) for key, value in PARAMETERS.items()},
        "parameters",
    )
    residual_bound = Fraction(181, 100)
    contraction = Fraction(9, 10)
    computed_horizon = 0
    while residual_bound > PARAMETERS["tolerance"]:
        residual_bound *= contraction
        computed_horizon += 1
    _require(computed_horizon == HORIZON, "formula-derived horizon")
    trace_consequence = (
        (HORIZON + 1) * PARAMETERS["initial_distance_upper"] ** 2
        + (HORIZON + 1)
        * (
            PARAMETERS["initial_distance_upper"]
            + PARAMETERS["proposal_norm_upper"]
        )
        ** 2
        + PARAMETERS["initial_distance_upper"] ** 2
        + PARAMETERS["proposal_norm_upper"] ** 2
    )
    _require(trace_consequence < PARAMETERS["derived_trace_bound"], "trace bound")
    _verify_nonempty_nonlinear_class()
    certificates = payload["certificates"]
    _require(
        [item["cell"] for item in certificates] == [list(cell) for cell in BAD_CELLS],
        "certificate order",
    )
    verified: list[tuple[Fraction, int]] = []
    for completed, certificate in enumerate(certificates, start=1):
        verified.append(_verify_certificate(certificate))
        if progress and (completed % 10 == 0 or completed == len(certificates)):
            print(f"verified={completed}/{len(certificates)}", flush=True)
    bounds = [bound for bound, _ in verified]
    total_pivots = sum(count for _, count in verified)
    summary = payload["summary"]
    _require(summary["certificate_count"] == len(BAD_CELLS) == 66, "certificate count")
    _require(summary["maximum_gram_order"] == 24, "maximum Gram order")
    _require(summary["maximum_inequality_count"] == 534, "maximum inequalities")
    _require(
        summary["positive_leading_principal_minor_count"] == total_pivots,
        "positive-pivot total",
    )
    _require(
        Fraction(summary["maximum_certified_upper_bound"]) == max(bounds),
        "maximum upper bound",
    )
    _require(
        summary["recovery_grid"] == _expected_recovery_grid(certificates),
        "recovery grid summary",
    )
    _require(
        summary["certified_cell_progress"]
        == "66/66 independently replayable exclusions constructed",
        "certified-cell progress",
    )
    _require(
        summary["incomplete_recovery_outcome"] == "uncertified",
        "incomplete recovery outcome",
    )
    if root is not None:
        environment = payload["environment"]
        _require(
            environment["generator_sha256"]
            == _file_hash(root / "experiments" / "generate_h10_generic_pep_dual_certificate.py"),
            "generator hash",
        )
        _require(environment["verifier_sha256"] == _file_hash(Path(__file__)), "verifier hash")
    return {
        "payload_sha256": recorded_hash,
        "certificate_count": len(certificates),
        "maximum_certified_upper_bound": str(max(bounds)),
        "positive_ldl_pivots": total_pivots,
        "natural_horizon": HORIZON,
        "maximum_gram_order": 24,
        "maximum_inequality_count": 534,
        "certified_cell_progress": summary["certified_cell_progress"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    result = verify_payload(
        json.loads(args.payload.read_text(encoding="utf-8")),
        root=args.root,
        progress=True,
    )
    print(
        "VERIFIED: natural-H=10 generic joint-PEP dual suite, "
        f"{result['certificate_count']} cost-violating cells, "
        f"Gram order <= {result['maximum_gram_order']}, "
        f"{result['positive_ldl_pivots']} exact positive LDL pivots, "
        f"progress={result['certified_cell_progress']}"
    )


if __name__ == "__main__":
    main()
