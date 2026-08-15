#!/usr/bin/env python3
"""Freeze an exact joint-accept/rectangle-reject branch certificate."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "joint_only_shift_certificate.json"
VERIFIER = ROOT / "tools" / "verify_joint_only_shift_certificate.py"
SCHEMA = "c2o-joint-only-shift-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _stopping_time(curvature: Fraction, gradient: Fraction, tolerance: Fraction) -> int:
    calls = 0
    while abs(gradient) > tolerance:
        gradient *= 1 - curvature
        calls += 1
    return calls


def main() -> None:
    gradient = Fraction(4, 5)
    tolerance = Fraction(3, 5)
    curvatures = (Fraction(1, 10), Fraction(1))
    pairs = []
    witnesses = []
    for curvature in curvatures:
        baseline = _stopping_time(curvature, gradient, tolerance)
        hybrid = _stopping_time(
            curvature, (1 - curvature) * gradient, tolerance
        )
        pairs.append([baseline, hybrid])
        witnesses.append(
            {
                "curvature": str(curvature),
                "function": f"f(t)=({curvature})*t^2/2+(4/5)*t",
                "baseline_calls": baseline,
                "hybrid_calls": hybrid,
            }
        )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "function_class": "two-element subset of F_{1/10,1}",
            "shared_transcript": "x=0, f(x)=0, grad f(x)=4/5",
            "proposal": "y=x-grad f(x)=-4/5",
            "tolerance": "3/5",
            "step_size": "1",
            "initial_distance_upper": "8",
            "candidate_distance_upper": "44/5",
            "formula_horizon": 26,
            "cost_exact_units": "2/5",
            "minimum_saved_calls": 1,
            "attainable_pairs": pairs,
            "claim": "joint gate accepts and the independent rectangle rejects",
        },
        "witnesses": witnesses,
        "certificate": {
            "shift_identity": "N_f(y)=N_f(x)-1",
            "worst_joint_call_difference": -1,
            "joint_certificate_value": "0",
            "baseline_lower_calls": min(pair[0] for pair in pairs),
            "hybrid_upper_calls": max(pair[1] for pair in pairs),
            "rectangle_call_difference": max(pair[1] for pair in pairs)
            - min(pair[0] for pair in pairs),
            "rectangle_certificate_value": "2",
            "joint_accept": True,
            "rectangle_accept": False,
        },
        "environment": {
            "generator_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(VERIFIER) if VERIFIER.exists() else None,
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "EXACT: joint-only shift certificate, pairs=(1,0),(3,2), "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
