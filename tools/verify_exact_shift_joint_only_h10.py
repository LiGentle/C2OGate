#!/usr/bin/env python3
"""Verify the H=10 exact-shift joint-only certificate using only stdlib."""

from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path


SCHEMA = "c2o-exact-shift-joint-only-h10-v1"
PARAMETERS = {
    "strong_convexity": Fraction(1, 2),
    "smoothness": Fraction(1),
    "step_size": Fraction(1),
    "initial_distance_upper": Fraction(1),
    "initial_gradient_norm": Fraction(4, 5),
    "tolerance": Fraction(1, 1024),
    "cost_exact_units": Fraction(2, 5),
    "minimum_saved_calls": Fraction(1),
}


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError(f"verification failed: {label}")


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
    factor = 1 - PARAMETERS["step_size"] * curvature
    calls = 0
    while abs(gradient) > PARAMETERS["tolerance"]:
        gradient *= factor
        calls += 1
    return calls


def verify(payload_path: Path, root: Path) -> None:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    _require(payload["schema"] == SCHEMA, "schema")
    _require(
        payload["payload_sha256"] == sha256(_canonical(payload)).hexdigest(),
        "payload hash",
    )
    declared = {key: Fraction(value) for key, value in payload["parameters"].items()}
    _require(declared == PARAMETERS, "exact parameter tuple")
    environment = payload["environment"]
    _require(
        environment["generator_sha256"]
        == _file_hash(root / "experiments" / "generate_exact_shift_joint_only_h10.py"),
        "generator hash",
    )
    _require(environment["verifier_sha256"] == _file_hash(Path(__file__)), "verifier hash")

    q = max(
        abs(1 - PARAMETERS["step_size"] * PARAMETERS["strong_convexity"]),
        abs(1 - PARAMETERS["step_size"] * PARAMETERS["smoothness"]),
    )
    horizon = 0
    while PARAMETERS["smoothness"] * PARAMETERS["initial_distance_upper"] * q**horizon > PARAMETERS["tolerance"]:
        horizon += 1
    _require(horizon == 10, "branch-specific horizon")
    combinatorics = payload["combinatorics"]
    _require(combinatorics["horizon"] == horizon, "stored horizon")
    _require(combinatorics["candidate_horizon"] == horizon - 1, "candidate horizon")
    shift_line = [(r, r - 1) for r in range(1, horizon + 1)]
    _require(combinatorics["shift_line_cells"] == [list(cell) for cell in shift_line], "shift line")
    nominal = (horizon + 1) ** 2
    bad = sum(s >= r for r in range(horizon + 1) for s in range(horizon + 1))
    _require(combinatorics["nominal_joint_cells"] == nominal == 121, "nominal cells")
    _require(combinatorics["structurally_excluded_cells"] == nominal - horizon == 111, "structural exclusions")
    _require(combinatorics["cost_violating_cells"] == bad == 66, "bad-cell count")
    _require(combinatorics["cost_violating_cells_structurally_excluded"] == bad, "bad-cell exclusions")

    _require(PARAMETERS["initial_gradient_norm"] > PARAMETERS["tolerance"], "positive baseline stopping time")
    expected_curvatures = (Fraction(1), Fraction(4, 5))
    expected_pairs = ((1, 0), (5, 4))
    for witness, curvature, pair in zip(payload["witnesses"], expected_curvatures, expected_pairs, strict=True):
        _require(Fraction(witness["curvature"]) == curvature, "witness curvature")
        _require(Fraction(witness["optimum_distance"]) <= PARAMETERS["initial_distance_upper"], "witness distance")
        actual = _stopping_time(curvature)
        _require((actual, actual - 1) == pair, "witness stopping pair")
        _require((witness["baseline_calls"], witness["candidate_calls"]) == pair, "stored witness pair")

    joint = payload["joint_certificate"]
    _require(joint["worst_call_difference"] == -1, "joint call difference")
    _require(Fraction(joint["certificate_value"]) == 0 and joint["accept"] is True, "joint acceptance")
    rectangle = payload["marginal_rectangle"]
    _require(rectangle["baseline_lower_calls"] == 1, "exact baseline lower bound")
    _require(rectangle["candidate_upper_calls_lower_witness"] == 4, "candidate marginal witness")
    _require(Fraction(rectangle["certificate_value_lower_bound"]) == 4, "rectangle lower bound")
    _require(rectangle["accept"] is False, "rectangle rejection")
    print(
        "VERIFIED: full-class joint-only H=10 exact shift, "
        "66/66 bad cells excluded, witnesses (1,0) and (5,4), rectangle >= 4"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    verify(args.payload, args.root.resolve())


if __name__ == "__main__":
    main()
