#!/usr/bin/env python3
"""Real-SPX constant-pipeline and production-grid bridge audit.

The theorem-compatible case fits a rationalized ridge surface to a frozen SPX
option chain.  All curvature constants and stopping comparisons are verified
with Fraction arithmetic.  A separate bridge imports the already frozen
101x101 SLV production-grid audit and labels it explicitly as out of class for
the smooth strongly convex theorem.
"""

from __future__ import annotations

import csv
from fractions import Fraction
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
CHAIN = PROJECT_ROOT / "data" / "market_data" / "spx_options_2026-08-08.csv"
CHAIN_META = PROJECT_ROOT / "data" / "market_data" / "spx_options_2026-08-08_meta.json"
PRODUCTION = (
    PROJECT_ROOT
    / "HWC_study"
    / "production_real"
    / "results"
    / "real_market_results.json"
)
OUTPUT = ROOT / "results" / "real_spx_two_oracle_study.json"
SCHEMA = "c2o-real-spx-two-oracle-study-v1"
ROUNDING_SCALE = 10**6
RIDGE = Fraction(1, 20)
SKETCH_STRIDE = 10


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


def _load_hashed_payload(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    computed = sha256(_canonical(payload)).hexdigest()
    if recorded != computed:
        raise ValueError(f"payload hash mismatch: {path}")
    return payload, recorded


def _dot(left: Vector, right: Vector) -> Fraction:
    return sum((a * b for a, b in zip(left, right, strict=True)), Fraction(0))


def _matvec(matrix: Matrix, vector: Vector) -> Vector:
    return [
        sum(
            (matrix[i][j] * vector[j] for j in range(len(vector))),
            Fraction(0),
        )
        for i in range(len(matrix))
    ]


def _subtract(left: Vector, right: Vector) -> Vector:
    return [a - b for a, b in zip(left, right, strict=True)]


def _scale_vector(scalar: Fraction, vector: Vector) -> Vector:
    return [scalar * value for value in vector]


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
        work[column] = [entry / pivot_value for entry in work[column]]
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            if factor == 0:
                continue
            work[row] = [
                work[row][index] - factor * work[column][index]
                for index in range(size + 1)
            ]
    return [work[i][-1] for i in range(size)]


def _gershgorin(matrix: Matrix) -> tuple[Fraction, Fraction]:
    lower: list[Fraction] = []
    upper: list[Fraction] = []
    for i, row in enumerate(matrix):
        radius = sum((abs(value) for j, value in enumerate(row) if j != i), Fraction(0))
        lower.append(row[i] - radius)
        upper.append(row[i] + radius)
    return min(lower), max(upper)


def _residual(matrix: Matrix, linear: Vector, point: Vector) -> Vector:
    return _subtract(_matvec(matrix, point), linear)


def _exact_calls(
    matrix: Matrix,
    linear: Vector,
    start: Vector,
    step_size: Fraction,
    tolerance_squared: Fraction,
) -> tuple[int, Fraction, Fraction, Vector]:
    point = start.copy()
    calls = 0
    previous_squared: Fraction | None = None
    while True:
        residual = _residual(matrix, linear, point)
        residual_squared = _dot(residual, residual)
        if residual_squared <= tolerance_squared:
            return calls, previous_squared or residual_squared, residual_squared, point
        previous_squared = residual_squared
        point = _subtract(point, _scale_vector(step_size, residual))
        calls += 1
        if calls > 200:
            raise RuntimeError("rational gradient trajectory exceeded 200 calls")


def _fraction_matrix_from_integer_rows(rows: np.ndarray, *, ridge: Fraction) -> Matrix:
    count, dimension = rows.shape
    denominator = count * ROUNDING_SCALE**2
    matrix: Matrix = []
    for i in range(dimension):
        row: list[Fraction] = []
        for j in range(dimension):
            numerator = sum(
                int(a) * int(b) for a, b in zip(rows[:, i], rows[:, j], strict=True)
            )
            value = Fraction(numerator, denominator)
            if i == j:
                value += ridge
            row.append(value)
        matrix.append(row)
    return matrix


def _fraction_linear_from_integer_rows(rows: np.ndarray, targets: np.ndarray) -> Vector:
    count, dimension = rows.shape
    denominator = count * ROUNDING_SCALE**2
    return [
        Fraction(
            sum(int(a) * int(b) for a, b in zip(rows[:, i], targets, strict=True)),
            denominator,
        )
        for i in range(dimension)
    ]


def _load_market_panel() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    with CHAIN.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            try:
                row = {
                    **raw,
                    **{
                        key: float(raw[key])
                        for key in (
                            "Knorm",
                            "T",
                            "iv_bs",
                            "bid",
                            "ask",
                            "bid_ask_spread",
                        )
                    },
                }
            except (TypeError, ValueError):
                continue
            eligible = (
                raw["otm"].lower() == "true"
                and raw["liquidity_flag"] == "liquid"
                and row["bid"] > 0.0
                and row["ask"] > row["bid"]
                and row["bid_ask_spread"] <= 0.08
                and 0.75 <= row["Knorm"] <= 1.25
                and 0.05 <= row["iv_bs"] <= 0.80
                and 0.03 <= row["T"] <= 3.0
            )
            if eligible:
                selected.append(row)
    meta = json.loads(CHAIN_META.read_text(encoding="utf-8"))
    return selected, meta


def _market_surface_case() -> dict[str, Any]:
    started = perf_counter()
    rows, meta = _load_market_panel()
    u = np.asarray([(row["Knorm"] - 1.0) / 0.25 for row in rows])
    t = np.asarray([row["T"] / 3.0 for row in rows])
    raw_features = np.column_stack(
        [
            np.ones(len(rows)),
            u,
            t,
            u**2,
            u * t,
            t**2,
            u**3,
            u**2 * t,
            u * t**2,
            t**3,
        ]
    )
    centers = np.zeros(raw_features.shape[1])
    scales = np.ones(raw_features.shape[1])
    centers[1:] = raw_features[:, 1:].mean(axis=0)
    raw_features[:, 1:] -= centers[1:]
    scales[1:] = np.sqrt(np.mean(raw_features[:, 1:] ** 2, axis=0))
    raw_features[:, 1:] /= scales[1:]
    gram = raw_features.T @ raw_features / len(rows)
    eigenvalues, eigenvectors = np.linalg.eigh(gram)
    whitening = eigenvectors @ np.diag(1.0 / np.sqrt(eigenvalues)) @ eigenvectors.T
    whitening = np.round(whitening, 6)
    features = raw_features @ whitening
    targets = np.asarray([row["iv_bs"] for row in rows])
    feature_integers = np.rint(features * ROUNDING_SCALE).astype(np.int64)
    target_integers = np.rint(targets * ROUNDING_SCALE).astype(np.int64)
    feature_rounding_error = float(
        np.max(np.abs(features - feature_integers / ROUNDING_SCALE))
    )
    target_rounding_error = float(
        np.max(np.abs(targets - target_integers / ROUNDING_SCALE))
    )

    exact_hessian = _fraction_matrix_from_integer_rows(feature_integers, ridge=RIDGE)
    exact_linear = _fraction_linear_from_integer_rows(feature_integers, target_integers)
    sketch_integers = feature_integers[::SKETCH_STRIDE]
    sketch_hessian = _fraction_matrix_from_integer_rows(sketch_integers, ridge=RIDGE)
    candidate = _solve(sketch_hessian, exact_linear)
    dimension = len(exact_linear)
    current = [Fraction(0) for _ in range(dimension)]
    initial_residual = _residual(exact_hessian, exact_linear, current)
    initial_residual_squared = _dot(initial_residual, initial_residual)
    tolerance_squared = initial_residual_squared / 10**10
    mu, smoothness = _gershgorin(exact_hessian)
    if mu <= 0:
        raise RuntimeError("exact Gershgorin lower curvature bound is not positive")
    step_size = Fraction(17, 20) / smoothness
    if not 0 < step_size < Fraction(2, 1) / smoothness:
        raise RuntimeError("certified step size is outside the contraction range")

    baseline = _exact_calls(
        exact_hessian,
        exact_linear,
        current,
        step_size,
        tolerance_squared,
    )
    hybrid = _exact_calls(
        exact_hessian,
        exact_linear,
        candidate,
        step_size,
        tolerance_squared,
    )
    call_saving = baseline[0] - hybrid[0]
    if call_saving < 1:
        raise RuntimeError("the real-data cheap candidate does not save a call")

    gamma = -_dot(candidate, initial_residual) / initial_residual_squared
    proposal_defect = _subtract(candidate, _scale_vector(-gamma, initial_residual))
    defect_squared = _dot(proposal_defect, proposal_defect)
    candidate_distance_squared = _dot(candidate, candidate)
    radius_squared = initial_residual_squared / (mu * mu)

    row_count = len(rows)
    sketch_count = len(sketch_integers)
    exact_gradient_flops = 2.0 * row_count * dimension
    proposal_flops = 2.0 * sketch_count * dimension**2 + (2.0 / 3.0) * dimension**3
    verification_flops = 2.0 * (baseline[0] + hybrid[0]) * dimension**2
    online_cost = (proposal_flops + verification_flops) / exact_gradient_flops
    offline_flops = (
        50.0 * row_count * dimension
        + 6.0 * row_count * dimension**2
        + 30.0 * dimension**3
    )
    offline_cost = offline_flops / exact_gradient_flops
    if online_cost >= call_saving:
        raise RuntimeError("online branch work costs more than the realized saving")
    break_even_reuses = ceil(offline_cost / (call_saving - online_cost))
    amortized_cost = online_cost + offline_cost / break_even_reuses

    constant_pipeline_seconds = perf_counter() - started
    float_features = feature_integers.astype(float) / ROUNDING_SCALE
    float_targets = target_integers.astype(float) / ROUNDING_SCALE
    float_current = np.zeros(dimension)
    float_sketch = float_features[::SKETCH_STRIDE]
    float_ridge = float(RIDGE)
    float_hessian = np.asarray(
        [[float(value) for value in row] for row in exact_hessian]
    )
    float_linear = np.asarray([float(value) for value in exact_linear])
    float_candidate = np.asarray([float(value) for value in candidate])

    def exact_gradient(point: np.ndarray) -> np.ndarray:
        return (
            float_features.T @ (float_features @ point - float_targets) / row_count
            + float_ridge * point
        )

    cached_gradient = exact_gradient(float_current)

    def cheap_proposal_from_cached(point: np.ndarray) -> np.ndarray:
        model = float_sketch.T @ float_sketch / sketch_count + float_ridge * np.eye(
            dimension
        )
        return point - np.linalg.solve(model, cached_gradient)

    def replay_certificate() -> tuple[int, int]:
        counts: list[int] = []
        for start in (float_current, float_candidate):
            point = start.copy()
            for calls in range(201):
                residual = float_hessian @ point - float_linear
                if float(residual @ residual) <= float(tolerance_squared):
                    counts.append(calls)
                    break
                point -= float(step_size) * residual
            else:
                raise RuntimeError("floating certificate replay did not terminate")
        return counts[0], counts[1]

    exact_times: list[float] = []
    proposal_times: list[float] = []
    verification_times: list[float] = []
    for _ in range(101):
        tick = perf_counter()
        exact_gradient(float_current)
        exact_times.append(perf_counter() - tick)
        tick = perf_counter()
        cheap_proposal_from_cached(float_current)
        proposal_times.append(perf_counter() - tick)
        tick = perf_counter()
        replay_certificate()
        verification_times.append(perf_counter() - tick)
    median_exact_seconds = float(np.median(exact_times))
    measured_online_cost = float(
        (np.median(proposal_times) + np.median(verification_times))
        / median_exact_seconds
    )
    measured_pipeline_units = constant_pipeline_seconds / median_exact_seconds
    measured_break_even_reuses = (
        ceil(measured_pipeline_units / (call_saving - measured_online_cost))
        if measured_online_cost < call_saving
        else None
    )

    return {
        "data": {
            "source_symbol": meta["source_symbol"],
            "snapshot_timestamp": meta["snapshot_ts"],
            "raw_quote_count": meta["n_options"],
            "filtered_quote_count": row_count,
            "expiry_count": len({row["exp"] for row in rows}),
            "filter": (
                "native OTM, liquid flag, positive noncrossed quotes, relative spread <=8%, "
                "0.75<=K/S<=1.25, 0.05<=IV<=0.80, 0.03<=T<=3"
            ),
            "provenance_limit": (
                "workspace snapshot collected through yfinance; not an official consolidated feed"
            ),
        },
        "objective": {
            "type": "rationalized ridge implied-volatility surface least squares",
            "dimension": dimension,
            "basis": "total-degree-three polynomial in normalized moneyness and maturity",
            "ridge": str(RIDGE),
            "rounding_scale": ROUNDING_SCALE,
            "maximum_feature_rounding_error": feature_rounding_error,
            "maximum_target_rounding_error": target_rounding_error,
            "whitening_centers": centers.tolist(),
            "whitening_scales": scales.tolist(),
            "rounded_whitening_matrix": whitening.tolist(),
            "exact_hessian": [[str(value) for value in row] for row in exact_hessian],
            "exact_linear": [str(value) for value in exact_linear],
        },
        "cheap_oracle": {
            "type": "deterministic every-tenth-quote sketch Hessian applied to cached exact gradient",
            "sketch_stride": SKETCH_STRIDE,
            "sketch_quote_count": sketch_count,
            "sketch_fraction": sketch_count / row_count,
            "candidate": [str(value) for value in candidate],
        },
        "certificate": {
            "arithmetic": "Python Fraction exact arithmetic",
            "mu_gershgorin": str(mu),
            "smoothness_gershgorin": str(smoothness),
            "condition_upper": float(smoothness / mu),
            "step_size": str(step_size),
            "initial_residual_squared": str(initial_residual_squared),
            "tolerance_squared": str(tolerance_squared),
            "radius_squared": str(radius_squared),
            "candidate_distance_squared": str(candidate_distance_squared),
            "proposal_gamma": str(gamma),
            "proposal_defect_squared": str(defect_squared),
            "baseline_calls": baseline[0],
            "hybrid_calls": hybrid[0],
            "exact_call_saving": call_saving,
            "baseline_preterminal_residual_squared": str(baseline[1]),
            "baseline_terminal_residual_squared": str(baseline[2]),
            "hybrid_preterminal_residual_squared": str(hybrid[1]),
            "hybrid_terminal_residual_squared": str(hybrid[2]),
            "strict_crossings_verified": bool(
                baseline[1] > tolerance_squared >= baseline[2]
                and hybrid[1] > tolerance_squared >= hybrid[2]
            ),
        },
        "cost_accounting": {
            "unit": "one full-panel exact gradient flop count",
            "exact_gradient_flops": exact_gradient_flops,
            "online_proposal_and_verification_units": online_cost,
            "one_time_constant_pipeline_units": offline_cost,
            "arithmetic_ledger": (
                "common ledger: feature/filter budget 50nd + dense panel transforms "
                "6nd^2 + factorization/eigendecomposition budget 30d^3; "
                "unit-cost scalar arithmetic"
            ),
            "cold_start_total_units": online_cost + offline_cost + hybrid[0],
            "cold_start_baseline_units": float(baseline[0]),
            "cold_start_dominates": bool(
                online_cost + offline_cost + hybrid[0] <= baseline[0]
            ),
            "break_even_reuses": break_even_reuses,
            "amortized_branch_units_at_break_even": amortized_cost,
            "amortized_total_units_at_break_even": amortized_cost + hybrid[0],
            "amortized_dominates": bool(
                amortized_cost + hybrid[0] <= baseline[0] + 1.0e-12
            ),
            "measured_median_exact_gradient_seconds": median_exact_seconds,
            "measured_median_rebuild_and_proposal_seconds": float(
                np.median(proposal_times)
            ),
            "measured_median_certificate_replay_seconds": float(
                np.median(verification_times)
            ),
            "measured_online_to_exact_ratio": measured_online_cost,
            "measured_constant_pipeline_seconds": constant_pipeline_seconds,
            "measured_constant_pipeline_units": measured_pipeline_units,
            "measured_break_even_reuses": measured_break_even_reuses,
            "timing_scope": (
                "descriptive local CPU timing, including CSV filtering and exact Fraction "
                "construction; the certified comparison uses the declared arithmetic ledger"
            ),
        },
        "generation_seconds": perf_counter() - started,
    }


def _production_bridge() -> dict[str, Any]:
    payload, payload_hash = _load_hashed_payload(PRODUCTION)
    for relative, expected in payload["environment"]["input_sha256"].items():
        path = (
            PROJECT_ROOT / "HWC_study" / relative
            if relative.startswith("production_real/")
            else PROJECT_ROOT / relative
        )
        if _file_hash(path) != expected:
            raise ValueError(f"production input hash mismatch: {relative}")
    records = {
        (record["grid"], record["method"]): record for record in payload["records"]
    }
    exact = records[("production_101", "exact_only")]
    hybrid = records[("production_101", "hwc_2")]
    return {
        "theorem_status": (
            "out of class: projected nonconvex SLV calibration; descriptive downstream stress test only"
        ),
        "source_payload_sha256": payload_hash,
        "grid": "101x101",
        "selected_quote_count": payload["declaration"]["selected_quote_count"],
        "expiry_count": len(payload["declaration"]["selected_expiries"]),
        "both_exactly_stationarity_certified": bool(
            exact["certified"] and hybrid["certified"]
        ),
        "exact_median_wall_seconds": exact["median_wall_seconds"],
        "hybrid_median_wall_seconds": hybrid["median_wall_seconds"],
        "runtime_speedup": payload["summary"]["production_101"]["runtime_speedup"],
        "exact_adjoint_change_fraction": -payload["summary"]["production_101"][
            "adjoint_reduction_fraction"
        ],
        "iv_rmse_ratio": payload["summary"]["production_101"]["iv_rmse_ratio"],
        "repeat_count": exact["repeat_count"],
        "interpretation": (
            "wall time improved in two frozen repeats, but exact adjoint work did not; "
            "this is not evidence for the transcript-optimal gate"
        ),
    }


def main() -> None:
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "purpose": (
                "demonstrate a verifiable constant/cost pipeline on real market data and "
                "bridge to an application-scale out-of-class stress test"
            ),
            "claims": (
                "the rational surface case is theorem compatible; the SLV production bridge is not"
            ),
        },
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__).resolve()),
            "input_sha256": {
                str(CHAIN.relative_to(PROJECT_ROOT)): _file_hash(CHAIN),
                str(CHAIN_META.relative_to(PROJECT_ROOT)): _file_hash(CHAIN_META),
                str(PRODUCTION.relative_to(PROJECT_ROOT)): _file_hash(PRODUCTION),
            },
        },
        "theorem_compatible_surface": _market_surface_case(),
        "production_grid_bridge": _production_bridge(),
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "payload_sha256": payload["payload_sha256"],
        "surface": {
            "filtered_quotes": payload["theorem_compatible_surface"]["data"][
                "filtered_quote_count"
            ],
            "baseline_calls": payload["theorem_compatible_surface"]["certificate"][
                "baseline_calls"
            ],
            "hybrid_calls": payload["theorem_compatible_surface"]["certificate"][
                "hybrid_calls"
            ],
            "break_even_reuses": payload["theorem_compatible_surface"][
                "cost_accounting"
            ]["break_even_reuses"],
        },
        "production": payload["production_grid_bridge"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
