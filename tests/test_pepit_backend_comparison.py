"""Integrity checks for the same-model C2OGate/PEPit comparison."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "pepit_backend_comparison.json"
EXPECTED_HASH = "89dc25fffbbb5e29bc0301e37fae2315f9b7a8fd208b8aaee104b01ff52fff0c"


def test_pepit_comparison_is_complete_and_numerically_matched() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert recorded == EXPECTED_HASH == sha256(canonical).hexdigest()
    assert payload["environment"]["pepit"] == "0.5.1"
    assert payload["environment"]["runner_sha256"] == sha256(
        (ROOT / "experiments" / "run_pepit_backend_comparison.py").read_bytes()
    ).hexdigest()
    assert len(payload["runs"]) == 2 * 3 * 3
    for horizon in (2, 6, 10):
        c2o = [
            row["maximum_margin"]
            for row in payload["runs"]
            if row["backend"] == "c2ogate" and row["horizon"] == horizon
        ]
        pepit = [
            row["maximum_margin"]
            for row in payload["runs"]
            if row["backend"] == "pepit" and row["horizon"] == horizon
        ]
        assert len(c2o) == len(pepit) == 3
        assert max(abs(left - right) for left, right in zip(c2o, pepit, strict=True)) < 1e-6
