#!/usr/bin/env python3
"""Generate exact rational SDP dual certificates from high-precision candidates."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import itertools
import json
from pathlib import Path
from typing import Any

import mpmath as mp


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "rational_sdp_dual_certificates.json"
VERIFIER = ROOT / "tools" / "verify_rational_dual_certificates.py"
SCHEMA = "c2o-rational-sdp-dual-certificates-v2"


Matrix = list[list[Fraction]]


def _q(value: int | str | Fraction) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(value)


def _identity(size: int) -> Matrix:
    return [
        [Fraction(int(row == column)) for column in range(size)]
        for row in range(size)
    ]


def _transpose(matrix: Matrix) -> Matrix:
    return [list(row) for row in zip(*matrix, strict=True)]


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    return [
        [
            sum(
                (left[row][index] * right[index][column] for index in range(len(right))),
                start=Fraction(0),
            )
            for column in range(len(right[0]))
        ]
        for row in range(len(left))
    ]


def _subtract(left: Matrix, right: Matrix) -> Matrix:
    return [
        [left[row][column] - right[row][column] for column in range(len(left))]
        for row in range(len(left))
    ]


def _scale(scalar: Fraction, matrix: Matrix) -> Matrix:
    return [[scalar * entry for entry in row] for row in matrix]


def _power(matrix: Matrix, exponent: int) -> Matrix:
    result = _identity(len(matrix))
    for _ in range(exponent):
        result = _multiply(result, matrix)
    return result


def _diagonal(values: list[Fraction]) -> Matrix:
    return [
        [value if row == column else Fraction(0) for column, value in enumerate(values)]
        for row in range(len(values))
    ]


def _plane_rotation(
    dimension: int,
    first: int,
    second: int,
    cosine: Fraction,
    sine: Fraction,
) -> Matrix:
    rotation = _identity(dimension)
    rotation[first][first] = cosine
    rotation[first][second] = -sine
    rotation[second][first] = sine
    rotation[second][second] = cosine
    return rotation


def _orthogonal_basis(dimension: int, rotations: list[tuple[int, int, str, str]]) -> Matrix:
    basis = _identity(dimension)
    for first, second, cosine, sine in rotations:
        basis = _multiply(
            basis,
            _plane_rotation(dimension, first, second, _q(cosine), _q(sine)),
        )
    return basis


def _matrix_to_json(matrix: Matrix) -> list[list[str]]:
    return [[str(entry) for entry in row] for row in matrix]


def _vector_to_json(vector: list[Fraction]) -> list[str]:
    return [str(entry) for entry in vector]


def _matvec(matrix: Matrix, vector: list[Fraction]) -> list[Fraction]:
    return [
        sum(
            (matrix[row][column] * vector[column] for column in range(len(vector))),
            start=Fraction(0),
        )
        for row in range(len(matrix))
    ]


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _determinant(matrix: Matrix) -> Fraction:
    work = [row.copy() for row in matrix]
    determinant = Fraction(1)
    for column in range(len(work)):
        pivot = next(
            (row for row in range(column, len(work)) if work[row][column]),
            None,
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


def _minimum_principal_minor(matrix: Matrix) -> Fraction:
    values: list[Fraction] = []
    for order in range(1, len(matrix) + 1):
        for indices in itertools.combinations(range(len(matrix)), order):
            principal = [[matrix[i][j] for j in indices] for i in indices]
            values.append(_determinant(principal))
    return min(values)


def _high_precision_smallest_eigenvalue(matrix: Matrix) -> mp.mpf:
    mp_matrix = mp.matrix(
        [[mp.mpf(entry.numerator) / entry.denominator for entry in row] for row in matrix]
    )
    eigenvalues, _ = mp.eigsy(mp_matrix)
    return min(eigenvalues)


def _instance(
    identifier: str,
    eigenvalues: list[str],
    rotations: list[tuple[int, int, str, str]],
    alpha: str,
    shift_calls: int,
    tolerance_squared: str,
    cost: str,
    current_displacement: list[str],
) -> dict[str, Any]:
    spectrum = [_q(value) for value in eigenvalues]
    dimension = len(spectrum)
    basis = _orthogonal_basis(dimension, rotations)
    hessian = _multiply(_multiply(basis, _diagonal(spectrum)), _transpose(basis))
    step = _subtract(_identity(dimension), _scale(_q(alpha), hessian))
    current = [_q(value) for value in current_displacement]
    if len(current) != dimension or sum(value * value for value in current) != 1:
        raise ValueError("the rational witness must have exact unit norm")
    candidate = _matvec(_power(step, shift_calls), current)
    tolerance = _q(tolerance_squared)
    residual_certificates: list[dict[str, Any]] = []
    for iteration in range(shift_calls):
        iterate_map = _power(step, iteration)
        objective = _multiply(
            _multiply(_transpose(iterate_map), _multiply(hessian, hessian)),
            iterate_map,
        )
        numeric_minimum = _high_precision_smallest_eigenvalue(objective)
        reconstructed = Fraction(mp.nstr(numeric_minimum, 90)).limit_denominator(
            10**12
        )
        slack = _subtract(objective, _scale(reconstructed, _identity(dimension)))
        if _minimum_principal_minor(slack) < 0:
            raise RuntimeError("high-precision rational reconstruction is not dual feasible")
        strict_gap = reconstructed - tolerance
        if strict_gap <= 0:
            raise RuntimeError("certificate does not exclude premature termination")
        residual_certificates.append(
            {
                "iteration": iteration,
                "primal": {
                    "objective_matrix": _matrix_to_json(objective),
                    "normalization_matrix": _matrix_to_json(_identity(dimension)),
                    "normalization_rhs": "1",
                    "cone": "W positive semidefinite",
                },
                "dual": {
                    "normalization_multiplier": str(reconstructed),
                    "slack_matrix": _matrix_to_json(slack),
                    "certified_lower_bound": str(reconstructed),
                },
                "strict_gap_over_tolerance_squared": str(strict_gap),
                "high_precision_candidate": mp.nstr(numeric_minimum, 80),
                "minimum_principal_minor": str(_minimum_principal_minor(slack)),
            }
        )
    return {
        "id": identifier,
        "dimension": dimension,
        "transcript_class": (
            "quadratic f(z)=0.5 z^T Q z with unit-norm current displacement"
        ),
        "hessian": _matrix_to_json(hessian),
        "orthogonal_eigenbasis": _matrix_to_json(basis),
        "eigenvalues": [str(value) for value in spectrum],
        "step_size": str(_q(alpha)),
        "current_displacement": _vector_to_json(current),
        "current_norm_squared": "1",
        "candidate_definition": "y=(I-alpha Q)^d x",
        "candidate_displacement": _vector_to_json(candidate),
        "candidate_shift_calls": shift_calls,
        "tolerance_squared": str(tolerance),
        "cost_exact_units": str(_q(cost)),
        "minimum_saved_calls": 1,
        "residual_dual_certificates": residual_certificates,
        "claimed_acceptance": True,
        "claimed_exact_call_saving": shift_calls,
    }


def main() -> None:
    mp.mp.dps = 110
    instances = [
        _instance(
            "rational_rotation_2d_shift_2",
            ["1/2", "3/4"],
            [(0, 1, "3/5", "4/5")],
            "1",
            2,
            "1/64",
            "3/2",
            ["3/5", "4/5"],
        ),
        _instance(
            "rational_rotation_3d_shift_3",
            ["1/4", "2/5", "3/5"],
            [(0, 1, "3/5", "4/5"), (1, 2, "5/13", "12/13")],
            "1/2",
            3,
            "1/64",
            "5/2",
            ["1/3", "2/3", "2/3"],
        ),
        _instance(
            "rational_rotation_4d_shift_4",
            ["1/5", "1/3", "1/2", "2/3"],
            [
                (0, 1, "3/5", "4/5"),
                (1, 2, "5/13", "12/13"),
                (2, 3, "7/25", "24/25"),
            ],
            "1/2",
            4,
            "1/100",
            "7/2",
            ["1/2", "1/2", "1/2", "1/2"],
        ),
    ]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "generation_method": (
                "110-decimal-digit symmetric eigensolve followed by bounded-denominator "
                "rational reconstruction"
            ),
            "verification_method": (
                "exact Fraction arithmetic, exact matrix identities, and all principal minors"
            ),
            "certificate_count": sum(
                len(instance["residual_dual_certificates"]) for instance in instances
            ),
            "instance_count": len(instances),
        },
        "environment": {
            "mpmath": mp.__version__,
            "generator_sha256": _file_hash(Path(__file__).resolve()),
            "verifier_sha256": _file_hash(VERIFIER),
        },
        "instances": instances,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
