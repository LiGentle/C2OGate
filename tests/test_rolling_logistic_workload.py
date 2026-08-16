from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
from typing import Any

from experiments.run_rolling_logistic_workload import run_workload


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "rolling_logistic_workload.json"
CERTIFICATE = ROOT / "certificates" / "h6_joint_only_pep_dual.json"


_PLATFORM_DERIVED_RATIONAL_FIELDS = {
    "contract_residual_squared_exact",
    "exact_maximum_feature_row_squared_norm",
    "exact_smoothness_upper",
    "gradient_squared_norm_exact",
    "proposal_squared_norm_exact",
}
_FLOAT_REL_TOL = 1e-12
_FLOAT_ABS_TOL = 1e-14


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _assert_cross_platform_regeneration(
    regenerated: Any,
    frozen: Any,
    *,
    path: tuple[str, ...] = (),
) -> None:
    """Compare stable semantics exactly and BLAS-derived diagnostics numerically."""
    if isinstance(frozen, dict):
        assert isinstance(regenerated, dict), ".".join(path)
        assert regenerated.keys() == frozen.keys(), ".".join(path)
        for key in frozen:
            _assert_cross_platform_regeneration(
                regenerated[key],
                frozen[key],
                path=(*path, key),
            )
        return

    if isinstance(frozen, list):
        assert isinstance(regenerated, list), ".".join(path)
        assert len(regenerated) == len(frozen), ".".join(path)
        for index, (regenerated_item, frozen_item) in enumerate(
            zip(regenerated, frozen, strict=True)
        ):
            _assert_cross_platform_regeneration(
                regenerated_item,
                frozen_item,
                path=(*path, str(index)),
            )
        return

    field = path[-1] if path else ""
    if field in _PLATFORM_DERIVED_RATIONAL_FIELDS:
        regenerated_fraction = Fraction(regenerated)
        frozen_fraction = Fraction(frozen)
        scale = max(abs(regenerated_fraction), abs(frozen_fraction), Fraction(1))
        assert (
            abs(regenerated_fraction - frozen_fraction)
            <= Fraction(1, 10**12) * scale
        ), ".".join(path)
        return

    if isinstance(frozen, float):
        assert isinstance(regenerated, float), ".".join(path)
        assert isclose(
            regenerated,
            frozen,
            rel_tol=_FLOAT_REL_TOL,
            abs_tol=_FLOAT_ABS_TOL,
        ), ".".join(path)
        return

    # Booleans, counts, decisions, reasons, and other semantic fields remain
    # bit-for-bit checks.  In particular, a platform-dependent threshold flip
    # cannot be hidden by the numerical tolerances above.
    assert regenerated == frozen, ".".join(path)


def test_rolling_workload_payload_integrity() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    claimed = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == claimed
    assert payload["schema"] == "c2o-rolling-logistic-workload-v5"
    assert payload["evidence"]["certificate_file_sha256"] == sha256(
        CERTIFICATE.read_bytes()
    ).hexdigest()


def test_short_transcript_gate_is_nonvacuous_and_safe() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert 0 < summary["accepted_episode_count"] < payload["configuration"][
        "episode_count"
    ]
    assert summary["accepted_safety_violation_count"] == 0
    assert summary["rejected_episode_count"] == 0
    assert summary["uncertified_episode_count"] == 12
    assert summary["three_valued_attempt_count"] == 30
    assert 0 < summary["proposal_attempt_count"] < payload["configuration"][
        "episode_count"
    ]
    assert summary["saved_exact_calls_before_cheap_cost"] > 0
    assert summary["warm_cost_ratio"] < 1
    for record in payload["records"]:
        if record["accepted_from_short_transcript"]:
            assert record["proposal_attempted_after_free_prefilter"]
            assert 0.54 <= record["proposal_norm"] <= 0.56
            assert record["contract_residual"] <= 0.01
            assert record["distance_bound"] <= 1.8
            assert record["proposal_band_passed_exactly"]
            assert record["residual_ball_passed_exactly"]
            assert record["distance_bound_passed_exactly"]
            assert (
                record["candidate_calls_post_decision"]
                < record["baseline_calls_post_decision"]
            )


def test_cold_ledger_reports_funding_boundary() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    scenarios = {
        row["exact_oracle_seconds"]: row
        for row in payload["cold_cost_scenarios"]
    }
    assert not scenarios[1.0]["observed_batch_self_financing"]
    assert scenarios[60.0]["observed_batch_self_financing"]
    assert scenarios[60.0]["break_even_episode_count"] <= 256
    assert not payload["declaration"]["zero_credit_first_decision_self_financing"]


def test_joint_gate_changes_the_marginal_decision() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["accepted_episode_count"] > 0
    assert summary["marginal_gate_accepted_episode_count"] == 0
    assert summary["marginal_gate_cost_ratio"] > summary["warm_cost_ratio"]
    assert summary["always_query_pointwise_overrun_count"] > 0
    assert summary["always_query_risk_break_even_penalty_exact_units_per_overrun"] > 0
    assert summary["greedy_prefilter_accept_count"] == summary[
        "proposal_attempt_count"
    ]
    assert summary["greedy_prefilter_cost_ratio"] < summary["warm_cost_ratio"]
    assert summary["greedy_prefilter_candidate_nonimprovement_count"] == 0
    assert summary["greedy_prefilter_pointwise_overrun_count"] == 0
    assert summary["exact_membership_decision_count"] == 512


def test_rolling_workload_regenerates_deterministically() -> None:
    frozen = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    regenerated = run_workload()
    assert regenerated["configuration"] == frozen["configuration"]
    _assert_cross_platform_regeneration(
        regenerated["summary"], frozen["summary"], path=("summary",)
    )
    _assert_cross_platform_regeneration(
        regenerated["cold_cost_scenarios"],
        frozen["cold_cost_scenarios"],
        path=("cold_cost_scenarios",),
    )
    _assert_cross_platform_regeneration(
        regenerated["records"], frozen["records"], path=("records",)
    )
