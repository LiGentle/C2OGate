#!/usr/bin/env python3
"""Verify the infinite-class joint-only PEP suite using only stdlib arithmetic."""

from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_generic_nonquadratic_pep_dual import (  # noqa: E402
    LinearConstraint,
    Matrix,
    _basis,
    _canonical,
    _file_hash,
    _matrix_add,
    _require,
    _scaled_sum,
    _symmetric_outer,
    _vector_subtract,
    _zero_matrix,
    _zero_vector,
)


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
        _require(pivot > 0, f"positive LDL pivot {column + 1}")
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


def _build_constraints(
    cell: tuple[int, int],
) -> tuple[list[LinearConstraint], list[LinearConstraint]]:
    baseline_calls, candidate_calls = cell
    _require(cell in BAD_CELLS, "cost-violating cell")
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
    candidate_gradients = [
        _basis(atom_count, branch_size + k) for k in range(branch_size)
    ]
    optimum = _basis(atom_count, atom_count - 2)
    proposal = _basis(atom_count, atom_count - 1)
    zero = _zero_vector(atom_count)
    baseline_points = [zero]
    candidate_points = [proposal]
    for k in range(1, branch_size):
        baseline_points.append(
            _scaled_sum(
                zero,
                [(-step_size, gradient) for gradient in baseline_gradients[:k]],
            )
        )
        candidate_points.append(
            _scaled_sum(
                proposal,
                [(-step_size, gradient) for gradient in candidate_gradients[:k]],
            )
        )
    points = baseline_points + candidate_points + [optimum]
    gradients = baseline_gradients + candidate_gradients + [zero]
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
            baseline_gradients[baseline_calls],
            baseline_gradients[baseline_calls],
        ),
        margin=Fraction(1),
        rhs=tolerance_squared,
    )
    add_inequality(
        "hybrid_terminal",
        _symmetric_outer(
            candidate_gradients[candidate_calls],
            candidate_gradients[candidate_calls],
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
        ("hybrid", candidate_gradients[:candidate_calls]),
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


def _verify_certificate(certificate: dict[str, Any]) -> tuple[Fraction, int]:
    cell = tuple(certificate["cell"])
    inequalities, equalities = _build_constraints(cell)
    primal = certificate["primal"]
    _require(primal["gram_order"] == 10, "Gram order")
    _require(primal["function_value_count"] == 9, "function-value count")
    _require(primal["inequality_count"] == len(inequalities), "inequality count")
    _require(primal["equality_count"] == len(equalities), "equality count")
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
    _require(all(value >= 0 for value in lambdas), "dual multiplier sign")
    stationarity = [Fraction(0) for _ in range(10)]
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    for multiplier, item in zip(nus, equalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    _require(
        stationarity == [*([Fraction(0)] * 9), Fraction(1)],
        "dual stationarity",
    )
    slack = _zero_matrix(10)
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    for multiplier, item in zip(nus, equalities, strict=True):
        slack = _matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    pivots = _positive_ldl_pivots(slack)
    _require(
        dual["positive_ldl_pivot_count"] == len(pivots) == 10,
        "positive pivot count",
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
    _require(
        objective == Fraction(dual["certified_upper_bound"]), "dual objective"
    )
    _require(objective < 0, "strict bad-cell exclusion")
    return objective, len(pivots)


def _stopping_time(curvature: Fraction, gradient: Fraction) -> int:
    calls = 0
    while abs(gradient) > PARAMETERS["tolerance"]:
        gradient *= 1 - curvature
        calls += 1
    return calls


def verify_payload(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    recorded_hash = payload.get("payload_sha256")
    unsigned = dict(payload)
    unsigned.pop("payload_sha256", None)
    _require(recorded_hash == sha256(_canonical(unsigned)).hexdigest(), "payload hash")
    _require(payload.get("schema") == SCHEMA, "schema")
    declaration = payload["declaration"]
    _require(declaration["cells"] == [list(cell) for cell in BAD_CELLS], "cells")
    _require(declaration["horizon"] == HORIZON, "horizon")
    _require(
        declaration["function_class"]
        == "full infinite class F_{1/2,1} consistent with the transcript",
        "function class",
    )
    _require(
        payload["parameters"]
        == {key: str(value) for key, value in PARAMETERS.items()},
        "parameters",
    )
    q = Fraction(1, 2)
    distance = PARAMETERS["initial_distance_upper"] + PARAMETERS[
        "proposal_norm_upper"
    ]
    tolerance = PARAMETERS["tolerance"]
    _require(distance * q**2 > tolerance >= distance * q**3, "natural horizon")
    trace_consequence = (
        4 * PARAMETERS["initial_distance_upper"] ** 2
        + 4 * distance**2
        + PARAMETERS["initial_distance_upper"] ** 2
        + PARAMETERS["proposal_norm_upper"] ** 2
    )
    _require(trace_consequence < PARAMETERS["derived_trace_bound"], "trace bound")

    gradient = Fraction(1, 2)
    candidate = -Fraction(11, 20)
    pairs = []
    for witness, curvature in zip(
        payload["witnesses"], (Fraction(1, 2), Fraction(1)), strict=True
    ):
        _require(Fraction(witness["curvature"]) == curvature, "witness curvature")
        _require(abs(gradient / curvature) <= 1, "witness distance")
        _require(
            PARAMETERS["proposal_norm_lower"]
            <= abs(candidate)
            <= PARAMETERS["proposal_norm_upper"],
            "witness proposal norm",
        )
        _require(
            abs(candidate + PARAMETERS["proposal_step"] * gradient)
            <= PARAMETERS["contract_radius"],
            "witness proposal contract",
        )
        candidate_gradient = gradient + curvature * candidate
        baseline_calls = _stopping_time(curvature, gradient)
        candidate_calls = _stopping_time(curvature, candidate_gradient)
        _require(witness["baseline_calls"] == baseline_calls, "baseline calls")
        _require(witness["candidate_calls"] == candidate_calls, "candidate calls")
        pairs.append((baseline_calls, candidate_calls))
    _require(pairs == [(2, 1), (1, 0)], "witness stopping pairs")

    marginal = payload["marginal_certificate"]
    gradient_lower = (
        PARAMETERS["proposal_norm_lower"] - PARAMETERS["contract_radius"]
    ) / PARAMETERS["proposal_step"]
    gradient_upper = (
        PARAMETERS["proposal_norm_upper"] + PARAMETERS["contract_radius"]
    ) / PARAMETERS["proposal_step"]
    proposal_q = max(
        abs(1 - PARAMETERS["proposal_step"] * PARAMETERS["strong_convexity"]),
        abs(1 - PARAMETERS["proposal_step"] * PARAMETERS["smoothness"]),
    )
    candidate_gradient_upper = (
        proposal_q * gradient_upper
        + PARAMETERS["smoothness"] * PARAMETERS["contract_radius"]
    )
    one_step_upper = q * candidate_gradient_upper
    _require(gradient_lower == Fraction(marginal["current_gradient_lower"]), "gradient lower")
    _require(gradient_upper == Fraction(marginal["current_gradient_upper"]), "gradient upper")
    _require(proposal_q == Fraction(marginal["proposal_step_contraction"]), "proposal contraction")
    _require(
        candidate_gradient_upper
        == Fraction(marginal["candidate_gradient_upper"]),
        "candidate gradient upper",
    )
    _require(
        one_step_upper
        == Fraction(marginal["one_step_candidate_gradient_upper"])
        < tolerance
        < gradient_lower,
        "exact marginal call bounds",
    )
    _require(marginal["baseline_lower_calls"] == 1, "baseline marginal")
    _require(marginal["candidate_upper_calls"] == 1, "candidate marginal")
    _require(marginal["rectangle_call_difference"] == 0, "rectangle difference")
    _require(Fraction(marginal["rectangle_certificate_value"]) == 1, "rectangle value")

    certificates = payload["certificates"]
    _require(
        [item["cell"] for item in certificates] == [list(cell) for cell in BAD_CELLS],
        "certificate order",
    )
    verified = [_verify_certificate(item) for item in certificates]
    bounds = [bound for bound, _ in verified]
    pivots = sum(count for _, count in verified)
    summary = payload["summary"]
    _require(summary["certificate_count"] == 10, "certificate count")
    _require(summary["positive_ldl_pivot_count"] == pivots == 100, "pivot count")
    _require(
        Fraction(summary["maximum_certified_upper_bound"]) == max(bounds),
        "maximum upper bound",
    )
    joint = payload["joint_certificate"]
    _require(joint["worst_call_difference"] == -1, "joint difference")
    _require(Fraction(joint["certificate_value"]) == 0, "joint value")
    _require(joint["joint_accept"] and not joint["rectangle_accept"], "decisions")
    if root is not None:
        environment = payload["environment"]
        _require(
            environment["generator_sha256"]
            == _file_hash(
                root
                / "experiments"
                / "generate_full_class_joint_only_pep_dual_certificate.py"
            ),
            "generator hash",
        )
        _require(
            environment["verifier_sha256"] == _file_hash(Path(__file__)),
            "verifier hash",
        )
    return {
        "payload_sha256": recorded_hash,
        "certificate_count": len(certificates),
        "positive_ldl_pivots": pivots,
        "maximum_certified_upper_bound": str(max(bounds)),
        "witness_pairs": [list(pair) for pair in pairs],
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
        "VERIFIED: full infinite-class joint-only PEP acceptance, "
        f"H=3, {result['certificate_count']} bad cells, "
        f"{result['positive_ldl_pivots']} positive LDL pivots, "
        f"witness pairs={result['witness_pairs']}"
    )


if __name__ == "__main__":
    main()
