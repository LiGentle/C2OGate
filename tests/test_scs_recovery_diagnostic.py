"""Integrity checks for the SCS recovery diagnostic."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "scs_recovery_diagnostic.json"


def test_scs_recovery_payload_is_self_consistent() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert sha256(canonical).hexdigest() == recorded
    summary = payload["summary"]
    assert summary["cell_count"] == 9
    assert summary["recovery_success_count"] + summary["recovery_failure_count"] == 9
