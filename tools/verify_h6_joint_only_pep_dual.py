#!/usr/bin/env python3
"""Exact stdlib verifier for the natural-H=6 joint-only PEP suite."""

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

import tools.verify_full_class_joint_only_pep_dual as base  # noqa: E402


SCHEMA = "c2o-h6-joint-only-pep-dual-v1"
HORIZON = 6
BAD_CELLS = [
    (baseline, candidate)
    for baseline in range(HORIZON + 1)
    for candidate in range(HORIZON + 1)
    if candidate >= baseline
]
PARAMETERS = {
    "strong_convexity": Fraction(3, 10),
    "smoothness": Fraction(1),
    "step_size": Fraction(1),
    "proposal_step": Fraction(11, 10),
    "proposal_norm_lower": Fraction(27, 50),
    "proposal_norm_upper": Fraction(14, 25),
    "contract_radius": Fraction(1, 100),
    "initial_distance_upper": Fraction(9, 5),
    "tolerance": Fraction(7, 25),
    "derived_trace_bound": Fraction(66),
}


def _configure_base() -> None:
    base.HORIZON = HORIZON
    base.BAD_CELLS = BAD_CELLS
    base.PARAMETERS = PARAMETERS


def _stopping_time(curvature: Fraction, gradient: Fraction) -> int:
    calls = 0
    while abs(gradient) > PARAMETERS["tolerance"]:
        gradient *= 1 - curvature
        calls += 1
    return calls


