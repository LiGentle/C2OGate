#!/usr/bin/env python3
"""Deterministic exact differential fuzzing of producer and second consumer."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import random
import sys
from typing import Any

import sympy as sp


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT))

import generate_full_class_joint_only_pep_dual_certificate as producer  # noqa: E402
from tools.verify_h6_sympy_independent import _build_constraints  # noqa: E402


OUTPUT = ROOT / "results" / "consumer_differential_fuzz.json"
SCHEMA = "c2o-consumer-differential-fuzz-v1"
HORIZON = 6
BAD_CELLS = [
    (baseline, candidate)
    for baseline in range(HORIZON + 1)
    for candidate in range(HORIZON + 1)
    if candidate >= baseline
]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sympy_fraction(value: Fraction) -> sp.Rational:
    return sp.Rational(value.numerator, value.denominator)


def _compare_rows(producer_rows: list[Any], consumer_rows: list[Any]) -> int:
    if [row.name for row in producer_rows] != [row.name for row in consumer_rows]:
        raise RuntimeError("constraint names or order differ")
    comparisons = 0
    for left, right in zip(producer_rows, consumer_rows, strict=True):
        if _sympy_fraction(left.rhs) != right.rhs:
            raise RuntimeError(f"RHS mismatch for {left.name}")
        if _sympy_fraction(left.margin) != right.margin:
            raise RuntimeError(f"margin mismatch for {left.name}")
        if tuple(_sympy_fraction(value) for value in left.values) != right.values:
            raise RuntimeError(f"function-value row mismatch for {left.name}")
        matrix = sp.Matrix(
            [[_sympy_fraction(value) for value in row] for row in left.matrix]
        )
        if matrix != right.matrix:
            raise RuntimeError(f"Gram row mismatch for {left.name}")
        comparisons += len(left.values) + len(left.matrix) ** 2 + 2
    return comparisons


def main() -> None:
    rng = random.Random(20260816)
    rows = []
    total_comparisons = 0
    for case in range(32):
        parameters = {
            "strong_convexity": rng.choice(
                [Fraction(1, 4), Fraction(3, 10), Fraction(2, 5)]
            ),
            "smoothness": Fraction(1),
            "step_size": rng.choice([Fraction(4, 5), Fraction(1)]),
            "proposal_step": rng.choice([Fraction(1), Fraction(11, 10)]),
            "proposal_norm_lower": rng.choice(
                [Fraction(1, 2), Fraction(27, 50)]
            ),
            "proposal_norm_upper": rng.choice(
                [Fraction(14, 25), Fraction(3, 5)]
            ),
            "contract_radius": rng.choice(
                [Fraction(1, 200), Fraction(1, 100), Fraction(3, 200)]
            ),
            "initial_distance_upper": rng.choice(
                [Fraction(3, 2), Fraction(9, 5), Fraction(2)]
            ),
            "tolerance": rng.choice(
                [Fraction(1, 4), Fraction(7, 25), Fraction(3, 10)]
            ),
            "derived_trace_bound": Fraction(100),
        }
        if parameters["proposal_norm_lower"] > parameters["proposal_norm_upper"]:
            raise RuntimeError("invalid fuzz proposal band")
        cell = rng.choice(BAD_CELLS)
        producer.HORIZON = HORIZON
        producer.BAD_CELLS = BAD_CELLS
        producer.PARAMETERS = parameters
        _, p_ineq, p_eq, _, _ = producer._build_problem(
            cell, **producer._problem_kwargs()
        )
        serialized = {key: str(value) for key, value in parameters.items()}
        s_ineq, s_eq = _build_constraints(cell, serialized)
        comparisons = _compare_rows(p_ineq, s_ineq) + _compare_rows(p_eq, s_eq)
        total_comparisons += comparisons
        rows.append(
            {
                "case": case,
                "cell": list(cell),
                "parameters": serialized,
                "constraint_count": len(p_ineq) + len(p_eq),
                "exact_scalar_comparisons": comparisons,
            }
        )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "seed": 20260816,
        "case_count": len(rows),
        "exact_scalar_comparisons": total_comparisons,
        "scope": (
            "exact coefficient equality between the CVXPY producer builder and "
            "the nonsharing SymPy consumer over randomized legal rational tuples"
        ),
        "rows": rows,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "VERIFIED: producer/consumer differential fuzz, "
        f"{len(rows)} cases, {total_comparisons} exact scalar comparisons"
    )


if __name__ == "__main__":
    main()
