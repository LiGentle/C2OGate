"""Integrity and adversarial checks for the exact joint-only example."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.verify_joint_only_shift_certificate import verify_payload


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "certificates" / "joint_only_shift_certificate.json"
EXPECTED_HASH = "2b82b861ea19f5d2fd2bc2f7bf2a927e19adbd84d9baf63b2b128183fcc3d3ca"


def _load() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def _rehash(payload: dict) -> None:
    payload.pop("payload_sha256", None)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    payload["payload_sha256"] = sha256(canonical).hexdigest()


def test_joint_accepts_while_rectangle_rejects() -> None:
    payload = _load()
    assert payload["payload_sha256"] == EXPECTED_HASH
    result = verify_payload(payload, root=ROOT)
    assert result["pairs"] == [[3, 2], [1, 0]]
    assert result["joint_accept"]
    assert not result["rectangle_accept"]


def test_rehashed_pair_tampering_is_rejected() -> None:
    payload = deepcopy(_load())
    payload["witnesses"][0]["hybrid_calls"] += 1
    _rehash(payload)
    with pytest.raises(ValueError):
        verify_payload(payload, root=ROOT)
