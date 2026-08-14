"""Integrity tests for the direct nonquadratic joint-PEP acceptance."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.verify_nonlinear_joint_pep_acceptance import verify_payload


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results" / "nonlinear_joint_pep_acceptance.json"
EXPECTED_HASH = "d973a0da85b227881782a7a253e555ef99aa4e108109abbe4380c88b180f76f8"


def _load() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _rehash(payload: dict) -> None:
    payload.pop("payload_sha256", None)
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()


def test_frozen_nonlinear_acceptance_verifies() -> None:
    payload = _load()
    assert payload["payload_sha256"] == EXPECTED_HASH
    result = verify_payload(payload, root=ROOT)
    assert result["strict_pair"] == [1, 0]
    assert result["bad_cells_excluded"] == 10
    assert result["joint_accept"] is True
    assert result["dimension"] == 2
    assert result["natural_horizon"] == 2
    assert result["audit_horizon"] == 3


@pytest.mark.parametrize("target", ["candidate", "bound", "cell", "cost"])
def test_rehashed_tampering_is_rejected(target: str) -> None:
    forged = deepcopy(_load())
    if target == "candidate":
        forged["actual_instance"]["candidate_y"][0] = "0.04"
    elif target == "bound":
        forged["exact_certificate"]["candidate_gradient_upper"] = "1/10"
    elif target == "cell":
        forged["exact_certificate"]["cost_violating_cells"].pop()
    else:
        forged["gate"]["declared_all_in_cost_ratio"] = 0.4
    _rehash(forged)
    with pytest.raises(ValueError):
        verify_payload(forged)
