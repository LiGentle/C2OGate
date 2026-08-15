#!/usr/bin/env python3
"""Standard-library verifier for the exact joint-only shift certificate."""

from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


SCHEMA = "c2o-joint-only-shift-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _stopping_time(curvature: Fraction, gradient: Fraction, tolerance: Fraction) -> int:
    calls = 0
    while abs(gradient) > tolerance:
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
    _require(declaration["shared_transcript"] == "x=0, f(x)=0, grad f(x)=4/5", "transcript")
    _require(declaration["proposal"] == "y=x-grad f(x)=-4/5", "proposal")
    gradient = Fraction(4, 5)
    tolerance = Fraction(declaration["tolerance"])
    mu = Fraction(1, 10)
    smoothness = Fraction(1)
    curvatures = (mu, smoothness)
    pairs = []
    for witness, curvature in zip(payload["witnesses"], curvatures, strict=True):
        _require(Fraction(witness["curvature"]) == curvature, "curvature")
        baseline = _stopping_time(curvature, gradient, tolerance)
        hybrid = _stopping_time(curvature, (1 - curvature) * gradient, tolerance)
        _require(witness["baseline_calls"] == baseline, "baseline calls")
        _require(witness["hybrid_calls"] == hybrid, "hybrid calls")
        _require(hybrid == baseline - 1, "shift identity")
        pairs.append([baseline, hybrid])
    _require(pairs == declaration["attainable_pairs"] == [[3, 2], [1, 0]], "pairs")
    _require(abs(gradient / mu) <= Fraction(declaration["initial_distance_upper"]), "distance bound")
    residual_bound = smoothness * Fraction(declaration["candidate_distance_upper"])
    horizon = 0
    while residual_bound > tolerance:
        residual_bound *= 1 - mu / smoothness
        horizon += 1
    _require(horizon == declaration["formula_horizon"] == 26, "formula horizon")
    threshold = max(
        Fraction(declaration["cost_exact_units"]),
        Fraction(declaration["minimum_saved_calls"]),
    )
    worst_joint = max(hybrid - baseline for baseline, hybrid in pairs)
    baseline_lower = min(baseline for baseline, _ in pairs)
    hybrid_upper = max(hybrid for _, hybrid in pairs)
    rectangle = hybrid_upper - baseline_lower
    certificate = payload["certificate"]
    _require(worst_joint == certificate["worst_joint_call_difference"] == -1, "joint difference")
    _require(worst_joint + threshold == Fraction(certificate["joint_certificate_value"]) == 0, "joint value")
    _require(baseline_lower == certificate["baseline_lower_calls"] == 1, "baseline lower")
    _require(hybrid_upper == certificate["hybrid_upper_calls"] == 2, "hybrid upper")
    _require(rectangle == certificate["rectangle_call_difference"] == 1, "rectangle difference")
    _require(rectangle + threshold == Fraction(certificate["rectangle_certificate_value"]) == 2, "rectangle value")
    _require(certificate["joint_accept"] and not certificate["rectangle_accept"], "decisions")
    if root is not None:
        environment = payload["environment"]
        _require(
            environment["generator_sha256"]
            == _file_hash(root / "experiments" / "generate_joint_only_shift_certificate.py"),
            "generator hash",
        )
        _require(environment["verifier_sha256"] == _file_hash(Path(__file__)), "verifier hash")
    return {
        "payload_sha256": recorded_hash,
        "pairs": pairs,
        "formula_horizon": horizon,
        "joint_accept": True,
        "rectangle_accept": False,
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
        "VERIFIED: exact joint-only acceptance, rectangle rejection, "
        f"pairs={result['pairs']}, formula horizon={result['formula_horizon']}"
    )


if __name__ == "__main__":
    main()
