from __future__ import annotations

import json
from pathlib import Path

from tools.verify_h6_joint_only_pep_dual import verify_payload


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "certificates" / "h6_joint_only_pep_dual.json"


def test_h6_joint_only_payload_verifies() -> None:
    result = verify_payload(
        json.loads(PAYLOAD.read_text(encoding="utf-8")), root=ROOT
    )
    assert result["certificate_count"] == 28
    assert result["positive_ldl_pivots"] == 448
    assert result["witness_pairs"] == [[1, 0], [2, 1]]


def test_h6_joint_only_tampering_fails_closed() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    payload["joint_certificate"]["rectangle_accept"] = True
    try:
        verify_payload(payload)
    except ValueError:
        return
    raise AssertionError("tampered H=6 payload was accepted")
