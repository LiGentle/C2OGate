#!/usr/bin/env python3
"""Independent exact verifier for the nonlinear joint-PEP acceptance."""

from __future__ import annotations

import argparse
from decimal import Decimal, getcontext
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
    verify_payload as verify_generic_dual,
)


SCHEMA = "c2o-nonlinear-joint-pep-acceptance-v4"


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


def _norm(values: tuple[Decimal, ...]) -> Decimal:
    return sum((value * value for value in values), Decimal(0)).sqrt()


def _certified_horizon(
    contraction: Fraction,
    smoothness: Fraction,
    distance: Fraction,
    tolerance: Fraction,
) -> int:
    horizon = 0
    residual_bound = smoothness * distance
    while residual_bound > tolerance:
        residual_bound *= contraction
        horizon += 1
    return horizon


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
        generic_dual_path = root / "certificates" / "generic_nonquadratic_pep_dual.json"
        _require(
            environment["generic_dual_file_sha256"] == _file_hash(generic_dual_path),
            "generic dual file hash",
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
    natural_horizon = _certified_horizon(
        (smoothness - mu) / smoothness,
        smoothness,
        Fraction(parameters["initial_distance_upper"]) + proposal_upper,
        tolerance,
    )
    _require(natural_horizon == 2, "formula-derived horizon")
    _require(int(parameters["natural_horizon"]) == natural_horizon, "stored horizon")
    _require(int(parameters["audit_padding"]) == 1, "audit padding")
    _require(horizon == natural_horizon + 1 == 3, "padded horizon")

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
    _require(certificate["analytic_excluded_cells"] == [], "analytic exclusion ledger")
    _require(
        certificate["generic_dual_excluded_cells"] == expected_bad,
        "generic dual cells",
    )
    _require(
        certificate["generic_dual_certificate_count"] == len(expected_bad),
        "generic dual count",
    )
    _require(
        certificate["generic_dual_positive_leading_minors"] == 10 * len(expected_bad),
        "generic dual minors",
    )
    if root is not None:
        generic_payload = json.loads(
            (root / "certificates" / "generic_nonquadratic_pep_dual.json").read_text(
                encoding="utf-8"
            )
        )
        generic_result = verify_generic_dual(generic_payload, root=root)
        _require(generic_result["cells"] == expected_bad, "generic dual verified cells")
        _require(
            generic_result["certificate_count"] == len(expected_bad),
            "generic dual verified count",
        )
        _require(
            generic_result["payload_sha256"]
            == certificate["generic_dual_payload_sha256"],
            "generic dual payload binding",
        )

    getcontext().prec = 100
    actual = payload["actual_instance"]
    _require(actual["dimension"] == 2, "realized dimension")
    x = (Decimal("0.9"), Decimal("0.4"))
    residual_vector = (Decimal("0.003"), Decimal("-0.004"))
    gradient_x = tuple(_gradient(value) for value in x)
    baseline_one = tuple(
        value - gradient
        for value, gradient in zip(x, gradient_x, strict=True)
    )
    candidate = tuple(
        value + perturbation
        for value, perturbation in zip(baseline_one, residual_vector, strict=True)
    )
    gradient_candidate = tuple(_gradient(value) for value in candidate)
    gradient_baseline_one = tuple(_gradient(value) for value in baseline_one)
    _require([str(value) for value in x] == actual["x"], "realized current point")
    _require(
        [str(value) for value in gradient_x] == actual["gradient_x"],
        "realized current gradient",
    )
    _require([str(value) for value in candidate] == actual["candidate_y"], "candidate")
    _require(
        [str(value) for value in residual_vector] == actual["candidate_residual"],
        "candidate residual",
    )
    _require(
        [str(value) for value in gradient_candidate] == actual["gradient_y"],
        "candidate gradient",
    )
    _require(
        [str(value) for value in baseline_one] == actual["baseline_x_one"],
        "baseline step",
    )
    _require(
        [str(value) for value in gradient_baseline_one]
        == actual["gradient_x_one"],
        "baseline gradient",
    )
    proposal = tuple(
        candidate_value - current_value
        for candidate_value, current_value in zip(candidate, x, strict=True)
    )
    proposal_norm = _norm(proposal)
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
    _require(_norm(gradient_x) > decimal_tolerance, "realized baseline survival")
    _require(
        _norm(gradient_baseline_one) < decimal_tolerance,
        "realized baseline stop",
    )
    _require(_norm(gradient_candidate) < decimal_tolerance, "realized candidate stop")
    _require(_norm(residual_vector) == Decimal("0.005"), "realized residual norm")
    _require(
        str(_norm(residual_vector)) == actual["candidate_residual_norm"],
        "stored residual norm",
    )
    _require(str(proposal_norm) == actual["proposal_norm"], "stored proposal norm")
    span_determinant = x[0] * baseline_one[1] - x[1] * baseline_one[0]
    _require(span_determinant < Decimal("-0.005"), "two-dimensional span")
    _require(
        str(span_determinant) == actual["trajectory_span_determinant"],
        "stored span determinant",
    )
    _require(
        actual["baseline_calls"] == 1 and actual["hybrid_calls"] == 0, "realized calls"
    )
    third_derivative_at_x = (
        -(Decimal(1) - _tanh(x[0]) ** 2) * _tanh(x[0]) / Decimal(5)
    )
    _require(third_derivative_at_x < 0, "nonquadratic witness")

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
        "dimension": 2,
        "natural_horizon": natural_horizon,
        "audit_horizon": horizon,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    result = verify_payload(payload, root=args.root)
    print(
        "VERIFIED: two-dimensional nonquadratic joint PEP acceptance, "
        "natural H0=2, padded H=3, exact pair (1,0), "
        f"{result['bad_cells_excluded']} cost-violating cells excluded"
    )


if __name__ == "__main__":
    main()
