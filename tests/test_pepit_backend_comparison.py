"""Integrity checks for the same-model C2OGate/PEPit comparison."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "pepit_backend_comparison.json"
EXPECTED_HASH = "14cb38b073bbd7a06e13a59b22751b535ce09e8df4aa9a2d4c04f814605c709e"


def test_pepit_comparison_is_complete_and_numerically_matched() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert recorded == EXPECTED_HASH == sha256(canonical).hexdigest()
    assert payload["environment"]["pepit"] == "0.5.1"
    installation = payload["environment"]["pepit_installation"]
    assert installation["pinned_requirement"] == "PEPit==0.5.1"
    assert installation["installer_metadata"] == "uv"
    assert not installation["direct_url_metadata_present"]
    assert payload["environment"]["runner_sha256"] == sha256(
        (ROOT / "experiments" / "run_pepit_backend_comparison.py").read_bytes()
    ).hexdigest()
    assert len(payload["runs"]) == 2 * 3 * 3
    for horizon in (2, 6, 10):
        c2o = [
            row["maximum_margin"]
            for row in payload["runs"]
            if row["backend"] == "c2ogate" and row["horizon"] == horizon
        ]
        pepit = [
            row["maximum_margin"]
            for row in payload["runs"]
            if row["backend"] == "pepit" and row["horizon"] == horizon
        ]
        assert len(c2o) == len(pepit) == 3
        assert max(abs(left - right) for left, right in zip(c2o, pepit, strict=True)) < 1e-6
    h10 = next(
        row for row in payload["comparison_to_pepit"] if row["horizon"] == 10
    )
    assert 1.4 < h10["end_to_end_ratio_c2ogate_over_pepit"] < 1.7
    extras = h10["median_extra_seconds_c2ogate_minus_pepit"]
    assert extras["model_build_seconds"] > 0
    assert extras["framework_and_canonicalization_seconds"] > 0
    assert extras["solver_numeric_seconds"] < 0
