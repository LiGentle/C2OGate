#!/usr/bin/env python3
"""Positive real-SPX audit with certified ill conditioning and total cost.

The design is centered and scaled but deliberately not whitened.  Exact
rational curvature bounds, condition witnesses, candidate identities, and
stopping crossings are independently verifiable.  The expensive oracle is a
full-panel gradient over the filtered option chain.
"""

from __future__ import annotations

import csv
from fractions import Fraction
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
CHAIN = PROJECT_ROOT / "data" / "market_data" / "spx_options_2026-08-08.csv"
CHAIN_META = PROJECT_ROOT / "data" / "market_data" / "spx_options_2026-08-08_meta.json"
OUTPUT = ROOT / "results" / "real_spx_ill_conditioned_study.json"
VERIFIER = ROOT / "tools" / "verify_real_spx_ill_conditioned_certificate.py"
SCHEMA = "c2o-real-spx-ill-conditioned-v2"
ROUNDING_SCALE = 10**6
RIDGE = Fraction(1, 10_000)
MU_LOWER = Fraction(1, 400)
SMOOTHNESS_UPPER = Fraction(21, 5)
STEP_SIZE = Fraction(17, 84)
SKETCH_STRIDE = 10
TIMING_REPEATS = 3


Matrix = list[list[Fraction]]
Vector = list[Fraction]


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


def _dot(left: Vector, right: Vector) -> Fraction:
    return sum((a * b for a, b in zip(left, right, strict=True)), Fraction(0))


def _matvec(matrix: Matrix, vector: Vector) -> Vector:
    return [
        sum(
            (value * coordinate for value, coordinate in zip(row, vector, strict=True)),
            Fraction(0),
        )
        for row in matrix
    ]


def _determinant(matrix: Matrix) -> Fraction:
    work = [row.copy() for row in matrix]
    sign = 1
    determinant = Fraction(1)
    for column in range(len(work)):
        pivot = next(
            (row for row in range(column, len(work)) if work[row][column]),
            None,
        )
        if pivot is None:
            return Fraction(0)
        if pivot != column:
            work[column], work[pivot] = work[pivot], work[column]
            sign *= -1
        pivot_value = work[column][column]
        determinant *= pivot_value
        for row in range(column + 1, len(work)):
            factor = work[row][column] / pivot_value
            for index in range(column + 1, len(work)):
                work[row][index] -= factor * work[column][index]
    return sign * determinant


def _leading_minors(matrix: Matrix) -> list[Fraction]:
    return [
        _determinant([row[:size] for row in matrix[:size]])
        for size in range(1, len(matrix) + 1)
    ]


def _rayleigh(matrix: Matrix, vector: Vector) -> Fraction:
    return _dot(vector, _matvec(matrix, vector)) / _dot(vector, vector)


