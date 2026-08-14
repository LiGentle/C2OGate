#!/usr/bin/env python3
"""Bind the MPC manuscript to the frozen transcript-PEP payload."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "transcript_pep_study.json"
SCALING_PAYLOAD = ROOT / "results" / "pep_scaling_study.json"
GENERIC_SCALING_PAYLOAD = ROOT / "results" / "generic_pep_scaling_study.json"
NONLINEAR_PEP_PAYLOAD = ROOT / "results" / "nonlinear_joint_pep_acceptance.json"
REAL_SPX_PAYLOAD = ROOT / "results" / "real_spx_two_oracle_study.json"
REAL_SPX_POSITIVE_PAYLOAD = ROOT / "results" / "real_spx_ill_conditioned_study.json"
ACCOUNTING_PAYLOAD = ROOT / "results" / "study.json"
RATIONAL_CERTIFICATES = ROOT / "certificates" / "rational_sdp_dual_certificates.json"
RATIONAL_VERIFIER = ROOT / "tools" / "verify_rational_dual_certificates.py"
REAL_SPX_POSITIVE_VERIFIER = (
    ROOT / "tools" / "verify_real_spx_ill_conditioned_certificate.py"
)
NONLINEAR_PEP_VERIFIER = ROOT / "tools" / "verify_nonlinear_joint_pep_acceptance.py"
OUTPUT = ROOT / "paper_mpc" / "generated" / "metrics.tex"


def _pct(value: float) -> str:
    return f"{100.0 * value:.1f}\\%"


def _tex_fraction(value: str) -> str:
    if "/" not in value:
        return value
    numerator, denominator = value.split("/", maxsplit=1)
    return f"\\frac{{{numerator}}}{{{denominator}}}"


def _load_hashed_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if sha256(canonical).hexdigest() != recorded:
        raise ValueError(f"payload hash mismatch: {path}")
    payload["payload_sha256"] = recorded
    return payload


def main() -> None:
    payload = _load_hashed_payload(PAYLOAD)
    scaling_payload = _load_hashed_payload(SCALING_PAYLOAD)
    generic_scaling_payload = _load_hashed_payload(GENERIC_SCALING_PAYLOAD)
    nonlinear_pep_payload = _load_hashed_payload(NONLINEAR_PEP_PAYLOAD)
    real_spx_payload = _load_hashed_payload(REAL_SPX_PAYLOAD)
    real_spx_positive_payload = _load_hashed_payload(REAL_SPX_POSITIVE_PAYLOAD)
    accounting_payload = _load_hashed_payload(ACCOUNTING_PAYLOAD)
    certificate_process = subprocess.run(
        [
            sys.executable,
            str(RATIONAL_VERIFIER),
            str(RATIONAL_CERTIFICATES),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    certificate_summary = json.loads(certificate_process.stdout)
    subprocess.run(
        [
            sys.executable,
            str(REAL_SPX_POSITIVE_VERIFIER),
            str(REAL_SPX_POSITIVE_PAYLOAD),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(NONLINEAR_PEP_VERIFIER),
            str(NONLINEAR_PEP_PAYLOAD),
            "--root",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = payload["summary"]
    accounting = accounting_payload["summary"]
    gap = summary["rectangle_minus_joint_difference"]
    slack = summary["joint_only_cost_slack"]
    scaling = {row["horizon"]: row for row in scaling_payload["reduced_horizons"]}
    dense_scaling = scaling_payload["dense_reference"]
    generic = generic_scaling_payload["summary"]
    generic_status_counts: dict[str, int] = {}
    for cell in generic_scaling_payload["cells"]:
        status = cell["status"]
        generic_status_counts[status] = generic_status_counts.get(status, 0) + 1
    real_surface = real_spx_payload["theorem_compatible_surface"]
    real_data = real_surface["data"]
    real_certificate = real_surface["certificate"]
    real_cost = real_surface["cost_accounting"]
    production = real_spx_payload["production_grid_bridge"]
    positive_certificate = real_spx_positive_payload["certificate"]
    positive_cost = real_spx_positive_payload["cost_accounting"]
    positive_timing = real_spx_positive_payload["timing"]
    metrics = {
        "TranscriptCases": f"{summary['case_count']:,}",
        "JointAcceptCount": str(summary["joint_accept_count"]),
        "JointAcceptRate": _pct(summary["joint_accept_rate"]),
        "RectangleAcceptCount": str(summary["rectangle_accept_count"]),
        "RectangleAcceptRate": _pct(summary["rectangle_accept_rate"]),
        "JointOnlyCount": str(summary["joint_only_accept_count"]),
        "JointOnlyRate": _pct(summary["joint_only_accept_rate"]),
        "JointViolationCount": str(summary["accepted_joint_violation_count"]),
        "MedianRectangleGap": f"{gap['median']:.1f}",
        "MeanRectangleGap": f"{gap['mean']:.3f}",
        "MedianJointOnlySlack": f"{slack['median']:.3f}",
        "PepCells": str(summary["pep_cell_count"]),
        "PepPositiveCells": str(summary["pep_attainable_pair_count"]),
        "PepAmbiguousCells": str(summary["pep_numerically_ambiguous_cell_count"]),
        "PepOffShiftCells": str(summary["pep_off_shift_attainable_count"]),
        "TranscriptPayloadHash": payload["payload_sha256"],
        "JointPolicyMeanRatio": f"{summary['joint_policy_cost_ratio']['mean']:.3f}",
        "JointPolicyMedianRatio": (
            f"{summary['joint_policy_cost_ratio']['median']:.3f}"
        ),
        "JointPolicyWorseRate": _pct(summary["joint_policy_worse_fraction"]),
        "RectanglePolicyMeanRatio": (
            f"{summary['rectangle_policy_cost_ratio']['mean']:.3f}"
        ),
        "RectanglePolicyMedianRatio": (
            f"{summary['rectangle_policy_cost_ratio']['median']:.3f}"
        ),
        "RectanglePolicyWorseRate": _pct(summary["rectangle_policy_worse_fraction"]),
        "AlwaysPolicyMeanRatio": (f"{summary['always_policy_cost_ratio']['mean']:.3f}"),
        "AlwaysPolicyMedianRatio": (
            f"{summary['always_policy_cost_ratio']['median']:.3f}"
        ),
        "AlwaysPolicyWorseRate": _pct(summary["always_policy_worse_fraction"]),
        "PepDenseElapsed": f"{dense_scaling['elapsed_seconds']:.2f}",
        "PepScaleTenElapsed": f"{scaling[10]['elapsed_seconds']:.2f}",
        "PepScaleFifteenElapsed": f"{scaling[15]['elapsed_seconds']:.2f}",
        "PepScaleTwentyElapsed": f"{scaling[20]['elapsed_seconds']:.2f}",
        "PepScaleTwentyNominal": str(scaling[20]["nominal_joint_cell_count"]),
        "PepScaleTwentySolved": str(scaling[20]["solved_sdp_cell_count"]),
        "PepScaleTwentyExcluded": str(scaling[20]["structurally_excluded_cell_count"]),
        "PepScaleTwentyGram": str(scaling[20]["maximum_gram_order"]),
        "PepScalingPayloadHash": scaling_payload["payload_sha256"],
        "GenericPepNominal": str(
            generic_scaling_payload["declaration"]["nominal_joint_cell_count"]
        ),
        "GenericPepBadCells": str(
            generic_scaling_payload["declaration"]["bad_cell_count"]
        ),
        "GenericPepPositiveCells": str(generic["positive_margin_bad_cell_count"]),
        "GenericPepAmbiguousCells": str(
            generic["numerically_ambiguous_bad_cell_count"]
        ),
        "GenericPepOptimal": str(generic_status_counts.get("optimal", 0)),
        "GenericPepOptimalInaccurate": str(
            generic_status_counts.get("optimal_inaccurate", 0)
        ),
        "GenericPepInfeasible": str(generic_status_counts.get("infeasible", 0)),
        "GenericPepInfeasibleInaccurate": str(
            generic_status_counts.get("infeasible_inaccurate", 0)
        ),
        "GenericPepMaxGram": str(generic["maximum_gram_order"]),
        "GenericPepMedianGram": f"{generic['median_gram_order']:.0f}",
        "GenericPepMaxConstraints": f"{generic['maximum_constraint_count']:,}",
        "GenericPepWallSeconds": f"{generic['wall_seconds']:.1f}",
        "GenericPepPayloadHash": generic_scaling_payload["payload_sha256"],
        "NonlinearPepCells": str(
            nonlinear_pep_payload["pep_enumeration"]["cell_count"]
        ),
        "NonlinearPepBadCells": str(
            nonlinear_pep_payload["exact_certificate"][
                "excluded_cost_violating_cell_count"
            ]
        ),
        "NonlinearPepPositiveCells": str(
            len(nonlinear_pep_payload["pep_enumeration"]["positive_margin_pairs"])
        ),
        "NonlinearPepCandidateBound": _tex_fraction(
            nonlinear_pep_payload["exact_certificate"]["candidate_gradient_upper"]
        ),
        "NonlinearPepCostRatio": (
            f"{nonlinear_pep_payload['gate']['declared_all_in_cost_ratio']:.3f}"
        ),
        "NonlinearPepPayloadHash": nonlinear_pep_payload["payload_sha256"],
        "RealSpxRawQuotes": f"{real_data['raw_quote_count']:,}",
        "RealSpxFilteredQuotes": f"{real_data['filtered_quote_count']:,}",
        "RealSpxExpiries": str(real_data["expiry_count"]),
        "RealSpxMu": f"{float(Fraction(real_certificate['mu_gershgorin'])):.6f}",
        "RealSpxL": (
            f"{float(Fraction(real_certificate['smoothness_gershgorin'])):.6f}"
        ),
        "RealSpxBaselineCalls": str(real_certificate["baseline_calls"]),
        "RealSpxHybridCalls": str(real_certificate["hybrid_calls"]),
        "RealSpxSavedCalls": str(real_certificate["exact_call_saving"]),
        "RealSpxOnlineCost": (
            f"{real_cost['online_proposal_and_verification_units']:.3f}"
        ),
        "RealSpxOfflineCost": (f"{real_cost['one_time_constant_pipeline_units']:.3f}"),
        "RealSpxColdTotal": f"{real_cost['cold_start_total_units']:.3f}",
        "RealSpxBreakEven": str(real_cost["break_even_reuses"]),
        "RealSpxWarmTotal": (f"{real_cost['amortized_total_units_at_break_even']:.3f}"),
        "RealSpxMeasuredCost": (f"{real_cost['measured_online_to_exact_ratio']:.3f}"),
        "RealSpxMeasuredBreakEven": str(real_cost["measured_break_even_reuses"]),
        "RealSpxPayloadHash": real_spx_payload["payload_sha256"],
        "ProductionExactSeconds": f"{production['exact_median_wall_seconds']:.1f}",
        "ProductionHybridSeconds": f"{production['hybrid_median_wall_seconds']:.1f}",
        "ProductionSpeedup": f"{production['runtime_speedup']:.3f}",
        "ProductionAdjointIncrease": _pct(production["exact_adjoint_change_fraction"]),
        "ProductionIvRatio": f"{production['iv_rmse_ratio']:.4f}",
        "ProductionRepeats": str(production["repeat_count"]),
        "ProductionPayloadHash": production["source_payload_sha256"],
        "PositiveSpxConditionLower": (
            f"{(Fraction(positive_certificate['condition_lower']) * 100).__floor__() / 100:.2f}"
        ),
        "PositiveSpxConditionUpper": (
            f"{float(Fraction(positive_certificate['condition_upper'])):.0f}"
        ),
        "PositiveSpxBaselineCalls": str(positive_certificate["baseline_calls"]),
        "PositiveSpxHybridCalls": str(positive_certificate["hybrid_calls"]),
        "PositiveSpxSavedCalls": f"{positive_certificate['saved_exact_calls']:,}",
        "PositiveSpxNonexactCost": (f"{positive_cost['charged_nonexact_units']:.3f}"),
        "PositiveSpxCandidateTotal": (f"{positive_cost['candidate_total_units']:.3f}"),
        "PositiveSpxCostRatio": (f"{positive_cost['candidate_to_baseline_ratio']:.3f}"),
        "PositiveSpxCostSlack": (f"{positive_cost['total_cost_slack_units']:,.1f}"),
        "PositiveSpxBreakEven": str(positive_timing["measured_break_even_reuses"]),
        "PositiveSpxWarmSpeedup": (f"{positive_timing['measured_warm_speedup']:.3f}"),
        "PositiveSpxMeasuredRatio": (
            f"{positive_timing['measured_ratio_at_break_even']:.3f}"
        ),
        "PositiveSpxPipelineSeconds": (
            f"{positive_timing['pipeline_seconds_including_certificate_generation_and_verification']:.3f}"
        ),
        "PositiveSpxPayloadHash": real_spx_positive_payload["payload_sha256"],
        "AccountingCases": f"{accounting['case_count']:,}",
        "AccountingGateAccepted": str(accounting["gate_accept_count"]),
        "AccountingGateAcceptRate": _pct(accounting["gate_accept_rate"]),
        "AccountingGateMeanRatio": f"{accounting['gated_cost_ratio']['mean']:.3f}",
        "AccountingGateMedianRatio": f"{accounting['gated_cost_ratio']['median']:.3f}",
        "AccountingAcceptedMeanRatio": (
            f"{accounting['accepted_gate_cost_ratio']['mean']:.3f}"
        ),
        "AccountingAlwaysMeanRatio": (f"{accounting['always_cost_ratio']['mean']:.3f}"),
        "AccountingAlwaysMedianRatio": (
            f"{accounting['always_cost_ratio']['median']:.3f}"
        ),
        "AccountingAlwaysWorseRate": _pct(accounting["always_worse_fraction"]),
        "AccountingPosthocMeanRatio": (
            f"{accounting['posthoc_cost_ratio']['mean']:.3f}"
        ),
        "AccountingPosthocMedianRatio": (
            f"{accounting['posthoc_cost_ratio']['median']:.3f}"
        ),
        "AccountingPosthocWorseRate": _pct(accounting["posthoc_worse_fraction"]),
        "AccountingPayloadHash": accounting_payload["payload_sha256"],
        "RationalCertificateInstances": str(certificate_summary["instance_count"]),
        "RationalDualCertificates": str(certificate_summary["certificate_count"]),
        "RationalPrincipalMinors": str(certificate_summary["principal_minor_count"]),
        "RationalCertificatePayloadHash": certificate_summary["payload_sha256"],
    }
    for dimension_name, instance in zip(
        ("TwoD", "ThreeD", "FourD"), certificate_summary["instances"], strict=True
    ):
        metrics[f"RationalMinGap{dimension_name}"] = _tex_fraction(
            instance["minimum_strict_gap"]
        )
    lines = ["% Generated from the frozen transcript-PEP and accounting payloads."]
    lines.extend(
        f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in metrics.items()
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
