"""Fast integrity checks for the five-profile H=10 family."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_h10_generic_pep_dual as base  # noqa: E402


MANIFEST = ROOT / "certificates" / "h10_envelope_family.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_h10_envelope_manifest_and_bindings() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == recorded
    assert payload["declaration"]["profile_count"] == 5
    assert payload["declaration"]["independently_recovered_profile_count"] == 3
    for row in payload["sources"]:
        source_path = ROOT / row["path"]
        source = json.loads(source_path.read_text(encoding="utf-8"))
        assert sha256(source_path.read_bytes()).hexdigest() == row["file_sha256"]
        assert source["payload_sha256"] == row["payload_sha256"]


def test_representative_cells_from_new_profiles_verify_exactly() -> None:
    original = base.PARAMETERS
    try:
        for profile in ("candidate_heavy", "tight_contract"):
            payload = json.loads(
                (ROOT / "certificates" / f"h10_{profile}_pep_dual.json").read_text(
                    encoding="utf-8"
                )
            )
            base.PARAMETERS = {
                key: Fraction(value)
                for key, value in payload["parameters"].items()
            }
            for certificate in (
                payload["certificates"][0],
                payload["certificates"][32],
                payload["certificates"][-1],
            ):
                upper, pivots = base._verify_certificate(certificate)
                assert upper < 0
                assert pivots == 24
    finally:
        base.PARAMETERS = original
