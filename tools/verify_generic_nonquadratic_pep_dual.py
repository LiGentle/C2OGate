#!/usr/bin/env python3
"""Standard-library verifier for a generic nonquadratic joint-PEP dual.

The verifier reconstructs the complete rational Gram-SDP cell from the
declared transcript.  It does not import CVXPY, NumPy, or a conic solver.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, getcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


SCHEMA = "c2o-generic-nonquadratic-pep-dual-v1"
Matrix = list[list[Fraction]]


class LinearConstraint:
    def __init__(
        self,
        name: str,
        matrix: Matrix,
        values: list[Fraction],
        margin: Fraction,
        rhs: Fraction,
    ) -> None:
        self.name = name
        self.matrix = matrix
        self.values = values
        self.margin = margin
        self.rhs = rhs


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _zero_matrix(size: int) -> Matrix:
    return [[Fraction(0) for _ in range(size)] for _ in range(size)]


def _zero_vector(size: int) -> list[Fraction]:
    return [Fraction(0) for _ in range(size)]


def _basis(size: int, index: int) -> list[Fraction]:
    result = _zero_vector(size)
    result[index] = Fraction(1)
    return result


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


def _matrix(raw: list[list[str]]) -> Matrix:
    result = [[Fraction(value) for value in row] for row in raw]
    _require(result and all(len(row) == len(result) for row in result), "square matrix")
    return result


def _build_constraints() -> tuple[list[LinearConstraint], list[LinearConstraint]]:
    baseline_calls = 3
    hybrid_calls = 3
    mu = Fraction(9, 10)
    smoothness = Fraction(1)
    step_size = Fraction(1)
    proposal_step = Fraction(1)
    proposal_lower = Fraction(24, 25)
    proposal_upper = Fraction(97, 100)
    contract_radius = Fraction(1, 100)
    initial_distance_upper = Fraction(6, 5)
    tolerance = Fraction(7, 50)
    baseline_size = baseline_calls + 1
    hybrid_size = hybrid_calls + 1
    atom_count = baseline_size + hybrid_size + 2
    value_count = baseline_size + hybrid_size + 1
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
            "value_anchor", _zero_matrix(atom_count), anchor, Fraction(0), Fraction(0)
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
    tolerance_squared = tolerance**2
    add_inequality(
        "baseline_terminal",
        _symmetric_outer(baseline_gradients[-1], baseline_gradients[-1]),
        rhs=tolerance_squared,
    )
    add_inequality(
        "hybrid_terminal",
        _symmetric_outer(hybrid_gradients[-1], hybrid_gradients[-1]),
        rhs=tolerance_squared,
    )
    add_inequality(
        "margin_upper",
        margin=Fraction(1),
        rhs=smoothness**2 * (initial_distance_upper + proposal_upper) ** 2,
    )
    for label, branch in (
        ("baseline", baseline_gradients[:-1]),
        ("hybrid", hybrid_gradients[:-1]),
    ):
        for index, gradient in enumerate(branch):
            add_inequality(
                f"{label}_strict_{index}",
                _matrix_add(
                    (-Fraction(1), _symmetric_outer(gradient, gradient))
                ),
                margin=Fraction(1),
                rhs=-tolerance_squared,
            )
    return inequalities, equalities


def _tanh(value: Decimal) -> Decimal:
    exponential = (Decimal(2) * value).exp()
    return (exponential - 1) / (exponential + 1)


def verify_payload(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    recorded_hash = payload.get("payload_sha256")
    unsigned = dict(payload)
    unsigned.pop("payload_sha256", None)
    _require(recorded_hash == sha256(_canonical(unsigned)).hexdigest(), "payload hash")
    _require(payload.get("schema") == SCHEMA, "schema")
    declaration = payload["declaration"]
    _require(declaration["cell"] == [3, 3] and declaration["horizon"] == 3, "cell")
    _require(declaration["function_class"] == "F_{9/10,1}", "function class")
    _require(
        declaration["nonquadratic_realization"]
        == "f(t)=9*t^2/20+log(cosh(t))/10",
        "nonquadratic realization",
    )
    parameters = payload["parameters"]
    expected_parameters = {
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
    }
    _require(parameters == expected_parameters, "parameters")
    trace_consequence = (
        4 * Fraction(6, 5) ** 2
        + 4 * (Fraction(6, 5) + Fraction(97, 100)) ** 2
        + Fraction(6, 5) ** 2
        + Fraction(97, 100) ** 2
    )
    _require(trace_consequence < 27, "derived trace bound")

    getcontext().prec = 100
    gradient = Decimal(9) / Decimal(10) + _tanh(Decimal(1)) / Decimal(10)
    proposal = -gradient + Decimal(1) / Decimal(100)
    _require(Decimal("0.96") <= abs(proposal) <= Decimal("0.97"), "realized proposal")
    _require(abs(proposal + gradient) == Decimal("0.01"), "realized contract")
    third_derivative = -(
        Decimal(1) - _tanh(Decimal(1)) ** 2
    ) * _tanh(Decimal(1)) / Decimal(5)
    _require(third_derivative < 0, "nonquadratic witness")

    inequalities, equalities = _build_constraints()
    _require(payload["primal"]["gram_order"] == 10, "Gram order")
    _require(payload["primal"]["function_value_count"] == 9, "value count")
    _require(payload["primal"]["inequality_count"] == len(inequalities), "inequality count")
    _require(payload["primal"]["equality_count"] == len(equalities), "equality count")
    dual = payload["dual"]
    raw_lambdas = dual["inequality_multipliers"]
    raw_nus = dual["equality_multipliers"]
    inequality_names = {item.name for item in inequalities}
    equality_names = {item.name for item in equalities}
    _require(set(raw_lambdas) <= inequality_names, "unknown inequality multiplier")
    _require(set(raw_nus) <= equality_names, "unknown equality multiplier")
    lambdas = [Fraction(raw_lambdas.get(item.name, "0")) for item in inequalities]
    nus = [Fraction(raw_nus.get(item.name, "0")) for item in equalities]
    _require(all(value >= 0 for value in lambdas), "dual multiplier sign")

    stationarity = [Fraction(0) for _ in range(10)]
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    for multiplier, item in zip(nus, equalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    _require(stationarity == [*([Fraction(0)] * 9), Fraction(1)], "dual stationarity")

    slack = _zero_matrix(10)
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    for multiplier, item in zip(nus, equalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    stored_slack = _matrix(dual["slack_matrix"])
    _require(slack == stored_slack, "dual slack identity")
    _require(slack == [list(row) for row in zip(*slack, strict=True)], "slack symmetry")
    leading_minors = [
        _determinant([row[:order] for row in slack[:order]])
        for order in range(1, 11)
    ]
    _require(all(value > 0 for value in leading_minors), "slack positive definiteness")
    _require(
        [Fraction(value) for value in dual["leading_principal_minors"]]
        == leading_minors,
        "recorded leading minors",
    )
    objective = sum(
        (multiplier * item.rhs for multiplier, item in zip(lambdas, inequalities, strict=True)),
        Fraction(0),
    ) + sum(
        (multiplier * item.rhs for multiplier, item in zip(nus, equalities, strict=True)),
        Fraction(0),
    )
    _require(objective == Fraction(dual["certified_upper_bound"]), "dual objective")
    _require(objective < 0, "strict cell exclusion")
    if root is not None:
        environment = payload["environment"]
        _require(
            environment["generator_sha256"]
            == _file_hash(root / "experiments" / "generate_generic_pep_dual_certificate.py"),
            "generator hash",
        )
        _require(environment["verifier_sha256"] == _file_hash(Path(__file__)), "verifier hash")
    return {
        "payload_sha256": recorded_hash,
        "cell": [3, 3],
        "certified_upper_bound": str(objective),
        "positive_leading_minors": len(leading_minors),
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
        "VERIFIED: generic nonquadratic H=3 joint-PEP dual, "
        f"cell {tuple(result['cell'])}, upper bound < 0, "
        f"{result['positive_leading_minors']} positive leading minors"
    )


if __name__ == "__main__":
    main()
