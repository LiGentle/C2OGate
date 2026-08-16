#!/usr/bin/env python3
"""Second H6 consumer with an independent SymPy coefficient builder.

This audit deliberately imports none of the producer or standard-library
consumer modules.  It translates the interpolation theorem and transcript
rows directly into SymPy matrices, then checks the complete rational dual
identity and exact LDL decomposition for every flagship cell.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import sympy as sp


SCHEMA = "c2o-h6-sympy-independent-consumer-v1"
HORIZON = 6
ATOM_COUNT = 16
VALUE_COUNT = 15


@dataclass(frozen=True)
class Constraint:
    name: str
    matrix: sp.Matrix
    values: tuple[sp.Rational, ...]
    margin: sp.Rational
    rhs: sp.Rational


def _q(value: str | int | float | sp.Rational) -> sp.Rational:
    return sp.Rational(value)


def _basis(index: int) -> sp.Matrix:
    return sp.eye(ATOM_COUNT)[:, index]


def _outer(left: sp.Matrix, right: sp.Matrix) -> sp.Matrix:
    return (left * right.T + right * left.T) / 2


def _values() -> list[sp.Rational]:
    return [_q(0) for _ in range(VALUE_COUNT)]


def _build_constraints(
    cell: tuple[int, int], parameters: dict[str, Any]
) -> tuple[list[Constraint], list[Constraint]]:
    baseline_calls, candidate_calls = cell
    if not (0 <= baseline_calls <= HORIZON and baseline_calls <= candidate_calls <= HORIZON):
        raise ValueError("not an H6 cost-violating cell")

    mu = _q(parameters["strong_convexity"])
    smoothness = _q(parameters["smoothness"])
    step = _q(parameters["step_size"])
    proposal_step = _q(parameters["proposal_step"])
    proposal_lower = _q(parameters["proposal_norm_lower"])
    proposal_upper = _q(parameters["proposal_norm_upper"])
    radius = _q(parameters["contract_radius"])
    distance = _q(parameters["initial_distance_upper"])
    tolerance = _q(parameters["tolerance"])
    trace_bound = _q(parameters["derived_trace_bound"])

    baseline_gradients = [_basis(k) for k in range(HORIZON + 1)]
    candidate_gradients = [_basis(HORIZON + 1 + k) for k in range(HORIZON + 1)]
    optimum = _basis(ATOM_COUNT - 2)
    proposal = _basis(ATOM_COUNT - 1)
    zero = sp.zeros(ATOM_COUNT, 1)
    baseline_points = [zero]
    candidate_points = [proposal]
    for k in range(1, HORIZON + 1):
        baseline_points.append(
            -step * sum(baseline_gradients[:k], sp.zeros(ATOM_COUNT, 1))
        )
        candidate_points.append(
            proposal
            - step * sum(candidate_gradients[:k], sp.zeros(ATOM_COUNT, 1))
        )
    points = [*baseline_points, *candidate_points, optimum]
    gradients = [*baseline_gradients, *candidate_gradients, zero]

    inequalities: list[Constraint] = []
    equalities: list[Constraint] = []

    def add(
        name: str,
        *,
        matrix: sp.Matrix | None = None,
        values: list[sp.Rational] | None = None,
        margin: sp.Rational = _q(0),
        rhs: sp.Rational = _q(0),
    ) -> None:
        inequalities.append(
            Constraint(
                name,
                matrix if matrix is not None else sp.zeros(ATOM_COUNT),
                tuple(values if values is not None else _values()),
                margin,
                rhs,
            )
        )

    anchor = _values()
    anchor[0] = _q(1)
    equalities.append(
        Constraint(
            "value_anchor",
            sp.zeros(ATOM_COUNT),
            tuple(anchor),
            _q(0),
            _q(0),
        )
    )
    add("proposal_norm_upper", matrix=_outer(proposal, proposal), rhs=proposal_upper**2)
    add("proposal_norm_lower", matrix=-_outer(proposal, proposal), rhs=-(proposal_lower**2))
    add("initial_distance", matrix=_outer(optimum, optimum), rhs=distance**2)
    residual = proposal + proposal_step * baseline_gradients[0]
    add("proposal_contract", matrix=_outer(residual, residual), rhs=radius**2)
    add("derived_trace_bound", matrix=sp.eye(ATOM_COUNT), rhs=trace_bound)

    denominator = 2 * (1 - mu / smoothness)
    for i, point_i in enumerate(points):
        for j, point_j in enumerate(points):
            if i == j:
                continue
            dx = point_i - point_j
            dg = gradients[i] - gradients[j]
            matrix = (
                _outer(dg, dg) / (smoothness * denominator)
                + mu * _outer(dx, dx) / denominator
                - 2 * mu * _outer(dg, dx) / (smoothness * denominator)
                + _outer(gradients[j], dx)
            )
            value_row = _values()
            value_row[i] -= 1
            value_row[j] += 1
            add(f"interpolation_{i}_{j}", matrix=matrix, values=value_row)

    tolerance_squared = tolerance**2
    add(
        "baseline_terminal",
        matrix=_outer(
            baseline_gradients[baseline_calls],
            baseline_gradients[baseline_calls],
        ),
        margin=_q(1),
        rhs=tolerance_squared,
    )
    add(
        "hybrid_terminal",
        matrix=_outer(
            candidate_gradients[candidate_calls],
            candidate_gradients[candidate_calls],
        ),
        margin=_q(1),
        rhs=tolerance_squared,
    )
    add(
        "margin_upper",
        margin=_q(1),
        rhs=smoothness**2 * (distance + proposal_upper) ** 2,
    )
    for label, branch in (
        ("baseline", baseline_gradients[:baseline_calls]),
        ("hybrid", candidate_gradients[:candidate_calls]),
    ):
        for index, gradient in enumerate(branch):
            add(
                f"{label}_strict_{index}",
                matrix=-_outer(gradient, gradient),
                margin=_q(1),
                rhs=-tolerance_squared,
            )
    return inequalities, equalities


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def verify_payload(payload: dict[str, Any]) -> dict[str, Any]:
    unsigned = dict(payload)
    recorded_hash = unsigned.pop("payload_sha256")
    if sha256(_canonical(unsigned)).hexdigest() != recorded_hash:
        raise ValueError("payload hash")
    if payload.get("schema") != "c2o-h6-joint-only-pep-dual-v1":
        raise ValueError("flagship schema")

    rows = []
    started = perf_counter()
    for certificate in payload["certificates"]:
        cell = tuple(certificate["cell"])
        inequalities, equalities = _build_constraints(cell, payload["parameters"])
        dual = certificate["dual"]
        raw_lambdas = dual["inequality_multipliers"]
        raw_nus = dual["equality_multipliers"]
        if set(raw_lambdas) - {item.name for item in inequalities}:
            raise ValueError(f"unknown inequality multiplier in {cell}")
        if set(raw_nus) - {item.name for item in equalities}:
            raise ValueError(f"unknown equality multiplier in {cell}")
        lambdas = [_q(raw_lambdas.get(item.name, "0")) for item in inequalities]
        nus = [_q(raw_nus.get(item.name, "0")) for item in equalities]
        if any(value < 0 for value in lambdas):
            raise ValueError(f"negative inequality multiplier in {cell}")

        stationarity = [_q(0) for _ in range(VALUE_COUNT + 1)]
        slack = sp.zeros(ATOM_COUNT)
        objective = _q(0)
        for multiplier, item in zip(lambdas, inequalities, strict=True):
            for index, coefficient in enumerate((*item.values, item.margin)):
                stationarity[index] += multiplier * coefficient
            if multiplier:
                slack += multiplier * item.matrix
                objective += multiplier * item.rhs
        for multiplier, item in zip(nus, equalities, strict=True):
            for index, coefficient in enumerate((*item.values, item.margin)):
                stationarity[index] += multiplier * coefficient
            if multiplier:
                slack += multiplier * item.matrix
                objective += multiplier * item.rhs
        if stationarity != [*([_q(0)] * VALUE_COUNT), _q(1)]:
            raise ValueError(f"dual stationarity in {cell}")
        if objective != _q(dual["certified_upper_bound"]) or objective >= 0:
            raise ValueError(f"strict dual objective in {cell}")
        if slack != slack.T:
            raise ValueError(f"symmetric slack in {cell}")
        _, diagonal = slack.LDLdecomposition(hermitian=False)
        pivots = [diagonal[index, index] for index in range(ATOM_COUNT)]
        if not all(value > 0 for value in pivots):
            raise ValueError(f"positive LDL pivots in {cell}")
        rows.append(
            {
                "cell": list(cell),
                "certified_upper_bound": str(objective),
                "positive_ldl_pivot_count": len(pivots),
            }
        )
    return {
        "schema": SCHEMA,
        "source_payload_sha256": recorded_hash,
        "certificate_count": len(rows),
        "positive_ldl_pivot_count": sum(
            row["positive_ldl_pivot_count"] for row in rows
        ),
        "maximum_certified_upper_bound": str(
            max(_q(row["certified_upper_bound"]) for row in rows)
        ),
        "wall_seconds": perf_counter() - started,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = json.loads(args.payload.read_text(encoding="utf-8"))
    result = verify_payload(source)
    result["environment"] = {
        "python": sys.version,
        "platform": platform.platform(),
        "sympy": sp.__version__,
        "consumer_sha256": _file_hash(Path(__file__)),
        "input_file_sha256": _file_hash(args.payload),
    }
    result["payload_sha256"] = sha256(_canonical(result)).hexdigest()
    if args.output is not None:
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(
        "VERIFIED: independent SymPy H6 consumer, "
        f"{result['certificate_count']} cells, "
        f"{result['positive_ldl_pivot_count']} exact positive pivots"
    )


if __name__ == "__main__":
    main()
