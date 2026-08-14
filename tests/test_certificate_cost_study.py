"""Checks for the frozen certificate-cost accounting study."""

from __future__ import annotations

from hashlib import sha256
import json
from math import ceil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "certificate_cost_study.json"
METRICS = ROOT / "paper_mpc" / "generated" / "metrics.tex"


def test_certificate_cost_ledger_is_complete() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert sha256(canonical).hexdigest() == recorded
    measurement = payload["measurement"]
    total = measurement["total_certificate_seconds"]
    assert total == (
        measurement["solver_and_rational_recovery_seconds"]
        + measurement["median_verification_seconds"]
    )
    saved = payload["declaration"]["saved_exact_calls_per_accepted_decision"]
    assert payload["declaration"]["zero_credit_online_rejection_funded"] is False
    for scenario in payload["scenarios"]:
        units = total / scenario["exact_oracle_seconds"]
        assert scenario["certificate_cost_exact_call_units"] == units
        assert scenario["one_shot_self_financing"] is (units <= saved)
        assert scenario["minimum_offline_reuses"] == max(1, ceil(units / saved))


def test_manuscript_cost_macros_use_the_frozen_total() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    scenarios = {
        row["exact_oracle_seconds"]: row for row in payload["scenarios"]
    }
    metrics = METRICS.read_text(encoding="utf-8")
    expected = {
        "CertificateUnitsTinyOracle": (
            f"{scenarios[0.0001]['certificate_cost_exact_call_units'] / 10**4:.3f}"
        ),
        "CertificateUnitsOneSecond": (
            f"{scenarios[1.0]['certificate_cost_exact_call_units']:.3f}"
        ),
        "CertificateUnitsTenSecond": (
            f"{scenarios[10.0]['certificate_cost_exact_call_units']:.3f}"
        ),
        "CertificateUnitsSixtySecond": (
            f"{scenarios[60.0]['certificate_cost_exact_call_units']:.3f}"
        ),
    }
    for name, value in expected.items():
        assert f"\\newcommand{{\\{name}}}{{{value}}}" in metrics
