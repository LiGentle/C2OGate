"""Frozen integrity checks for the SymPy exact cross-check."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "sympy_exact_crosscheck.json"


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_sympy_exact_crosscheck_is_complete_and_bound() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert sha256(canonical).hexdigest() == recorded
    assert payload["summary"]["certificate_count"] == 66
    assert payload["summary"]["positive_ldl_pivot_count"] == 1584
    environment = payload["environment"]
    assert environment["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_sympy_exact_crosscheck.py"
    )
    assert environment["input_file_sha256"] == _file_hash(
        ROOT / "certificates" / "h10_generic_pep_dual.json"
    )
