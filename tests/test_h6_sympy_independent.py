from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_independent_sympy_audit_binds_flagship_and_consumer() -> None:
    audit_path = ROOT / "results" / "h6_sympy_independent_consumer.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    source = json.loads(
        (ROOT / "certificates" / "h6_joint_only_pep_dual.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["source_payload_sha256"] == source["payload_sha256"]
    assert audit["certificate_count"] == 28
    assert audit["positive_ldl_pivot_count"] == 448
    consumer = ROOT / "tools" / "verify_h6_sympy_independent.py"
    assert audit["environment"]["consumer_sha256"] == sha256(
        consumer.read_bytes()
    ).hexdigest()
