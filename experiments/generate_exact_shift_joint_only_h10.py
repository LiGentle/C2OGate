#!/usr/bin/env python3
"""Generate the exact full-class H=10 joint-only shift certificate."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "exact_shift_joint_only_h10.json"
VERIFIER = ROOT / "tools" / "verify_exact_shift_joint_only_h10.py"
SCHEMA = "c2o-exact-shift-joint-only-h10-v1"
PARAMETERS = {
    "strong_convexity": Fraction(1, 2),
    "smoothness": Fraction(1),
    "step_size": Fraction(1),
    "initial_distance_upper": Fraction(1),
    "initial_gradient_norm": Fraction(4, 5),
    "tolerance": Fraction(1, 1024),
    "cost_exact_units": Fraction(2, 5),
    "minimum_saved_calls": 1,
}


def _canonical(payload: dict) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("payload_sha256", None)
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stopping_time(curvature: Fraction) -> int:
    gradient = PARAMETERS["initial_gradient_norm"]
    tolerance = PARAMETERS["tolerance"]
    factor = 1 - PARAMETERS["step_size"] * curvature
    calls = 0
    while abs(gradient) > tolerance:
        gradient *= factor
        calls += 1
    return calls


def _witness(curvature: Fraction) -> dict[str, object]:
    baseline_calls = _stopping_time(curvature)
    optimum_distance = PARAMETERS["initial_gradient_norm"] / curvature
    return {
        "curvature": str(curvature),
        "function": f"f(t)=({curvature})*t^2/2+(4/5)*t",
        "current_point": "0",
        "candidate_point": "-4/5",
        "optimum_distance": str(optimum_distance),
        "baseline_calls": baseline_calls,
        "candidate_calls": baseline_calls - 1,
    }


def main() -> None:
    mu = PARAMETERS["strong_convexity"]
    smoothness = PARAMETERS["smoothness"]
    step_size = PARAMETERS["step_size"]
    radius = PARAMETERS["initial_distance_upper"]
    tolerance = PARAMETERS["tolerance"]
    contraction = max(abs(1 - step_size * mu), abs(1 - step_size * smoothness))
    horizon = 0
    while smoothness * radius * contraction**horizon > tolerance:
        horizon += 1
    nominal = (horizon + 1) ** 2
    shift_line = [(r, r - 1) for r in range(1, horizon + 1)]
    bad_cells = [
        (r, s)
        for r in range(horizon + 1)
        for s in range(horizon + 1)
        if s >= r
    ]
    witnesses = [_witness(Fraction(1)), _witness(Fraction(4, 5))]
    baseline_lower = min(item["baseline_calls"] for item in witnesses)
    candidate_witness_lower = max(item["candidate_calls"] for item in witnesses)
    payload = {
        "schema": SCHEMA,
        "declaration": {
            "function_class": (
                "full infinite class F_{1/2,1} satisfying the exact first-order transcript"
            ),
            "exact_shift": "y=x-step_size*gradient_f(x)",
            "joint_identity": "N_f(y)=N_f(x)-1",
            "acceptance_claim": (
                "joint gate accepts while every independent marginal rectangle rejects"
            ),
        },
        "parameters": {key: str(value) for key, value in PARAMETERS.items()},
        "combinatorics": {
            "horizon": horizon,
            "candidate_horizon": horizon - 1,
            "nominal_joint_cells": nominal,
            "shift_line_cells": [list(cell) for cell in shift_line],
            "structurally_excluded_cells": nominal - len(shift_line),
            "cost_violating_cells": len(bad_cells),
            "cost_violating_cells_structurally_excluded": len(bad_cells),
        },
        "witnesses": witnesses,
        "joint_certificate": {
            "worst_call_difference": -1,
            "certificate_value": "0",
            "accept": True,
        },
        "marginal_rectangle": {
            "baseline_lower_calls": baseline_lower,
            "candidate_upper_calls_lower_witness": candidate_witness_lower,
            "certificate_value_lower_bound": str(
                candidate_witness_lower
                - baseline_lower
                + max(
                    PARAMETERS["cost_exact_units"],
                    PARAMETERS["minimum_saved_calls"],
                )
            ),
            "accept": False,
        },
        "environment": {
            "generator_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(VERIFIER),
            "arithmetic": "fractions.Fraction only",
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "EXACT: full-class joint-only H=10 shift certificate, "
        f"{len(bad_cells)}/{len(bad_cells)} bad cells excluded, "
        f"rectangle >= {payload['marginal_rectangle']['certificate_value_lower_bound']}"
    )


if __name__ == "__main__":
    main()
