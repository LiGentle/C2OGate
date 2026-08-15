"""Accounting checks for the natural-H=10 proof suite."""

from __future__ import annotations

from hashlib import sha256
import json
from math import ceil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "h10_certificate_cost_study.json"
METRICS = ROOT / "paper_mpc" / "generated" / "metrics.tex"


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_h10_cost_ledger_is_hash_bound_and_complete() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert sha256(canonical).hexdigest() == recorded
    measurement = payload["measurement"]
    assert measurement["total_certificate_seconds"] == (
        measurement["solver_and_rational_recovery_seconds"]
        + measurement["median_verification_seconds"]
    )
    declaration = payload["declaration"]
    budget = declaration["certificate_budget_exact_call_units"]
    assert budget == (
        declaration["saved_exact_calls_per_accepted_decision"]
        - declaration["base_nonexact_cost_exact_call_units"]
    ) == 0.6
    assert declaration["zero_credit_online_rejection_funded"] is False
    for scenario in payload["scenarios"]:
        units = (
            measurement["total_certificate_seconds"]
            / scenario["exact_oracle_seconds"]
        )
        assert scenario["certificate_cost_exact_call_units"] == units
        assert scenario["one_shot_self_financing"] is (units <= budget)
        assert scenario["minimum_offline_reuses"] == max(
            1, ceil(units / budget)
        )
    environment = payload["environment"]
    assert environment["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_h10_certificate_cost_study.py"
    )
    assert environment["generator_sha256"] == _file_hash(
        ROOT / "experiments" / "generate_h10_generic_pep_dual_certificate.py"
    )
    assert environment["verifier_sha256"] == _file_hash(
        ROOT / "tools" / "verify_h10_generic_pep_dual.py"
    )
    certificate = json.loads(
        (ROOT / "certificates" / "h10_generic_pep_dual.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        environment["certificate_payload_sha256"]
        == certificate["payload_sha256"]
    )


def test_h10_cost_macros_use_the_frozen_payload() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    measurement = payload["measurement"]
    scenarios = {
        row["exact_oracle_seconds"]: row for row in payload["scenarios"]
    }
    metrics = METRICS.read_text(encoding="utf-8")
    assert (
        f"\\newcommand{{\\HtenCertificateTotalSeconds}}"
        f"{{{measurement['total_certificate_seconds']:.1f}}}"
    ) in metrics
    assert (
        f"\\newcommand{{\\HtenCertificateBreakEvenSixtySeconds}}"
        f"{{{scenarios[60.0]['minimum_offline_reuses']}}}"
    ) in metrics
