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
EXPECTED_HASH = "4d383dc56ff5751761f7dc86cffd39d351ed255c6bcd2daf5ef6b3a63345766f"


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
    assert result["cell"] == [3, 3]
    assert result["positive_leading_minors"] == 10


@pytest.mark.parametrize("target", ["multiplier", "slack", "bound", "cell"])
def test_rehashed_generic_dual_tampering_is_rejected(target: str) -> None:
    forged = deepcopy(_load())
    if target == "multiplier":
        key = next(iter(forged["dual"]["inequality_multipliers"]))
        forged["dual"]["inequality_multipliers"][key] = "0"
    elif target == "slack":
        forged["dual"]["slack_matrix"][0][0] = "0"
    elif target == "bound":
        forged["dual"]["certified_upper_bound"] = "0"
    else:
        forged["declaration"]["cell"] = [2, 2]
    _rehash(forged)
    with pytest.raises(ValueError):
        verify_payload(forged, root=ROOT)
