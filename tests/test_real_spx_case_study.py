"""Exact integrity checks for the frozen real-SPX bridge study."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
RESULT = ROOT / "results" / "real_spx_two_oracle_study.json"
EXPECTED_HASH = "585dd81579978dc14be1265d4ce7afb1c0a6ccf684be0f184d05c6952c6d2a46"


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _matvec(matrix: list[list[Fraction]], vector: list[Fraction]) -> list[Fraction]:
    return [
        sum(
            (value * coordinate for value, coordinate in zip(row, vector, strict=True)),
            Fraction(0),
        )
        for row in matrix
    ]


def _residual_squared(
    matrix: list[list[Fraction]], linear: list[Fraction], point: list[Fraction]
) -> Fraction:
    residual = [
        value - target
        for value, target in zip(_matvec(matrix, point), linear, strict=True)
    ]
    return sum((value * value for value in residual), Fraction(0))


def _calls(
    matrix: list[list[Fraction]],
    linear: list[Fraction],
    start: list[Fraction],
    step: Fraction,
    tolerance_squared: Fraction,
) -> tuple[int, Fraction, Fraction]:
    point = start.copy()
    previous = Fraction(0)
    for calls in range(201):
        squared = _residual_squared(matrix, linear, point)
        if squared <= tolerance_squared:
            return calls, previous, squared
        previous = squared
        residual = [
            value - target
            for value, target in zip(_matvec(matrix, point), linear, strict=True)
        ]
        point = [
            coordinate - step * value
            for coordinate, value in zip(point, residual, strict=True)
        ]
    raise AssertionError("trajectory did not terminate")


def _load() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_real_spx_payload_and_inputs_are_hash_bound() -> None:
    payload = _load()
    recorded = payload.pop("payload_sha256")
    assert recorded == EXPECTED_HASH
    assert sha256(_canonical(payload)).hexdigest() == recorded
    environment = payload["environment"]
    assert environment["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_real_spx_case_study.py"
    )
    for relative, expected in environment["input_sha256"].items():
        source = PROJECT_ROOT / relative
        if source.is_file():
            assert _file_hash(source) == expected


def test_fraction_certificate_replays_both_stopping_times_exactly() -> None:
    study = _load()["theorem_compatible_surface"]
    objective = study["objective"]
    certificate = study["certificate"]
    matrix = [[Fraction(value) for value in row] for row in objective["exact_hessian"]]
    linear = [Fraction(value) for value in objective["exact_linear"]]
    candidate = [Fraction(value) for value in study["cheap_oracle"]["candidate"]]
    lower = []
    upper = []
    for i, row in enumerate(matrix):
        radius = sum((abs(value) for j, value in enumerate(row) if i != j), Fraction(0))
        lower.append(row[i] - radius)
        upper.append(row[i] + radius)
    assert min(lower) == Fraction(certificate["mu_gershgorin"]) > 0
    assert max(upper) == Fraction(certificate["smoothness_gershgorin"])

    tolerance_squared = Fraction(certificate["tolerance_squared"])
    step = Fraction(certificate["step_size"])
    baseline = _calls(
        matrix, linear, [Fraction(0)] * len(linear), step, tolerance_squared
    )
    hybrid = _calls(matrix, linear, candidate, step, tolerance_squared)
    assert baseline == (
        certificate["baseline_calls"],
        Fraction(certificate["baseline_preterminal_residual_squared"]),
        Fraction(certificate["baseline_terminal_residual_squared"]),
    )
    assert hybrid == (
        certificate["hybrid_calls"],
        Fraction(certificate["hybrid_preterminal_residual_squared"]),
        Fraction(certificate["hybrid_terminal_residual_squared"]),
    )
    assert baseline[1] > tolerance_squared >= baseline[2]
    assert hybrid[1] > tolerance_squared >= hybrid[2]
    assert baseline[0] - hybrid[0] == certificate["exact_call_saving"] == 2


def test_real_cost_pipeline_and_application_bridge_are_honest() -> None:
    payload = _load()
    surface = payload["theorem_compatible_surface"]
    data = surface["data"]
    cost = surface["cost_accounting"]
    assert data["raw_quote_count"] == 17_403
    assert data["filtered_quote_count"] == 6_162
    assert data["expiry_count"] == 38
    assert not cost["cold_start_dominates"]
    assert cost["break_even_reuses"] == 57
    assert cost["amortized_dominates"]
    assert cost["cold_start_total_units"] > cost["cold_start_baseline_units"]
    assert cost["amortized_total_units_at_break_even"] <= 7.0
    assert cost["measured_break_even_reuses"] >= cost["break_even_reuses"]

    bridge = payload["production_grid_bridge"]
    assert bridge["grid"] == "101x101"
    assert bridge["repeat_count"] == 2
    assert bridge["both_exactly_stationarity_certified"]
    assert bridge["runtime_speedup"] > 1.0
    assert bridge["exact_adjoint_change_fraction"] > 0.0
    assert bridge["theorem_status"].startswith("out of class")
    production = (
        PROJECT_ROOT
        / "HWC_study"
        / "production_real"
        / "results"
        / "real_market_results.json"
    )
    if production.is_file():
        source = json.loads(production.read_text(encoding="utf-8"))
        source_hash = source.pop("payload_sha256")
        assert sha256(_canonical(source)).hexdigest() == source_hash
        assert source_hash == bridge["source_payload_sha256"]
    else:
        assert bridge["source_payload_sha256"] == (
            "abb4b8cbb31ec8a6fa6a60ee7d08590a290c43d0a15bc0b801518b6ce9ec3a1b"
        )
