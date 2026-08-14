#!/usr/bin/env python3
"""Independent exact verifier for rational two-oracle SDP certificates.

This file deliberately imports only the Python standard library.  It does not
trust CVXPY, a conic solver, NumPy eigenvalues, or a floating-point tolerance.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import itertools
import json
from pathlib import Path
from typing import Any


SCHEMA = "c2o-rational-sdp-dual-certificates-v2"
Matrix = list[list[Fraction]]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _matrix(raw: list[list[str]]) -> Matrix:
    matrix = [[Fraction(entry) for entry in row] for row in raw]
    if not matrix or any(len(row) != len(matrix) for row in matrix):
        raise ValueError("matrix must be nonempty and square")
    return matrix


def _vector(raw: list[str], dimension: int) -> list[Fraction]:
    vector = [Fraction(entry) for entry in raw]
    if len(vector) != dimension:
        raise ValueError("declared vector dimension mismatch")
    return vector


def _identity(size: int) -> Matrix:
    return [
        [Fraction(int(row == column)) for column in range(size)]
        for row in range(size)
    ]


def _transpose(matrix: Matrix) -> Matrix:
    return [list(row) for row in zip(*matrix, strict=True)]


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    if len(left[0]) != len(right):
        raise ValueError("incompatible matrix dimensions")
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


def _matvec(matrix: Matrix, vector: list[Fraction]) -> list[Fraction]:
    if len(matrix[0]) != len(vector):
        raise ValueError("incompatible matrix-vector dimensions")
    return [
        sum(
            (matrix[row][column] * vector[column] for column in range(len(vector))),
            start=Fraction(0),
        )
        for row in range(len(matrix))
    ]


def _dot(left: list[Fraction], right: list[Fraction]) -> Fraction:
    if len(left) != len(right):
        raise ValueError("incompatible vector dimensions")
    return sum((a * b for a, b in zip(left, right, strict=True)), Fraction(0))


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


def _principal_minors(matrix: Matrix) -> list[Fraction]:
    if matrix != _transpose(matrix):
        raise ValueError("PSD matrix is not symmetric")
    minors: list[Fraction] = []
    for order in range(1, len(matrix) + 1):
        for indices in itertools.combinations(range(len(matrix)), order):
            principal = [[matrix[i][j] for j in indices] for i in indices]
            minors.append(_determinant(principal))
    return minors


def _verify_instance(instance: dict[str, Any]) -> dict[str, Any]:
    dimension = int(instance["dimension"])
    hessian = _matrix(instance["hessian"])
    basis = _matrix(instance["orthogonal_eigenbasis"])
    spectrum = [Fraction(value) for value in instance["eigenvalues"]]
    alpha = Fraction(instance["step_size"])
    tolerance_squared = Fraction(instance["tolerance_squared"])
    shift_calls = int(instance["candidate_shift_calls"])
    cost = Fraction(instance["cost_exact_units"])
    minimum_saved = int(instance["minimum_saved_calls"])
    identity = _identity(dimension)
    current = _vector(instance["current_displacement"], dimension)
    candidate = _vector(instance["candidate_displacement"], dimension)

    if any(len(matrix) != dimension for matrix in (hessian, basis)) or len(
        spectrum
    ) != dimension:
        raise ValueError("declared dimension mismatch")
    if _multiply(_transpose(basis), basis) != identity:
        raise ValueError("eigenbasis is not exactly orthogonal")
    reconstructed_hessian = _multiply(
        _multiply(basis, _diagonal(spectrum)), _transpose(basis)
    )
    if hessian != reconstructed_hessian or hessian != _transpose(hessian):
        raise ValueError("Hessian spectral decomposition is not exact")
    if not all(value > 0 and alpha * value < 2 for value in spectrum):
        raise ValueError("gradient iteration is not an exact contraction")
    if tolerance_squared <= 0 or cost < 0 or minimum_saved < 0:
        raise ValueError("invalid tolerance, cost, or saving requirement")
    if shift_calls < minimum_saved or cost > shift_calls:
        raise ValueError("claimed accepted branch does not pay its requirements")
    current_norm_squared = _dot(current, current)
    if current_norm_squared != 1:
        raise ValueError("current displacement does not have exact unit norm")
    if Fraction(instance["current_norm_squared"]) != current_norm_squared:
        raise ValueError("recorded current norm is inconsistent")

    step = _subtract(identity, _scale(alpha, hessian))
    expected_candidate = _matvec(_power(step, shift_calls), current)
    if candidate != expected_candidate:
        raise ValueError("candidate does not satisfy the exact shift identity")
    certificates = instance["residual_dual_certificates"]
    if [item["iteration"] for item in certificates] != list(range(shift_calls)):
        raise ValueError("premature-stopping certificates are incomplete")
    verified_minors = 0
    minimum_strict_gap: Fraction | None = None
    for certificate in certificates:
        iteration = int(certificate["iteration"])
        iterate_map = _power(step, iteration)
        expected_objective = _multiply(
            _multiply(_transpose(iterate_map), _multiply(hessian, hessian)),
            iterate_map,
        )
        primal = certificate["primal"]
        objective = _matrix(primal["objective_matrix"])
        normalization = _matrix(primal["normalization_matrix"])
        normalization_rhs = Fraction(primal["normalization_rhs"])
        if objective != expected_objective:
            raise ValueError("residual objective matrix is not generated by the transcript")
        if normalization != identity or normalization_rhs != 1:
            raise ValueError("unexpected primal normalization")

        dual = certificate["dual"]
        multiplier = Fraction(dual["normalization_multiplier"])
        lower_bound = Fraction(dual["certified_lower_bound"])
        slack = _matrix(dual["slack_matrix"])
        expected_slack = _subtract(objective, _scale(multiplier, normalization))
        if slack != expected_slack:
            raise ValueError("dual stationarity identity fails")
        minors = _principal_minors(slack)
        if any(value < 0 for value in minors):
            raise ValueError("dual slack is not positive semidefinite")
        if Fraction(certificate["minimum_principal_minor"]) != min(minors):
            raise ValueError("recorded minimum principal minor is inconsistent")
        verified_minors += len(minors)
        if lower_bound != multiplier * normalization_rhs:
            raise ValueError("dual objective is inconsistent")
        strict_gap = lower_bound - tolerance_squared
        if strict_gap <= 0:
            raise ValueError("dual bound does not exclude premature termination")
        if Fraction(certificate["strict_gap_over_tolerance_squared"]) != strict_gap:
            raise ValueError("recorded strict gap is inconsistent")
        minimum_strict_gap = (
            strict_gap
            if minimum_strict_gap is None
            else min(minimum_strict_gap, strict_gap)
        )
        witness_residual = _dot(current, _matvec(objective, current))
        if witness_residual <= tolerance_squared:
            raise ValueError("stored witness stops before the claimed shift")

    if not instance["claimed_acceptance"]:
        raise ValueError("certificate bundle is not marked as accepted")
    if int(instance["claimed_exact_call_saving"]) != shift_calls:
        raise ValueError("claimed call saving is inconsistent with the shift identity")
    return {
        "id": instance["id"],
        "verified_dual_certificates": len(certificates),
        "verified_principal_minors": verified_minors,
        "minimum_strict_gap": str(minimum_strict_gap),
        "certified_call_saving": shift_calls,
        "certified_cost_slack": str(Fraction(shift_calls) - cost),
        "verified_current_norm_squared": str(current_norm_squared),
        "verified_shift_identity": True,
    }


def verify_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError("unknown certificate schema")
    recorded_hash = payload.pop("payload_sha256")
    computed_hash = sha256(_canonical(payload)).hexdigest()
    if recorded_hash != computed_hash:
        raise ValueError("certificate payload hash mismatch")
    results = [_verify_instance(instance) for instance in payload["instances"]]
    if len(results) != payload["declaration"]["instance_count"]:
        raise ValueError("instance count mismatch")
    certificate_count = sum(item["verified_dual_certificates"] for item in results)
    if certificate_count != payload["declaration"]["certificate_count"]:
        raise ValueError("certificate count mismatch")
    return {
        "verified": True,
        "payload_sha256": recorded_hash,
        "instance_count": len(results),
        "certificate_count": certificate_count,
        "principal_minor_count": sum(
            item["verified_principal_minors"] for item in results
        ),
        "instances": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify_payload(args.certificate)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "VERIFIED: "
            f"{result['instance_count']} instances, "
            f"{result['certificate_count']} rational SDP dual certificates, "
            f"{result['principal_minor_count']} exact principal minors"
        )


if __name__ == "__main__":
    main()
