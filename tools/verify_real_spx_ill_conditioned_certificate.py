#!/usr/bin/env python3
"""Independent verifier for the ill-conditioned real-SPX certificate.

Only the Python standard library is used.  Curvature and candidate identities
are checked with exact rational arithmetic.  Stopping crossings are enclosed
with directed-rounding Decimal interval matrix powers.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from fractions import Fraction
from hashlib import sha256
import json
from math import floor
from math import sqrt
from pathlib import Path
from typing import Any


DEFAULT_PAYLOAD = (
    Path(__file__).resolve().parents[1]
    / "results"
    / "real_spx_ill_conditioned_study.json"
)
PRECISION = 110
Interval = tuple[Decimal, Decimal]
IntervalMatrix = list[list[Interval]]
IntervalVector = list[Interval]
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


def _fraction_matrix(rows: list[list[int]], scale: int, ridge: Fraction) -> Matrix:
    count = len(rows)
    dimension = len(rows[0])
    denominator = count * scale**2
    return [
        [
            Fraction(
                sum(row[i] * row[j] for row in rows),
                denominator,
            )
            + (ridge if i == j else 0)
            for j in range(dimension)
        ]
        for i in range(dimension)
    ]


def _fraction_linear(rows: list[list[int]], targets: list[int], scale: int) -> Vector:
    count = len(rows)
    denominator = count * scale**2
    return [
        Fraction(
            sum(row[i] * target for row, target in zip(rows, targets, strict=True)),
            denominator,
        )
        for i in range(len(rows[0]))
    ]


def _determinant(matrix: Matrix) -> Fraction:
    size = len(matrix)
    work = [row.copy() for row in matrix]
    sign = 1
    determinant = Fraction(1)
    for column in range(size):
        pivot = next(
            (row for row in range(column, size) if work[row][column] != 0),
            None,
        )
        if pivot is None:
            return Fraction(0)
        if pivot != column:
            work[column], work[pivot] = work[pivot], work[column]
            sign *= -1
        pivot_value = work[column][column]
        determinant *= pivot_value
        for row in range(column + 1, size):
            factor = work[row][column] / pivot_value
            for index in range(column + 1, size):
                work[row][index] -= factor * work[column][index]
    return sign * determinant


def _leading_minors(matrix: Matrix) -> list[Fraction]:
    return [
        _determinant([row[:size] for row in matrix[:size]])
        for size in range(1, len(matrix) + 1)
    ]


def _matvec(matrix: Matrix, vector: Vector) -> Vector:
    return [
        sum(
            (value * coordinate for value, coordinate in zip(row, vector, strict=True)),
            Fraction(0),
        )
        for row in matrix
    ]


def _dot(left: Vector, right: Vector) -> Fraction:
    return sum((a * b for a, b in zip(left, right, strict=True)), Fraction(0))


def _rayleigh(matrix: Matrix, vector: Vector) -> Fraction:
    return _dot(vector, _matvec(matrix, vector)) / _dot(vector, vector)


def _fraction_interval(value: Fraction) -> Interval:
    numerator = Decimal(value.numerator)
    denominator = Decimal(value.denominator)
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_FLOOR
        lower = numerator / denominator
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_CEILING
        upper = numerator / denominator
    return lower, upper


def _interval_product(left: Interval, right: Interval) -> Interval:
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_FLOOR
        lower = min(a * b for a in left for b in right)
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_CEILING
        upper = max(a * b for a in left for b in right)
    return lower, upper


def _interval_dot(left: list[Interval], right: list[Interval]) -> Interval:
    products = [_interval_product(a, b) for a, b in zip(left, right, strict=True)]
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_FLOOR
        lower = sum((value[0] for value in products), Decimal(0))
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_CEILING
        upper = sum((value[1] for value in products), Decimal(0))
    return lower, upper


def _interval_matvec(matrix: IntervalMatrix, vector: IntervalVector) -> IntervalVector:
    return [_interval_dot(row, vector) for row in matrix]


def _interval_matmul(left: IntervalMatrix, right: IntervalMatrix) -> IntervalMatrix:
    columns = [list(column) for column in zip(*right, strict=True)]
    return [[_interval_dot(row, column) for column in columns] for row in left]


def _interval_power_apply(
    matrix: Matrix, exponent: int, vector: Vector
) -> IntervalVector:
    result = [_fraction_interval(value) for value in vector]
    power = [[_fraction_interval(value) for value in row] for row in matrix]
    remaining = exponent
    while remaining:
        if remaining & 1:
            result = _interval_matvec(power, result)
        remaining >>= 1
        if remaining:
            power = _interval_matmul(power, power)
    return result


def _interval_square(value: Interval) -> Interval:
    lower, upper = value
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_FLOOR
        squared_lower = (
            Decimal(0) if lower <= 0 <= upper else min(lower * lower, upper * upper)
        )
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_CEILING
        squared_upper = max(lower * lower, upper * upper)
    return squared_lower, squared_upper


def _interval_norm_squared(vector: IntervalVector) -> Interval:
    squares = [_interval_square(value) for value in vector]
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_FLOOR
        lower = sum((value[0] for value in squares), Decimal(0))
    with localcontext() as context:
        context.prec = PRECISION
        context.rounding = ROUND_CEILING
        upper = sum((value[1] for value in squares), Decimal(0))
    return lower, upper


def _crossing_bounds(
    transition: Matrix, start_gradient: Vector, calls: int
) -> dict[str, str]:
    preterminal = _interval_norm_squared(
        _interval_power_apply(transition, calls - 1, start_gradient)
    )
    terminal = _interval_norm_squared(
        _interval_power_apply(transition, calls, start_gradient)
    )
    return {
        "preterminal_lower": str(preterminal[0]),
        "preterminal_upper": str(preterminal[1]),
        "terminal_lower": str(terminal[0]),
        "terminal_upper": str(terminal[1]),
    }


def _rebuild_market_matrices(
    payload: dict[str, Any], source_root: Path
) -> tuple[Matrix, Vector, Matrix]:
    environment = payload["environment"]
    resolved: dict[str, Path] = {}
    for relative, expected in environment["input_sha256"].items():
        path = source_root / relative
        if not path.is_file():
            raise ValueError(f"external source is missing: {path}")
        if _file_hash(path) != expected:
            raise ValueError(f"external source hash mismatch: {relative}")
        resolved[relative] = path
    chain = next(
        path for relative, path in resolved.items() if relative.endswith(".csv")
    )
    selected: list[tuple[float, float, float]] = []
    with chain.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            try:
                strike = float(raw["Knorm"])
                maturity = float(raw["T"])
                volatility = float(raw["iv_bs"])
                bid = float(raw["bid"])
                ask = float(raw["ask"])
                spread = float(raw["bid_ask_spread"])
            except (TypeError, ValueError):
                continue
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
    raw_features: list[list[float]] = []
    targets_float: list[float] = []
    for strike, maturity_value, volatility in selected:
        u = (strike - 1.0) / 0.25
        t = maturity_value / 3.0
        raw_features.append(
            [1.0, u, t, u**2, u * t, t**2, u**3, u**2 * t, u * t**2, t**3]
        )
        targets_float.append(volatility)
    count = len(raw_features)
    centers = [0.0] + [
        sum(row[column] for row in raw_features) / count for column in range(1, 10)
    ]
    scales = [1.0] + [
        sqrt(sum((row[column] - centers[column]) ** 2 for row in raw_features) / count)
        for column in range(1, 10)
    ]
    scale = int(payload["objective"]["rounding_scale"])
    integer_rows = [
        [
            int(round((value - centers[column]) / scales[column] * scale))
            if column
            else scale
            for column, value in enumerate(row)
        ]
        for row in raw_features
    ]
    integer_targets = [int(round(value * scale)) for value in targets_float]
    ridge = Fraction(payload["objective"]["ridge"])
    stride = int(payload["objective"]["sketch_stride"])
    return (
        _fraction_matrix(integer_rows, scale, ridge),
        _fraction_linear(integer_rows, integer_targets, scale),
        _fraction_matrix(integer_rows[::stride], scale, ridge),
    )


def verify_payload(
    payload: dict[str, Any],
    *,
    require_hash: bool = True,
    source_root: Path | None = None,
) -> dict[str, Any]:
    working = json.loads(json.dumps(payload))
    if require_hash:
        recorded = working.pop("payload_sha256")
        computed = sha256(_canonical(working)).hexdigest()
        if recorded != computed:
            raise ValueError("payload hash mismatch")
    if working["schema"] != "c2o-real-spx-ill-conditioned-v2":
        raise ValueError("unsupported payload schema")
    objective = working["objective"]
    certificate = working["certificate"]
    matrix = [[Fraction(value) for value in row] for row in objective["exact_hessian"]]
    linear = [Fraction(value) for value in objective["exact_linear"]]
    sketch = [[Fraction(value) for value in row] for row in objective["sketch_hessian"]]
    candidate = [Fraction(value) for value in certificate["candidate"]]
    dimension = len(matrix)
    if any(len(row) != dimension for row in matrix + sketch):
        raise ValueError("matrix is not square")
    if any(
        matrix[i][j] != matrix[j][i] for i in range(dimension) for j in range(dimension)
    ):
        raise ValueError("exact Hessian is not symmetric")
    if _matvec(sketch, candidate) != linear:
        raise ValueError("candidate does not solve the rational sketch system")
    source_rebuilt = False
    if source_root is not None:
        rebuilt_matrix, rebuilt_linear, rebuilt_sketch = _rebuild_market_matrices(
            working, source_root
        )
        if (
            rebuilt_matrix != matrix
            or rebuilt_linear != linear
            or rebuilt_sketch != sketch
        ):
            raise ValueError("external market data do not rebuild the stored matrices")
        source_rebuilt = True

    mu = Fraction(certificate["mu_lower"])
    smoothness = Fraction(certificate["smoothness_upper"])
    lower_matrix = [
        [value - (mu if i == j else 0) for j, value in enumerate(row)]
        for i, row in enumerate(matrix)
    ]
    upper_matrix = [
        [(smoothness if i == j else 0) - value for j, value in enumerate(row)]
        for i, row in enumerate(matrix)
    ]
    lower_minors = _leading_minors(lower_matrix)
    upper_minors = _leading_minors(upper_matrix)
    if min(lower_minors) <= 0 or min(upper_minors) <= 0:
        raise ValueError("strict curvature enclosure failed")
    if [str(value) for value in lower_minors] != certificate["lower_leading_minors"]:
        raise ValueError("lower leading-minor record mismatch")
    if [str(value) for value in upper_minors] != certificate["upper_leading_minors"]:
        raise ValueError("upper leading-minor record mismatch")

    witness_min = [Fraction(value) for value in certificate["condition_witness_min"]]
    witness_max = [Fraction(value) for value in certificate["condition_witness_max"]]
    rayleigh_min = _rayleigh(matrix, witness_min)
    rayleigh_max = _rayleigh(matrix, witness_max)
    condition_lower = rayleigh_max / rayleigh_min
    if str(rayleigh_min) != certificate["rayleigh_min_upper"]:
        raise ValueError("minimum-mode Rayleigh record mismatch")
    if str(rayleigh_max) != certificate["rayleigh_max_lower"]:
        raise ValueError("maximum-mode Rayleigh record mismatch")
    if (
        str(condition_lower) != certificate["condition_lower"]
        or condition_lower <= 1000
    ):
        raise ValueError("condition-number lower certificate failed")

    alpha = Fraction(certificate["step_size"])
    if not 0 < alpha * smoothness < 1:
        raise ValueError("step size does not certify monotone gradient norms")
    identity = [[Fraction(i == j) for j in range(dimension)] for i in range(dimension)]
    transition = [
        [identity[i][j] - alpha * matrix[i][j] for j in range(dimension)]
        for i in range(dimension)
    ]
    baseline_gradient = [-value for value in linear]
    candidate_gradient = [
        value - target
        for value, target in zip(_matvec(matrix, candidate), linear, strict=True)
    ]
    tolerance = Fraction(certificate["tolerance_squared"])
    tolerance_interval = _fraction_interval(tolerance)
    results: dict[str, dict[str, str]] = {}
    for name, gradient, calls_key in (
        ("baseline", baseline_gradient, "baseline_calls"),
        ("hybrid", candidate_gradient, "hybrid_calls"),
    ):
        calls = int(certificate[calls_key])
        bounds = _crossing_bounds(transition, gradient, calls)
        if Decimal(bounds["preterminal_lower"]) <= tolerance_interval[1]:
            raise ValueError(f"{name} preterminal norm is not strictly above tolerance")
        if Decimal(bounds["terminal_upper"]) > tolerance_interval[0]:
            raise ValueError(f"{name} terminal norm is not below tolerance")
        results[name] = bounds
    if certificate["baseline_calls"] - certificate["hybrid_calls"] <= 0:
        raise ValueError("candidate does not save exact calls")
    data = working["data"]
    cost = working["cost_accounting"]
    row_count = int(data["filtered_quote_count"])
    sketch_count = int(objective["sketch_quote_count"])
    baseline_calls = int(certificate["baseline_calls"])
    hybrid_calls = int(certificate["hybrid_calls"])
    exact_gradient_flops = 2.0 * row_count * dimension
    offline_flops = (
        50.0 * row_count * dimension
        + 2.0 * (row_count + sketch_count) * dimension**2
        + 30.0 * dimension**3
    )
    proposal_flops = (2.0 / 3.0) * dimension**3
    verification_flops = 2.0 * (baseline_calls + hybrid_calls) * dimension**2
    charged_nonexact = (
        offline_flops + proposal_flops + verification_flops
    ) / exact_gradient_flops
    candidate_total = hybrid_calls + charged_nonexact
    expected_costs = {
        "exact_gradient_flops": exact_gradient_flops,
        "offline_pipeline_flops": offline_flops,
        "online_proposal_flops": proposal_flops,
        "conservative_sequential_verification_flops": verification_flops,
        "charged_nonexact_units": charged_nonexact,
        "baseline_total_units": float(baseline_calls),
        "candidate_total_units": candidate_total,
        "candidate_to_baseline_ratio": candidate_total / baseline_calls,
        "total_cost_slack_units": baseline_calls - candidate_total,
    }
    for key, expected in expected_costs.items():
        if abs(float(cost[key]) - expected) > 1.0e-10 * max(1.0, abs(expected)):
            raise ValueError(f"cost ledger mismatch: {key}")
    expected_gate = bool(
        baseline_calls - hybrid_calls >= int(cost["minimum_saved_calls"])
        and baseline_calls - candidate_total >= 0
    )
    if bool(cost["gate_accepts"]) != expected_gate:
        raise ValueError("gate decision does not match the recomputed cost ledger")
    return {
        "dimension": dimension,
        "baseline_calls": certificate["baseline_calls"],
        "hybrid_calls": certificate["hybrid_calls"],
        "condition_lower": str(condition_lower),
        "interval_precision": PRECISION,
        "crossings": results,
        "cost_ratio": candidate_total / baseline_calls,
        "source_rebuilt": source_rebuilt,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?", type=Path, default=DEFAULT_PAYLOAD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--source-root",
        type=Path,
        help="optional companion-project root used to rebuild data into matrices",
    )
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    summary = verify_payload(payload, source_root=args.source_root)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        condition_floor = floor(float(Fraction(summary["condition_lower"])) * 100) / 100
        print(
            "VERIFIED: ill-conditioned real-SPX certificate, "
            f"dimension {summary['dimension']}, calls "
            f"{summary['baseline_calls']}->{summary['hybrid_calls']}, "
            f"condition lower bound > {condition_floor:.2f}"
        )


if __name__ == "__main__":
    main()
