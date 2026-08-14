#!/usr/bin/env python3
"""Independent exact verifier for the nonlinear joint-PEP acceptance."""

from __future__ import annotations

import argparse
from decimal import Decimal, getcontext
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


SCHEMA = "c2o-nonlinear-joint-pep-acceptance-v1"


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


def _tanh(value: Decimal) -> Decimal:
    exponential = (Decimal(2) * value).exp()
    return (exponential - 1) / (exponential + 1)


def _gradient(value: Decimal) -> Decimal:
    return Decimal(9) * value / Decimal(10) + _tanh(value) / Decimal(10)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_payload(
    payload: dict[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    recorded_hash = payload.get("payload_sha256")
    unsigned = dict(payload)
    unsigned.pop("payload_sha256", None)
    _require(recorded_hash == sha256(_canonical(unsigned)).hexdigest(), "payload hash")
    _require(payload.get("schema") == SCHEMA, "schema")

    if root is not None:
        environment = payload["environment"]
        _require(
            environment["runner_sha256"]
            == _file_hash(
                root / "experiments" / "run_nonlinear_joint_pep_acceptance.py"
            ),
            "runner hash",
        )
        _require(
            environment["verifier_sha256"] == _file_hash(Path(__file__)),
            "verifier hash",
        )
        for relative, expected in environment["source_sha256"].items():
            _require(
                _file_hash(root / relative) == expected, f"source hash: {relative}"
            )

    parameters = payload["parameters"]
    mu = Fraction(parameters["strong_convexity"])
    smoothness = Fraction(parameters["smoothness"])
    tolerance = Fraction(parameters["tolerance"])
    residual = Fraction(parameters["proposal_residual_upper"])
    proposal_lower = Fraction(parameters["proposal_norm_lower"])
    proposal_upper = Fraction(parameters["proposal_norm_upper"])
    cost = Fraction(parameters["cost_exact_units"])
    minimum_saved_calls = int(parameters["minimum_saved_calls"])
    horizon = int(parameters["horizon"])
    _require(mu == Fraction(9, 10) and smoothness == 1, "class constants")
    _require(Fraction(parameters["step_size"]) == 1, "step size")
    _require(0 < residual < proposal_lower <= proposal_upper, "proposal envelope")

    certificate = payload["exact_certificate"]
    gradient_lower = proposal_lower - residual
    gradient_upper = proposal_upper + residual
    contraction = (smoothness - mu) / smoothness
    baseline_one_upper = smoothness * contraction * gradient_upper / mu
    candidate_upper = baseline_one_upper + smoothness * residual
    _require(
        Fraction(certificate["current_gradient_lower"]) == gradient_lower, "g lower"
    )
    _require(
        Fraction(certificate["current_gradient_upper"]) == gradient_upper, "g upper"
    )
    _require(
        Fraction(certificate["gradient_step_contraction"]) == contraction, "contraction"
    )
    _require(
        Fraction(certificate["baseline_gradient_after_one_upper"])
        == baseline_one_upper,
        "baseline terminal bound",
    )
    _require(
        Fraction(certificate["candidate_gradient_upper"]) == candidate_upper,
        "candidate terminal bound",
    )
    _require(gradient_lower > tolerance, "baseline must survive at k=0")
    _require(baseline_one_upper < tolerance, "baseline must stop at k=1")
    _require(candidate_upper < tolerance, "candidate must stop at k=0")
    _require(certificate["strict_pair"] == [1, 0], "exact stopping pair")

    expected_bad = [
        [r, s]
        for r in range(horizon + 1)
        for s in range(horizon + 1)
        if Fraction(s - r) + max(Fraction(minimum_saved_calls), cost) > 0
    ]
    _require(certificate["cost_violating_cells"] == expected_bad, "bad-cell list")
    _require(
        certificate["excluded_cost_violating_cell_count"] == len(expected_bad),
        "bad-cell count",
    )
    _require([1, 0] not in expected_bad, "certified pair must be cost-safe")

    getcontext().prec = 100
    actual = payload["actual_instance"]
    x = Decimal(actual["x"])
    gradient_x = _gradient(x)
    candidate = x - gradient_x + Decimal(1) / Decimal(100)
    baseline_one = x - gradient_x
    _require(str(gradient_x) == actual["gradient_x"], "realized current gradient")
    _require(str(candidate) == actual["candidate_y"], "realized candidate")
    _require(str(_gradient(candidate)) == actual["gradient_y"], "candidate gradient")
    _require(str(baseline_one) == actual["baseline_x_one"], "baseline step")
    _require(
        str(_gradient(baseline_one)) == actual["gradient_x_one"], "baseline gradient"
    )
    proposal_norm = abs(candidate - x)
    _require(
        Decimal(proposal_lower.numerator) / Decimal(proposal_lower.denominator)
        <= proposal_norm,
        "proposal lower envelope",
    )
    _require(
        proposal_norm
        <= Decimal(proposal_upper.numerator) / Decimal(proposal_upper.denominator),
        "proposal upper envelope",
    )
    decimal_tolerance = Decimal(tolerance.numerator) / Decimal(tolerance.denominator)
    _require(abs(gradient_x) > decimal_tolerance, "realized baseline survival")
    _require(abs(_gradient(baseline_one)) < decimal_tolerance, "realized baseline stop")
    _require(abs(_gradient(candidate)) < decimal_tolerance, "realized candidate stop")
    _require(
        actual["baseline_calls"] == 1 and actual["hybrid_calls"] == 0, "realized calls"
    )
    third_derivative_at_one = (
        -(Decimal(1) - _tanh(Decimal(1)) ** 2) * _tanh(Decimal(1)) / Decimal(5)
    )
    _require(third_derivative_at_one < 0, "nonquadratic witness")

    enumeration = payload["pep_enumeration"]
    _require(enumeration["cell_count"] == (horizon + 1) ** 2, "cell count")
    _require(enumeration["positive_margin_pairs"] == [[1, 0]], "PEP positive cells")
    _require(len(enumeration["cells"]) == (horizon + 1) ** 2, "cell records")
    gate = payload["gate"]
    _require(gate["joint_accept"] is True, "joint acceptance")
    _require(gate["worst_joint_call_difference"] == -1, "joint difference")
    _require(Fraction(str(gate["certificate_value"])) <= 0, "gate certificate")
    _require(Fraction(str(gate["declared_all_in_cost_ratio"])) == cost, "cost ratio")
    return {
        "payload_sha256": recorded_hash,
        "bad_cells_excluded": len(expected_bad),
        "strict_pair": [1, 0],
        "joint_accept": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    result = verify_payload(payload, root=args.root)
    print(
        "VERIFIED: nonquadratic joint PEP acceptance, exact pair (1,0), "
        f"{result['bad_cells_excluded']} cost-violating cells excluded"
    )


if __name__ == "__main__":
    main()
