"""Integrity and tampering tests for the flagship marginal certificate."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_h10_marginal_pep_dual import verify_payload  # noqa: E402


PAYLOAD = ROOT / "certificates" / "h10_marginal_pep_dual.json"


def _load() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_h10_marginal_certificate_verifies() -> None:
    result = verify_payload(_load(), root=ROOT)
    assert result["rectangle_gate_value"] == 0
    assert result["positive_ldl_pivots"] == 4


def test_h10_marginal_tampering_is_rejected() -> None:
    payload = deepcopy(_load())
    payload["exact_consequences"]["candidate_marginal_upper"] = 1
    with pytest.raises(ValueError, match="payload hash"):
        verify_payload(payload)
