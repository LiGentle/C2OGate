#!/usr/bin/env python3
"""Sensitivity audit for the frozen ill-conditioned SPX construction."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
OUTPUT = ROOT / "results" / "spx_sensitivity_study.json"
SCHEMA = "c2o-spx-sensitivity-v1"
ROUNDING_SCALE = 10**6
STEP_SIZE = Fraction(17, 84)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.run_real_spx_ill_conditioned_study import (  # noqa: E402
    _fraction_linear,
    _fraction_matrix,
    _leading_minors,
    _solve,
)


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


def _load_rows(chain: Path) -> list[dict[str, float | str]]:
    selected: list[dict[str, float | str]] = []
    with chain.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            try:
                numeric = {
                    key: float(raw[key])
                    for key in ("Knorm", "T", "iv_bs", "bid", "ask", "bid_ask_spread")
                }
            except (TypeError, ValueError):
                continue
            if (
                raw["otm"].lower() == "true"
                and raw["liquidity_flag"] == "liquid"
                and numeric["bid"] > 0.0
                and numeric["ask"] > numeric["bid"]
                and numeric["bid_ask_spread"] <= 0.08
                and 0.75 <= numeric["Knorm"] <= 1.25
                and 0.05 <= numeric["iv_bs"] <= 0.80
                and 0.03 <= numeric["T"] <= 3.0
            ):
                selected.append({**raw, **numeric})
    return selected


def _design(rows: list[dict[str, float | str]]) -> tuple[np.ndarray, np.ndarray]:
    moneyness = np.asarray([(float(row["Knorm"]) - 1.0) / 0.25 for row in rows])
    maturity = np.asarray([float(row["T"]) / 3.0 for row in rows])
    features = np.column_stack(
        [
            np.ones(len(rows)),
            moneyness,
            maturity,
            moneyness**2,
            moneyness * maturity,
            maturity**2,
            moneyness**3,
            moneyness**2 * maturity,
            moneyness * maturity**2,
            maturity**3,
        ]
    )
    centers = features[:, 1:].mean(axis=0)
    features[:, 1:] -= centers
    scales = np.sqrt(np.mean(features[:, 1:] ** 2, axis=0))
    features[:, 1:] /= scales
    targets = np.asarray([float(row["iv_bs"]) for row in rows])
    return (
        np.rint(features * ROUNDING_SCALE).astype(np.int64),
        np.rint(targets * ROUNDING_SCALE).astype(np.int64),
    )


def _calls(matrix: np.ndarray, linear: np.ndarray, start: np.ndarray, tolerance: float) -> int:
    transition = np.eye(len(linear)) - float(STEP_SIZE) * matrix
    gradient = matrix @ start - linear
    for calls in range(200_001):
        if float(gradient @ gradient) <= tolerance:
            return calls
        gradient = transition @ gradient
    raise RuntimeError("sensitivity trajectory exceeded its horizon")


def _curvature_validity(
    exact_hessian: list[list[Fraction]], scalar: Fraction, *, lower: bool
) -> bool:
    matrix = [
        [
            (value - scalar if lower and i == j else scalar - value if not lower and i == j else value if lower else -value)
            for j, value in enumerate(row)
        ]
        for i, row in enumerate(exact_hessian)
    ]
    return all(value > 0 for value in _leading_minors(matrix))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chain",
        type=Path,
        default=WORKSPACE / "data" / "market_data" / "spx_options_2026-08-08.csv",
    )
    args = parser.parse_args()
    rows = _load_rows(args.chain)
    features, targets = _design(rows)
    row_count, dimension = features.shape
    exact_linear = _fraction_linear(features, targets)
    float_linear = np.asarray([float(value) for value in exact_linear])
    records: list[dict[str, Any]] = []
    for ridge in (Fraction(1, 100_000), Fraction(1, 10_000), Fraction(1, 1_000)):
        exact_hessian = _fraction_matrix(features, ridge)
        float_hessian = np.asarray(
            [[float(value) for value in row] for row in exact_hessian]
        )
        initial_gradient_squared = sum(value * value for value in exact_linear)
        for stride in (5, 10, 20):
            sketch = features[::stride]
            candidate = _solve(_fraction_matrix(sketch, ridge), exact_linear)
            float_candidate = np.asarray([float(value) for value in candidate])
            for tolerance_power in (8, 10, 12):
                tolerance = float(initial_gradient_squared / 10**tolerance_power)
                baseline_calls = _calls(
                    float_hessian, float_linear, np.zeros(dimension), tolerance
                )
                hybrid_calls = _calls(
                    float_hessian, float_linear, float_candidate, tolerance
                )
                saved_calls = baseline_calls - hybrid_calls
                exact_gradient_flops = 2.0 * row_count * dimension
                offline_flops = (
                    50.0 * row_count * dimension
                    + 6.0 * row_count * dimension**2
                    + 30.0 * dimension**3
                )
                proposal_flops = 2.0 * len(sketch) * dimension**2 + (2.0 / 3.0) * dimension**3
                verification_flops = 2.0 * (baseline_calls + hybrid_calls) * dimension**2
                nonexact_units = (
                    offline_flops + proposal_flops + verification_flops
                ) / exact_gradient_flops
                total_ratio = (hybrid_calls + nonexact_units) / baseline_calls
                records.append(
                    {
                        "ridge": str(ridge),
                        "sketch_stride": stride,
                        "tolerance_power": tolerance_power,
                        "baseline_calls": baseline_calls,
                        "hybrid_calls": hybrid_calls,
                        "saved_calls": saved_calls,
                        "charged_nonexact_units": nonexact_units,
                        "total_cost_ratio": total_ratio,
                        "cost_gate_accepts": bool(saved_calls >= 1 and total_ratio <= 1.0),
                    }
                )
    base_hessian = _fraction_matrix(features, Fraction(1, 10_000))
    curvature = {
        "mu_lower": [
            {
                "value": str(value),
                "valid": _curvature_validity(base_hessian, value, lower=True),
            }
            for value in (Fraction(1, 800), Fraction(1, 400), Fraction(1, 200))
        ],
        "smoothness_upper": [
            {
                "value": str(value),
                "valid": _curvature_validity(base_hessian, value, lower=False),
            }
            for value in (Fraction(189, 50), Fraction(21, 5), Fraction(231, 50))
        ],
    }
    accepted = [row for row in records if row["cost_gate_accepts"]]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "grid": "ridge x sketch stride x relative squared tolerance",
            "ridge_values": ["1/100000", "1/10000", "1/1000"],
            "sketch_strides": [5, 10, 20],
            "tolerance_powers": [8, 10, 12],
            "common_ledger": "50nd + 6nd^2 + 30d^3 offline, plus sketch/proposal and sequential verification",
            "scope": "frozen data-driven sensitivity; not a population study",
        },
        "summary": {
            "configuration_count": len(records),
            "accepted_count": len(accepted),
            "minimum_total_cost_ratio": min(row["total_cost_ratio"] for row in records),
            "maximum_total_cost_ratio": max(row["total_cost_ratio"] for row in records),
            "minimum_saved_calls": min(row["saved_calls"] for row in records),
            "maximum_saved_calls": max(row["saved_calls"] for row in records),
        },
        "curvature_misspecification": curvature,
        "records": records,
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__)),
            "helper_sha256": _file_hash(
                ROOT / "experiments" / "run_real_spx_ill_conditioned_study.py"
            ),
            "input_sha256": _file_hash(args.chain),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
