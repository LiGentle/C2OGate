"""Integrity checks for the infinite-class joint-only PEP certificate."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.verify_full_class_joint_only_pep_dual import verify_payload


ROOT = Path(__file__).resolve().parents[1]
CERTIFICATE = ROOT / "certificates" / "full_class_joint_only_pep_dual.json"
EXPECTED_HASH = "9848dac60c670d6ac9f3f2ca3ad57503ae75d9ac43da09b21b7cdd66d8e7acda"


def _load() -> dict:
    return json.loads(CERTIFICATE.read_text(encoding="utf-8"))


def _rehash(payload: dict) -> None:
    payload.pop("payload_sha256", None)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    payload["payload_sha256"] = sha256(canonical).hexdigest()


def test_full_class_joint_only_suite_verifies_exactly() -> None:
    payload = _load()
    assert payload["payload_sha256"] == EXPECTED_HASH
    result = verify_payload(payload, root=ROOT)
    assert result["certificate_count"] == 10
    assert result["positive_ldl_pivots"] == 100
    assert result["witness_pairs"] == [[2, 1], [1, 0]]
    assert Fraction(result["maximum_certified_upper_bound"]) < 0
    sensitivity = {
        row["contract_radius"]: row
        for row in payload["diagnostic_contract_radius_sensitivity"]
    }
    assert sensitivity["1/50"]["negative_bad_cell_count"] == 10
    assert sensitivity["3/100"]["negative_bad_cell_count"] == 9


@pytest.mark.parametrize("target", ["multiplier", "bound", "marginal", "cell"])
def test_rehashed_full_class_tampering_is_rejected(target: str) -> None:
    forged = deepcopy(_load())
    certificate = forged["certificates"][0]
    if target == "multiplier":
        key = next(iter(certificate["dual"]["inequality_multipliers"]))
        certificate["dual"]["inequality_multipliers"][key] = "0"
    elif target == "bound":
        certificate["dual"]["certified_upper_bound"] = "0"
    elif target == "marginal":
        forged["marginal_certificate"]["candidate_upper_calls"] = 0
    else:
        certificate["cell"] = [3, 3]
    _rehash(forged)
    with pytest.raises(ValueError):
        verify_payload(forged, root=ROOT)
