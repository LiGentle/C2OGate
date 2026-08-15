"""Integrity checks for the frozen two-oracle computational study."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results" / "study.json"


def _load() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


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


def test_frozen_payload_hash_is_self_consistent() -> None:
    payload = _load()
    recorded = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == recorded
    assert recorded == (
        "8d64b5e68e219176a6143a399af1b9884fda7a045391ff32a11866ef9d4f478c"
    )


def test_frozen_source_and_runner_hashes_match() -> None:
    environment = _load()["environment"]
    assert environment["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_study.py"
    )
    for relative, expected in environment["source_sha256"].items():
        assert _file_hash(ROOT / relative) == expected


def test_frozen_study_has_no_certified_gate_violations() -> None:
    payload = _load()
    assert payload["schema"] == "c2o-quadratic-study-v1"
    assert len(payload["records"]) == 2000
    summary = payload["summary"]
    assert summary["gate_accept_count"] == 349
    assert summary["contract_violation_count"] == 0
    assert summary["gate_cost_dominance_violation_count"] == 0
    assert summary["gate_exact_call_reduction_violation_count"] == 0
    assert math.isclose(summary["gate_accept_rate"], 0.1745)
    assert math.isclose(summary["gated_cost_ratio"]["mean"], 0.9394063809476988)
    assert math.isclose(summary["always_cost_ratio"]["mean"], 0.7291155026842021)
    assert math.isclose(summary["posthoc_cost_ratio"]["mean"], 0.7291833380500558)
    assert math.isclose(summary["always_worse_fraction"], 0.026)
    assert math.isclose(summary["posthoc_worse_fraction"], 0.027)
    for row in payload["records"]:
        if row["gate_accept"]:
            assert row["gated_total_cost"] <= row["baseline_actual_calls"]
            assert row["post_actual_calls"] <= row["baseline_actual_calls"] - 1
