#!/usr/bin/env python3
"""Freeze a redistributable raw-row test of the SPX data-to-matrix map."""

from __future__ import annotations

import csv
from fractions import Fraction
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "synthetic_option_panel.csv"
OUTPUT = ROOT / "results" / "synthetic_data_to_matrix_fixture.json"
ROUNDING_SCALE = 10**6
RIDGE = Fraction(1, 10_000)
SKETCH_STRIDE = 3


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


def _fraction_matrix(rows: list[list[int]]) -> list[list[Fraction]]:
    count = len(rows)
    denominator = count * ROUNDING_SCALE**2
    return [
        [
            Fraction(sum(row[i] * row[j] for row in rows), denominator)
            + (RIDGE if i == j else 0)
            for j in range(len(rows[0]))
        ]
        for i in range(len(rows[0]))
    ]


def _fraction_linear(
    rows: list[list[int]], targets: list[int]
) -> list[Fraction]:
    denominator = len(rows) * ROUNDING_SCALE**2
    return [
        Fraction(
            sum(row[i] * target for row, target in zip(rows, targets, strict=True)),
            denominator,
        )
        for i in range(len(rows[0]))
    ]


def _selected_rows() -> list[tuple[float, float, float]]:
    selected: list[tuple[float, float, float]] = []
    with INPUT.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            strike = float(raw["Knorm"])
            maturity = float(raw["T"])
            volatility = float(raw["iv_bs"])
            bid = float(raw["bid"])
            ask = float(raw["ask"])
            spread = float(raw["bid_ask_spread"])
            if (
                raw["otm"].lower() == "true"
                and raw["liquidity_flag"] == "liquid"
                and bid > 0.0
                and ask > bid
                and spread <= 0.08
                and 0.75 <= strike <= 1.25
                and 0.05 <= volatility <= 0.80
                and 0.03 <= maturity <= 3.0
            ):
                selected.append((strike, maturity, volatility))
    return selected


def main() -> None:
    selected = _selected_rows()
    raw_features: list[list[float]] = []
    targets_float: list[float] = []
    for strike, maturity, volatility in selected:
        u = (strike - 1.0) / 0.25
        t = maturity / 3.0
        raw_features.append(
            [1.0, u, t, u**2, u * t, t**2, u**3, u**2 * t, u * t**2, t**3]
        )
        targets_float.append(volatility)
    centers = [0.0] + [
        sum(row[column] for row in raw_features) / len(raw_features)
        for column in range(1, 10)
    ]
    scales = [1.0] + [
        sqrt(
            sum(
                (row[column] - centers[column]) ** 2 for row in raw_features
            )
            / len(raw_features)
        )
        for column in range(1, 10)
    ]
    integer_rows = [
        [
            round((value - centers[column]) / scales[column] * ROUNDING_SCALE)
            if column
            else ROUNDING_SCALE
            for column, value in enumerate(row)
        ]
        for row in raw_features
    ]
    integer_targets = [round(value * ROUNDING_SCALE) for value in targets_float]
    matrix = _fraction_matrix(integer_rows)
    linear = _fraction_linear(integer_rows, integer_targets)
    sketch = _fraction_matrix(integer_rows[::SKETCH_STRIDE])
    payload: dict[str, Any] = {
        "schema": "c2o-synthetic-data-to-matrix-v1",
        "declaration": {
            "purpose": "redistributable raw-row test of the production data-to-matrix map",
            "raw_row_count": 20,
            "filtered_row_count": len(selected),
        },
        "environment": {
            "runner_sha256": _file_hash(Path(__file__).resolve()),
            "input_sha256": {
                str(INPUT.relative_to(ROOT)): _file_hash(INPUT),
            },
        },
        "objective": {
            "rounding_scale": ROUNDING_SCALE,
            "ridge": str(RIDGE),
            "sketch_stride": SKETCH_STRIDE,
            "exact_hessian": [[str(value) for value in row] for row in matrix],
            "exact_linear": [str(value) for value in linear],
            "sketch_hessian": [[str(value) for value in row] for row in sketch],
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "FROZEN: synthetic data-to-matrix fixture, "
        f"rows=20->{len(selected)}, dimension=10, payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
