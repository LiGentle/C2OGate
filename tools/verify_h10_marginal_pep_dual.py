#!/usr/bin/env python3
"""Standard-library verifier for the flagship marginal PEP certificate."""

from __future__ import annotations

import argparse
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
Matrix = list[list[Fraction]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _constraints() -> tuple[list[LinearConstraint], list[LinearConstraint]]:
    atom_count = 4
    value_count = 3
    gradient_x = _basis(atom_count, 0)
    gradient_y = _basis(atom_count, 1)
    optimum = _basis(atom_count, 2)
    proposal = _basis(atom_count, 3)
    zero = _zero_vector(atom_count)
    points = [zero, proposal, optimum]
    gradients = [gradient_x, gradient_y, zero]
    inequalities: list[LinearConstraint] = []
    equalities: list[LinearConstraint] = []

    def add(
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
    add(
        "proposal_norm_upper",
        _symmetric_outer(proposal, proposal),
        rhs=PARAMETERS["proposal_norm_upper"] ** 2,
    )
    add(
        "proposal_norm_lower",
        _matrix_add((-Fraction(1), _symmetric_outer(proposal, proposal))),
        rhs=-(PARAMETERS["proposal_norm_lower"] ** 2),
    )
    add(
        "initial_distance",
        _symmetric_outer(optimum, optimum),
        rhs=PARAMETERS["initial_distance_upper"] ** 2,
    )
    residual = _scaled_sum(proposal, [(Fraction(1), gradient_x)])
    add(
        "proposal_contract",
        _symmetric_outer(residual, residual),
        rhs=PARAMETERS["contract_radius"] ** 2,
    )
    add(
        "derived_trace_bound",
        [[Fraction(int(i == j)) for j in range(atom_count)] for i in range(atom_count)],
        rhs=PARAMETERS["derived_trace_bound"],
    )
    mu = PARAMETERS["strong_convexity"]
    smoothness = PARAMETERS["smoothness"]
    denominator = 2 * (1 - mu / smoothness)
    for i in range(3):
        for j in range(3):
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
            add(f"interpolation_{i}_{j}", matrix, values)
    add(
        "objective_link",
        _matrix_add((-Fraction(1), _symmetric_outer(gradient_y, gradient_y))),
        margin=Fraction(1),
        rhs=-(PARAMETERS["tolerance"] ** 2),
    )
    return inequalities, equalities


def _positive_ldl(matrix: Matrix) -> list[Fraction]:
    lower = _zero_matrix(len(matrix))
    pivots: list[Fraction] = []
    for column in range(len(matrix)):
        pivot = matrix[column][column] - sum(
            (
                lower[column][index] ** 2 * pivots[index]
                for index in range(column)
            ),
            Fraction(0),
        )
        _require(pivot > 0, f"positive LDL pivot {column + 1}")
        pivots.append(pivot)
        lower[column][column] = 1
        for row in range(column + 1, len(matrix)):
            lower[row][column] = (
                matrix[row][column]
                - sum(
                    (
                        lower[row][index]
                        * lower[column][index]
                        * pivots[index]
                        for index in range(column)
                    ),
                    Fraction(0),
                )
            ) / pivot
    return pivots


def verify_payload(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    unsigned = dict(payload)
    recorded = unsigned.pop("payload_sha256", None)
    _require(recorded == sha256(_canonical(unsigned)).hexdigest(), "payload hash")
    _require(payload.get("schema") == SCHEMA, "schema")
    _require(
        payload["parameters"] == {key: str(value) for key, value in PARAMETERS.items()},
        "parameters",
    )
    inequalities, equalities = _constraints()
    certificate = payload["certificate"]
    primal = certificate["primal"]
    _require(primal["gram_order"] == 4, "Gram order")
    _require(primal["function_value_count"] == 3, "function-value count")
    _require(primal["inequality_count"] == len(inequalities), "inequality count")
    _require(primal["equality_count"] == 1, "equality count")
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
    _require(all(value >= 0 for value in lambdas), "multiplier sign")
    stationarity = [Fraction(0) for _ in range(4)]
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    for multiplier, item in zip(nus, equalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    _require(stationarity == [Fraction(0), Fraction(0), Fraction(0), Fraction(1)], "stationarity")
    slack = _zero_matrix(4)
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    for multiplier, item in zip(nus, equalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    pivots = _positive_ldl(slack)
    _require(dual["positive_ldl_pivot_count"] == len(pivots) == 4, "pivot count")
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
    tolerance_squared = PARAMETERS["tolerance"] ** 2
    _require(objective == Fraction(dual["certified_margin_upper_bound"]), "dual objective")
    gradient_upper = objective + tolerance_squared
    _require(
        gradient_upper == Fraction(dual["certified_gradient_squared_upper_bound"]),
        "gradient upper bound",
    )
    _require(objective < 0, "candidate immediate termination")
    gradient_lower = (
        PARAMETERS["proposal_norm_lower"] - PARAMETERS["contract_radius"]
    )
    _require(gradient_lower > PARAMETERS["tolerance"], "baseline survives at x")
    consequences = payload["exact_consequences"]
    _require(consequences["baseline_marginal_lower"] == 1, "Lx")
    _require(consequences["candidate_marginal_upper"] == 0, "Uy")
    _require(consequences["rectangle_call_difference"] == -1, "rectangle difference")
    _require(
        consequences["rectangle_gate_value_with_max_cost_one"] == 0,
        "rectangle gate value",
    )
    # Exact attaining witness: f(t)=(t-4/5)^2/2, x=0, y=4/5.
    witness_distance = Fraction(4, 5)
    witness_gradient_x = -witness_distance
    _require(witness_distance <= PARAMETERS["initial_distance_upper"], "witness R")
    _require(
        PARAMETERS["proposal_norm_lower"]
        <= witness_distance
        <= PARAMETERS["proposal_norm_upper"],
        "witness D",
    )
    _require(witness_distance + witness_gradient_x == 0, "witness contract")
    _require(abs(witness_gradient_x) > PARAMETERS["tolerance"], "witness Nx>0")
    _require(Fraction(0) <= PARAMETERS["tolerance"], "witness Ny=0")
    if root is not None:
        environment = payload["environment"]
        _require(
            environment["generator_sha256"]
            == _file_hash(root / "experiments" / "generate_h10_marginal_certificate.py"),
            "generator hash",
        )
        _require(environment["verifier_sha256"] == _file_hash(Path(__file__)), "verifier hash")
    return {
        "payload_sha256": recorded,
        "gradient_squared_upper": str(gradient_upper),
        "rectangle_gate_value": 0,
        "positive_ldl_pivots": len(pivots),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    result = verify_payload(
        json.loads(args.payload.read_text(encoding="utf-8")), root=args.root
    )
    print(
        "VERIFIED: flagship exact marginals L_x=1, U_y=0, "
        f"rectangle gate value={result['rectangle_gate_value']}, "
        f"{result['positive_ldl_pivots']} positive LDL pivots"
    )


if __name__ == "__main__":
    main()