def _solve(matrix: Matrix, right: Vector) -> Vector:
    size = len(matrix)
    work = [matrix[i].copy() + [right[i]] for i in range(size)]
    for column in range(size):
        pivot = next(
            (row for row in range(column, size) if work[row][column] != 0),
            None,
        )
        if pivot is None:
            raise ValueError("singular rational sketch Hessian")
        work[column], work[pivot] = work[pivot], work[column]
        pivot_value = work[column][column]
        work[column] = [value / pivot_value for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            if factor:
                work[row] = [
                    work[row][index] - factor * work[column][index]
                    for index in range(size + 1)
                ]
    return [work[i][-1] for i in range(size)]


def _fraction_matrix(rows: np.ndarray, ridge: Fraction) -> Matrix:
    count, dimension = rows.shape
    denominator = count * ROUNDING_SCALE**2
    matrix: Matrix = []
    for i in range(dimension):
        output_row: list[Fraction] = []
        for j in range(dimension):
            numerator = sum(
                int(a) * int(b) for a, b in zip(rows[:, i], rows[:, j], strict=True)
            )
            value = Fraction(numerator, denominator)
            if i == j:
                value += ridge
            output_row.append(value)
        matrix.append(output_row)
    return matrix


def _fraction_linear(rows: np.ndarray, targets: np.ndarray) -> Vector:
    count, dimension = rows.shape
    denominator = count * ROUNDING_SCALE**2
    return [
        Fraction(
            sum(int(a) * int(b) for a, b in zip(rows[:, i], targets, strict=True)),
            denominator,
        )
        for i in range(dimension)
    ]


def _load_panel() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    with CHAIN.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            try:
                numeric = {
                    key: float(raw[key])
                    for key in (
                        "Knorm",
                        "T",
                        "iv_bs",
                        "bid",
                        "ask",
                        "bid_ask_spread",
                    )
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
    return selected, json.loads(CHAIN_META.read_text(encoding="utf-8"))


def _float_calls(
    matrix: np.ndarray,
    linear: np.ndarray,
    start: np.ndarray,
    tolerance_squared: float,
) -> int:
    transition = np.eye(len(linear)) - float(STEP_SIZE) * matrix
    gradient = matrix @ start - linear
    for calls in range(100_001):
        if float(gradient @ gradient) <= tolerance_squared:
            return calls
        gradient = transition @ gradient
    raise RuntimeError("trajectory exceeded the declared horizon")


def _timed_full_panel_calls(
    features: np.ndarray,
    targets: np.ndarray,
    start: np.ndarray,
    tolerance_squared: float,
) -> tuple[int, float]:
    count = len(features)
    point = start.copy()
    started = perf_counter()
    for calls in range(100_001):
        gradient = (
            features.T @ (features @ point - targets) / count + float(RIDGE) * point
        )
        if float(gradient @ gradient) <= tolerance_squared:
            return calls, perf_counter() - started
        point -= float(STEP_SIZE) * gradient
    raise RuntimeError("timed full-panel trajectory exceeded the declared horizon")


def main() -> None:
    pipeline_started = perf_counter()
    rows, meta = _load_panel()
    moneyness = np.asarray([(row["Knorm"] - 1.0) / 0.25 for row in rows])
    maturity = np.asarray([row["T"] / 3.0 for row in rows])
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
    centers = np.zeros(features.shape[1])
    scales = np.ones(features.shape[1])
    centers[1:] = features[:, 1:].mean(axis=0)
    features[:, 1:] -= centers[1:]
    scales[1:] = np.sqrt(np.mean(features[:, 1:] ** 2, axis=0))
    features[:, 1:] /= scales[1:]
    targets = np.asarray([row["iv_bs"] for row in rows])
    feature_integers = np.rint(features * ROUNDING_SCALE).astype(np.int64)
    target_integers = np.rint(targets * ROUNDING_SCALE).astype(np.int64)
    rational_features = feature_integers.astype(float) / ROUNDING_SCALE
    rational_targets = target_integers.astype(float) / ROUNDING_SCALE
    sketch_integers = feature_integers[::SKETCH_STRIDE]
    row_count, dimension = feature_integers.shape
    sketch_count = len(sketch_integers)

    exact_hessian = _fraction_matrix(feature_integers, RIDGE)
    exact_linear = _fraction_linear(feature_integers, target_integers)
    sketch_hessian = _fraction_matrix(sketch_integers, RIDGE)
    candidate = _solve(sketch_hessian, exact_linear)
    float_hessian = np.asarray(
        [[float(value) for value in row] for row in exact_hessian]
    )
    float_linear = np.asarray([float(value) for value in exact_linear])
    float_candidate = np.asarray([float(value) for value in candidate])
    initial_gradient_squared = _dot(exact_linear, exact_linear)
    tolerance_squared = initial_gradient_squared / 10**10
    baseline_calls = _float_calls(
        float_hessian,
        float_linear,
        np.zeros(dimension),
        float(tolerance_squared),
    )
    hybrid_calls = _float_calls(
        float_hessian,
        float_linear,
        float_candidate,
        float(tolerance_squared),
    )
    saved_calls = baseline_calls - hybrid_calls
    if saved_calls <= 0:
        raise RuntimeError("ill-conditioned candidate does not save exact calls")

    lower_matrix = [
        [value - (MU_LOWER if i == j else 0) for j, value in enumerate(row)]
        for i, row in enumerate(exact_hessian)
    ]
    upper_matrix = [
        [(SMOOTHNESS_UPPER if i == j else 0) - value for j, value in enumerate(row)]
        for i, row in enumerate(exact_hessian)
    ]
    lower_minors = _leading_minors(lower_matrix)
    upper_minors = _leading_minors(upper_matrix)
    if min(lower_minors) <= 0 or min(upper_minors) <= 0:
        raise RuntimeError("rational curvature enclosure failed")
    _, eigenvectors = np.linalg.eigh(float_hessian)
    witness_min = [
        Fraction(int(value)) for value in np.rint(eigenvectors[:, 0] * 10**6)
    ]
    witness_max = [
        Fraction(int(value)) for value in np.rint(eigenvectors[:, -1] * 10**6)
    ]
    rayleigh_min = _rayleigh(exact_hessian, witness_min)
    rayleigh_max = _rayleigh(exact_hessian, witness_max)
    condition_lower = rayleigh_max / rayleigh_min
    condition_upper = SMOOTHNESS_UPPER / MU_LOWER
    if condition_lower <= 1000:
        raise RuntimeError("condition lower certificate is not sufficiently separated")

    exact_gradient_flops = 2.0 * row_count * dimension
    offline_flops = (
        50.0 * row_count * dimension
        + 2.0 * (row_count + sketch_count) * dimension**2
        + 30.0 * dimension**3
    )
    proposal_flops = (2.0 / 3.0) * dimension**3
    verification_flops = 2.0 * (baseline_calls + hybrid_calls) * dimension**2
    charged_nonexact_units = (
        offline_flops + proposal_flops + verification_flops
    ) / exact_gradient_flops
    candidate_total_units = hybrid_calls + charged_nonexact_units
    arithmetic_ratio = candidate_total_units / baseline_calls
    cost_slack = baseline_calls - candidate_total_units
    if cost_slack <= 1.0:
        raise RuntimeError(
            "positive instance fails the total-cost and call-saving gate"
        )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "purpose": (
                "positive real-data point with certified ill conditioning, exact stopping "
                "crossings, and all declared costs charged"
            ),
            "scope": (
                "singleton rational quadratic induced by the frozen SPX panel; not a "
                "distributional or nonlinear-calibration claim"
            ),
            "reproduction_unit": (
                "the hash-bound payload is self-contained for certificate replay; "
                "data-to-matrix regeneration requires the external companion snapshot"
            ),
        },
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__).resolve()),
            "verifier_sha256": _file_hash(VERIFIER),
            "input_sha256": {
                str(CHAIN.relative_to(PROJECT_ROOT)): _file_hash(CHAIN),
                str(CHAIN_META.relative_to(PROJECT_ROOT)): _file_hash(CHAIN_META),
            },
        },
        "data": {
            "source_symbol": meta["source_symbol"],
            "snapshot_timestamp": meta["snapshot_ts"],
            "raw_quote_count": meta["n_options"],
            "filtered_quote_count": row_count,
            "expiry_count": len({row["exp"] for row in rows}),
            "provenance_limit": (
                "workspace snapshot collected through yfinance; not an official consolidated feed"
            ),
        },
        "objective": {
            "type": "unwhitened rational ridge implied-volatility surface least squares",
            "dimension": dimension,
            "basis": "centered/RMS-scaled total-degree-three polynomial; no whitening",
            "ridge": str(RIDGE),
            "rounding_scale": ROUNDING_SCALE,
            "centers": centers.tolist(),
            "scales": scales.tolist(),
            "exact_hessian": [[str(value) for value in row] for row in exact_hessian],
            "exact_linear": [str(value) for value in exact_linear],
            "sketch_hessian": [[str(value) for value in row] for row in sketch_hessian],
            "sketch_stride": SKETCH_STRIDE,
            "sketch_quote_count": sketch_count,
        },
        "certificate": {
            "arithmetic": (
                "exact Fraction identities and curvature; Decimal directed-rounding "
                "interval powers for stopping crossings"
            ),
            "mu_lower": str(MU_LOWER),
            "smoothness_upper": str(SMOOTHNESS_UPPER),
            "lower_leading_minors": [str(value) for value in lower_minors],
            "upper_leading_minors": [str(value) for value in upper_minors],
            "condition_witness_min": [str(value) for value in witness_min],
            "condition_witness_max": [str(value) for value in witness_max],
            "rayleigh_min_upper": str(rayleigh_min),
            "rayleigh_max_lower": str(rayleigh_max),
            "condition_lower": str(condition_lower),
            "condition_upper": str(condition_upper),
            "step_size": str(STEP_SIZE),
            "tolerance_squared": str(tolerance_squared),
            "candidate": [str(value) for value in candidate],
            "baseline_calls": baseline_calls,
            "hybrid_calls": hybrid_calls,
            "saved_exact_calls": saved_calls,
            "monotonicity_reason": (
                "0 < alpha*lambda(Q) < alpha*L_upper < 1, so gradient norms decrease"
            ),
        },
        "cost_accounting": {
            "unit": "one full-panel exact gradient arithmetic count",
            "exact_gradient_flops": exact_gradient_flops,
            "offline_pipeline_flops": offline_flops,
            "online_proposal_flops": proposal_flops,
            "conservative_sequential_verification_flops": verification_flops,
            "charged_nonexact_units": charged_nonexact_units,
            "baseline_total_units": float(baseline_calls),
            "candidate_total_units": candidate_total_units,
            "candidate_to_baseline_ratio": arithmetic_ratio,
            "total_cost_slack_units": cost_slack,
            "minimum_saved_calls": 1,
            "gate_accepts": bool(saved_calls >= 1 and cost_slack >= 0),
            "ledger": (
                "50nd filtering/features + two full/sketch Gram builds + 30d^3 "
                "factorization/curvature + proposal solve + sequential replay upper charge"
            ),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    verification_started = perf_counter()
    subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            str(OUTPUT),
            "--source-root",
            str(PROJECT_ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    independent_verification_seconds = perf_counter() - verification_started
    pipeline_seconds = perf_counter() - pipeline_started

    float_sketch_hessian = np.asarray(
        [[float(value) for value in row] for row in sketch_hessian]
    )
    baseline_timings: list[float] = []
    hybrid_timings: list[float] = []
    for _ in range(TIMING_REPEATS):
        calls, elapsed = _timed_full_panel_calls(
            rational_features,
            rational_targets,
            np.zeros(dimension),
            float(tolerance_squared),
        )
        if calls != baseline_calls:
            raise RuntimeError("timed baseline count disagrees with certificate")
        baseline_timings.append(elapsed)
        hybrid_started = perf_counter()
        timed_candidate = np.linalg.solve(float_sketch_hessian, float_linear)
        calls, trajectory_elapsed = _timed_full_panel_calls(
            rational_features,
            rational_targets,
            timed_candidate,
            float(tolerance_squared),
        )
        if calls != hybrid_calls:
            raise RuntimeError("timed hybrid count disagrees with certificate")
        hybrid_timings.append(perf_counter() - hybrid_started)
        if trajectory_elapsed <= 0:
            raise RuntimeError("invalid hybrid trajectory timing")
    baseline_median = float(np.median(baseline_timings))
    hybrid_median = float(np.median(hybrid_timings))
    per_reuse_saving = baseline_median - hybrid_median
    if per_reuse_saving <= 0:
        raise RuntimeError("measured hybrid path is not faster")
    measured_break_even = ceil(pipeline_seconds / per_reuse_saving)
    measured_ratio_at_break_even = (
        hybrid_median + pipeline_seconds / measured_break_even
    ) / baseline_median
    payload["timing"] = {
        "repeat_count": TIMING_REPEATS,
        "baseline_seconds": baseline_timings,
        "hybrid_seconds_including_proposal_solve": hybrid_timings,
        "baseline_median_seconds": baseline_median,
        "hybrid_median_seconds": hybrid_median,
        "pipeline_seconds_including_certificate_generation_and_verification": pipeline_seconds,
        "independent_verification_seconds": independent_verification_seconds,
        "measured_break_even_reuses": measured_break_even,
        "measured_ratio_at_break_even": measured_ratio_at_break_even,
        "measured_warm_speedup": baseline_median / hybrid_median,
        "scope": "descriptive local CPU timing; exact identities do not depend on timing",
    }
    payload.pop("payload_sha256")
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            str(OUTPUT),
            "--source-root",
            str(PROJECT_ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    print(
        json.dumps(
            {
                "payload_sha256": payload["payload_sha256"],
                "condition_interval": [
                    float(condition_lower),
                    float(condition_upper),
                ],
                "calls": [baseline_calls, hybrid_calls],
                "arithmetic_ratio": arithmetic_ratio,
                "measured_break_even_reuses": measured_break_even,
                "measured_warm_speedup": baseline_median / hybrid_median,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
