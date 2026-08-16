from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "certificates" / "exact_shift_joint_only_h10.json"
VERIFIER = ROOT / "tools" / "verify_exact_shift_joint_only_h10.py"


def _canonical(payload: dict) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("payload_sha256", None)
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_exact_shift_joint_only_h10_verifier() -> None:
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), str(PAYLOAD), "--root", str(ROOT)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "66/66 bad cells excluded" in completed.stdout
    assert "rectangle >= 4" in completed.stdout


def test_exact_shift_joint_only_h10_tampering_fails(tmp_path: Path) -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    payload["marginal_rectangle"]["candidate_upper_calls_lower_witness"] = 3
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), str(tampered), "--root", str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "candidate marginal witness" in completed.stderr
