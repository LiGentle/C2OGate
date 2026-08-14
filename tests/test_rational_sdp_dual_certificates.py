from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CERTIFICATE = ROOT / "certificates" / "rational_sdp_dual_certificates.json"
VERIFIER = ROOT / "tools" / "verify_rational_dual_certificates.py"
EXPECTED_PAYLOAD_HASH = (
    "1b9f47487cfc4fc9369695f0b6130da253a4074fde91aa62aef0ef89ca2d17b0"
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _run_verifier(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(path), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_frozen_rational_certificates_verify_exactly() -> None:
    process = _run_verifier(CERTIFICATE)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["verified"] is True
    assert result["payload_sha256"] == EXPECTED_PAYLOAD_HASH
    assert result["instance_count"] == 3
    assert result["certificate_count"] == 9
    assert result["principal_minor_count"] == 87
    assert [item["minimum_strict_gap"] for item in result["instances"]] == [
        "5/256",
        "1377/65536",
        "281441/25000000",
    ]
    assert [item["certified_call_saving"] for item in result["instances"]] == [
        2,
        3,
        4,
    ]
    assert all(
        item["certified_cost_slack"] == "1/2" for item in result["instances"]
    )
    assert all(
        item["verified_current_norm_squared"] == "1"
        and item["verified_shift_identity"] is True
        for item in result["instances"]
    )


def test_payload_binds_generator_and_verifier() -> None:
    payload = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    assert payload["payload_sha256"] == EXPECTED_PAYLOAD_HASH
    assert payload["environment"]["generator_sha256"] == sha256(
        (ROOT / "experiments" / "generate_rational_dual_certificates.py").read_bytes()
    ).hexdigest()
    assert payload["environment"]["verifier_sha256"] == sha256(
        VERIFIER.read_bytes()
    ).hexdigest()


def test_exact_verifier_rejects_rehashed_dual_tampering(tmp_path: Path) -> None:
    payload = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    del payload["payload_sha256"]
    slack = payload["instances"][0]["residual_dual_certificates"][0]["dual"][
        "slack_matrix"
    ]
    slack[0][0] = str(Fraction(slack[0][0]) + 1)
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    process = _run_verifier(tampered)
    assert process.returncode != 0
    assert "dual stationarity identity fails" in process.stderr


def test_exact_verifier_rejects_rehashed_nonunit_witness(tmp_path: Path) -> None:
    payload = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    del payload["payload_sha256"]
    payload["instances"][0]["current_displacement"][0] = "0"
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    tampered = tmp_path / "nonunit-witness.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    process = _run_verifier(tampered)
    assert process.returncode != 0
    assert "does not have exact unit norm" in process.stderr