def _verify_certificate(certificate: dict[str, Any]) -> tuple[Fraction, int]:
    cell = tuple(certificate["cell"])
    inequalities, equalities = base._build_constraints(cell)
    atom_count = 2 * (HORIZON + 1) + 2
    value_count = 2 * (HORIZON + 1) + 1
    primal = certificate["primal"]
    base._require(primal["gram_order"] == atom_count, "Gram order")
    base._require(
        primal["function_value_count"] == value_count, "function-value count"
    )
    base._require(
        primal["inequality_count"] == len(inequalities), "inequality count"
    )
    base._require(primal["equality_count"] == len(equalities), "equality count")
    dual = certificate["dual"]
    raw_lambdas = dual["inequality_multipliers"]
    raw_nus = dual["equality_multipliers"]
    base._require(
        set(raw_lambdas) <= {item.name for item in inequalities},
        "unknown inequality multiplier",
    )
    base._require(
        set(raw_nus) <= {item.name for item in equalities},
        "unknown equality multiplier",
    )
    lambdas = [
        Fraction(raw_lambdas.get(item.name, "0")) for item in inequalities
    ]
    nus = [Fraction(raw_nus.get(item.name, "0")) for item in equalities]
    base._require(all(value >= 0 for value in lambdas), "dual multiplier sign")
    stationarity = [Fraction(0) for _ in range(value_count + 1)]
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    for multiplier, item in zip(nus, equalities, strict=True):
        for index, coefficient in enumerate([*item.values, item.margin]):
            stationarity[index] += multiplier * coefficient
    base._require(
        stationarity == [*([Fraction(0)] * value_count), Fraction(1)],
        "dual stationarity",
    )
    slack = base._zero_matrix(atom_count)
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        slack = base._matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    for multiplier, item in zip(nus, equalities, strict=True):
        slack = base._matrix_add((Fraction(1), slack), (multiplier, item.matrix))
    pivots = base._positive_ldl_pivots(slack)
    base._require(
        dual["positive_ldl_pivot_count"] == len(pivots) == atom_count,
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
    base._require(
        objective == Fraction(dual["certified_upper_bound"]), "dual objective"
    )
    base._require(objective < 0, "strict bad-cell exclusion")
    return objective, len(pivots)


def verify_payload(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    _configure_base()
    recorded_hash = payload.get("payload_sha256")
    unsigned = dict(payload)
    unsigned.pop("payload_sha256", None)
    base._require(
        recorded_hash == sha256(base._canonical(unsigned)).hexdigest(), "payload hash"
    )
    base._require(payload.get("schema") == SCHEMA, "schema")
    declaration = payload["declaration"]
    base._require(declaration["cells"] == [list(cell) for cell in BAD_CELLS], "cells")
    base._require(declaration["horizon"] == HORIZON, "horizon")
    base._require(
        declaration["function_class"]
        == "full infinite class F_{3/10,1} consistent with the transcript",
        "function class",
    )
    base._require(
        payload["parameters"]
        == {key: str(value) for key, value in PARAMETERS.items()},
        "parameters",
    )

    q = Fraction(7, 10)
    distance = PARAMETERS["initial_distance_upper"] + PARAMETERS[
        "proposal_norm_upper"
    ]
    tolerance = PARAMETERS["tolerance"]
    base._require(distance * q**5 > tolerance >= distance * q**6, "natural horizon")
    trace_consequence = (
        7 * PARAMETERS["initial_distance_upper"] ** 2
        + 7 * distance**2
        + PARAMETERS["initial_distance_upper"] ** 2
        + PARAMETERS["proposal_norm_upper"] ** 2
    )
    base._require(trace_consequence < PARAMETERS["derived_trace_bound"], "trace bound")
    base._require(tolerance**2 <= distance**2, "margin upper redundancy")

    expected_witnesses = (
        (Fraction(1), Fraction(1, 2), -Fraction(11, 20), (1, 0)),
        (Fraction(3, 10), Fraction(1, 2), -Fraction(27, 50), (2, 1)),
    )
    pairs: list[tuple[int, int]] = []
    for witness, expected in zip(payload["witnesses"], expected_witnesses, strict=True):
        curvature, gradient, candidate, expected_pair = expected
        base._require(Fraction(witness["curvature"]) == curvature, "witness curvature")
        base._require(Fraction(witness["current_gradient"]) == gradient, "witness gradient")
        base._require(Fraction(witness["candidate"]) == candidate, "witness candidate")
        base._require(
            abs(gradient / curvature)
            <= PARAMETERS["initial_distance_upper"],
            "witness distance",
        )
        base._require(
            PARAMETERS["proposal_norm_lower"]
            <= abs(candidate)
            <= PARAMETERS["proposal_norm_upper"],
            "witness proposal norm",
        )
        residual = candidate + PARAMETERS["proposal_step"] * gradient
        base._require(abs(residual) <= PARAMETERS["contract_radius"], "witness contract")
        base._require(Fraction(witness["proposal_residual"]) == residual, "stored residual")
        candidate_gradient = gradient + curvature * candidate
        pair = (
            _stopping_time(curvature, gradient),
            _stopping_time(curvature, candidate_gradient),
        )
        base._require(pair == expected_pair, "witness stopping pair")
        base._require(witness["baseline_calls"] == pair[0], "stored baseline calls")
        base._require(witness["candidate_calls"] == pair[1], "stored candidate calls")
        pairs.append(pair)

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
    base._require(gradient_lower == Fraction(marginal["current_gradient_lower"]), "gradient lower")
    base._require(gradient_upper == Fraction(marginal["current_gradient_upper"]), "gradient upper")
    base._require(proposal_q == Fraction(marginal["proposal_step_contraction"]), "proposal contraction")
    base._require(
        candidate_gradient_upper == Fraction(marginal["candidate_gradient_upper"]),
        "candidate gradient upper",
    )
    base._require(
        one_step_upper
        == Fraction(marginal["one_step_candidate_gradient_upper"])
        < tolerance
        < gradient_lower,
        "exact marginal call bounds",
    )
    base._require(marginal["baseline_lower_calls"] == 1, "baseline marginal")
    base._require(marginal["candidate_upper_calls"] == 1, "candidate marginal")
    base._require(Fraction(marginal["rectangle_certificate_value"]) == 1, "rectangle value")

    certificates = payload["certificates"]
    base._require(
        [item["cell"] for item in certificates] == [list(cell) for cell in BAD_CELLS],
        "certificate order",
    )
    verified = [_verify_certificate(item) for item in certificates]
    bounds = [bound for bound, _ in verified]
    pivots = sum(count for _, count in verified)
    summary = payload["summary"]
    base._require(summary["certificate_count"] == 28, "certificate count")
    base._require(summary["positive_ldl_pivot_count"] == pivots == 448, "pivot count")
    base._require(summary["maximum_gram_order"] == 16, "Gram order")
    base._require(
        Fraction(summary["maximum_certified_upper_bound"]) == max(bounds),
        "maximum upper bound",
    )
    joint = payload["joint_certificate"]
    base._require(joint["worst_call_difference"] == -1, "joint difference")
    base._require(Fraction(joint["certificate_value"]) == 0, "joint value")
    base._require(joint["joint_accept"] and not joint["rectangle_accept"], "decisions")
    if root is not None:
        environment = payload["environment"]
        base._require(
            environment["generator_sha256"]
            == base._file_hash(
                root
                / "experiments"
                / "generate_h6_joint_only_pep_dual_certificate.py"
            ),
            "generator hash",
        )
        base._require(
            environment["verifier_sha256"] == base._file_hash(Path(__file__)),
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
        "VERIFIED: natural-H=6 nonzero-radius joint-only PEP acceptance, "
        f"{result['certificate_count']} bad cells, "
        f"{result['positive_ldl_pivots']} positive LDL pivots, "
        f"witness pairs={result['witness_pairs']}"
    )


if __name__ == "__main__":
    main()
