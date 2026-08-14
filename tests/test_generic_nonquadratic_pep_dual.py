"""Integrity tests for the recovered generic nonquadratic PEP dual."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.verify_generic_nonquadratic_pep_dual import verify_payload


ROOT = Path(__file__).resolve().parents[1]
CERTIFICATE = ROOT / "certificates" / "generic_nonquadratic_pep_dual.json"
EXPECTED_HASH = "538b08d7ef2c58156a3c42228307a6f236b75ca285ed25becc6470df7cf1505d"


def _load() -> dict:
    return json.loads(CERTIFICATE.read_text(encoding="utf-8"))


def _rehash(payload: dict) -> None:
    payload.pop("payload_sha256", None)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    payload["payload_sha256"] = sha256(canonical).hexdigest()


def test_frozen_generic_dual_verifies() -> None:
    payload = _load()
    assert payload["payload_sha256"] == EXPECTED_HASH
    result = verify_payload(payload, root=ROOT)
    assert result["certificate_count"] == 10
    assert result["cells"][-1] == [3, 3]
    assert result["positive_leading_minors"] == 100


@pytest.mark.parametrize("target", ["multiplier", "slack", "bound", "cell"])
def test_rehashed_generic_dual_tampering_is_rejected(target: str) -> None:
    forged = deepcopy(_load())
    certificate = forged["certificates"][0]
    if target == "multiplier":
        key = next(iter(certificate["dual"]["inequality_multipliers"]))
        certificate["dual"]["inequality_multipliers"][key] = "0"
    elif target == "slack":
        certificate["dual"]["slack_matrix"][0][0] = "0"
    elif target == "bound":
        certificate["dual"]["certified_upper_bound"] = "0"
    else:
        certificate["cell"] = [3, 3]
    _rehash(forged)
    with pytest.raises(ValueError):
        verify_payload(forged, root=ROOT)
