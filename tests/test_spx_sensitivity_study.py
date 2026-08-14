"""Integrity checks for the frozen SPX sensitivity grid."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "spx_sensitivity_study.json"


def test_spx_sensitivity_payload_and_ledger() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert sha256(canonical).hexdigest() == recorded
    assert payload["summary"]["configuration_count"] == 27
    assert len(payload["records"]) == 27
    for row in payload["records"]:
        assert row["saved_calls"] == row["baseline_calls"] - row["hybrid_calls"]
        expected = (
            row["hybrid_calls"] + row["charged_nonexact_units"]
        ) / row["baseline_calls"]
        assert row["total_cost_ratio"] == expected
        assert row["cost_gate_accepts"] is (
            row["saved_calls"] >= 1 and expected <= 1.0
        )
