from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "h6_certificate_cost_study.json"
CERTIFICATE = ROOT / "certificates" / "h6_joint_only_pep_dual.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_h6_certificate_cost_payload_is_bound_and_repeated() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    claimed = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == claimed
    assert payload["schema"] == "c2o-h6-certificate-cost-study-v1"
    assert payload["measurement"]["verification_repeats"] == 3
    assert len(payload["measurement"]["verification_seconds"]) == 3
    assert payload["environment"]["certificate_file_sha256"] == sha256(
        CERTIFICATE.read_bytes()
    ).hexdigest()


def test_h6_cost_has_explicit_funding_boundary() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    scenarios = {
        row["exact_oracle_seconds"]: row for row in payload["scenarios"]
    }
    assert not scenarios[1.0]["one_shot_self_financing"]
    assert scenarios[3600.0]["one_shot_self_financing"]
    assert not payload["declaration"]["zero_credit_online_rejection_funded"]
