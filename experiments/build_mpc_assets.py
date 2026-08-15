#!/usr/bin/env python3
"""Bind the MPC manuscript to the frozen transcript-PEP payload."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from math import ceil, log, sqrt
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
GENERIC_DUAL_CERTIFICATE = ROOT / "certificates" / "generic_nonquadratic_pep_dual.json"
H10_GENERIC_DUAL_CERTIFICATE = ROOT / "certificates" / "h10_generic_pep_dual.json"
H10_MARGINAL_CERTIFICATE = ROOT / "certificates" / "h10_marginal_pep_dual.json"
H10_ENVELOPE_FAMILY = ROOT / "certificates" / "h10_envelope_family.json"
H10_CANDIDATE_HEAVY = ROOT / "certificates" / "h10_candidate_heavy_pep_dual.json"
H10_TIGHT_CONTRACT = ROOT / "certificates" / "h10_tight_contract_pep_dual.json"
JOINT_ONLY_CERTIFICATE = ROOT / "certificates" / "joint_only_shift_certificate.json"
FULL_CLASS_JOINT_ONLY_CERTIFICATE = (
    ROOT / "certificates" / "full_class_joint_only_pep_dual.json"
)
SOLVER_BENCHMARK_PAYLOAD = ROOT / "results" / "generic_pep_solver_benchmark.json"
PEPIT_COMPARISON_PAYLOAD = ROOT / "results" / "pepit_backend_comparison.json"
CERTIFICATE_COST_PAYLOAD = ROOT / "results" / "certificate_cost_study.json"
H10_CERTIFICATE_COST_PAYLOAD = ROOT / "results" / "h10_certificate_cost_study.json"
SPX_SENSITIVITY_PAYLOAD = ROOT / "results" / "spx_sensitivity_study.json"
SCS_RECOVERY_PAYLOAD = ROOT / "results" / "scs_recovery_diagnostic.json"
SYMPY_CROSSCHECK_PAYLOAD = ROOT / "results" / "sympy_exact_crosscheck.json"
RATIONAL_VERIFIER = ROOT / "tools" / "verify_rational_dual_certificates.py"
REAL_SPX_POSITIVE_VERIFIER = (
    ROOT / "tools" / "verify_real_spx_ill_conditioned_certificate.py"
)
NONLINEAR_PEP_VERIFIER = ROOT / "tools" / "verify_nonlinear_joint_pep_acceptance.py"
GENERIC_DUAL_VERIFIER = ROOT / "tools" / "verify_generic_nonquadratic_pep_dual.py"
FULL_CLASS_JOINT_ONLY_VERIFIER = (
    ROOT / "tools" / "verify_full_class_joint_only_pep_dual.py"
)
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
    generic_dual_payload = _load_hashed_payload(GENERIC_DUAL_CERTIFICATE)
    h10_dual_payload = _load_hashed_payload(H10_GENERIC_DUAL_CERTIFICATE)
    h10_marginal_payload = _load_hashed_payload(H10_MARGINAL_CERTIFICATE)
    h10_family_payload = _load_hashed_payload(H10_ENVELOPE_FAMILY)
    h10_candidate_payload = _load_hashed_payload(H10_CANDIDATE_HEAVY)
    h10_tight_payload = _load_hashed_payload(H10_TIGHT_CONTRACT)
    joint_only_payload = _load_hashed_payload(JOINT_ONLY_CERTIFICATE)
    full_class_joint_only_payload = _load_hashed_payload(
        FULL_CLASS_JOINT_ONLY_CERTIFICATE
    )
    solver_benchmark_payload = _load_hashed_payload(SOLVER_BENCHMARK_PAYLOAD)
    pepit_comparison_payload = _load_hashed_payload(PEPIT_COMPARISON_PAYLOAD)
    certificate_cost_payload = _load_hashed_payload(CERTIFICATE_COST_PAYLOAD)
    h10_certificate_cost_payload = _load_hashed_payload(
        H10_CERTIFICATE_COST_PAYLOAD
    )
    spx_sensitivity_payload = _load_hashed_payload(SPX_SENSITIVITY_PAYLOAD)
    scs_recovery_payload = _load_hashed_payload(SCS_RECOVERY_PAYLOAD)
    sympy_crosscheck_payload = _load_hashed_payload(SYMPY_CROSSCHECK_PAYLOAD)
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
            str(GENERIC_DUAL_VERIFIER),
            str(GENERIC_DUAL_CERTIFICATE),
            "--root",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(FULL_CLASS_JOINT_ONLY_VERIFIER),
            str(FULL_CLASS_JOINT_ONLY_CERTIFICATE),
            "--root",
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
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
    positive_objective = real_spx_positive_payload["objective"]
    positive_gradient_norm = sqrt(
        float(
            sum(
                Fraction(value) ** 2
                for value in positive_objective["exact_linear"]
            )
        )
    )
    positive_tolerance = sqrt(
        float(Fraction(positive_certificate["tolerance_squared"]))
    )
    positive_mu = float(Fraction(positive_certificate["mu_lower"]))
    positive_smoothness = float(
        Fraction(positive_certificate["smoothness_upper"])
    )
    positive_step = float(Fraction(positive_certificate["step_size"]))
    positive_q = max(
        abs(1.0 - positive_step * positive_mu),
        abs(1.0 - positive_step * positive_smoothness),
    )
    positive_candidate_norm = sqrt(
        float(sum(Fraction(value) ** 2 for value in positive_certificate["candidate"]))
    )
    short_baseline_lower = ceil(
        log(positive_tolerance / positive_gradient_norm)
        / log(abs(1.0 - positive_step * positive_smoothness))
    )
    short_hybrid_upper = ceil(
        log(
            positive_tolerance
            / (
                positive_smoothness
                * (positive_gradient_norm / positive_mu + positive_candidate_norm)
            )
        )
        / log(positive_q)
    )
    cost_measurement = certificate_cost_payload["measurement"]
    cost_scenarios = {
        row["exact_oracle_seconds"]: row
        for row in certificate_cost_payload["scenarios"]
    }
    h10_cost_measurement = h10_certificate_cost_payload["measurement"]
    h10_cost_scenarios = {
        row["exact_oracle_seconds"]: row
        for row in h10_certificate_cost_payload["scenarios"]
    }
    pde_fixed_seconds = 720.0 + h10_cost_measurement["total_certificate_seconds"]
    pde_break_even = ceil(pde_fixed_seconds / (0.6 * 60.0))
    pde_amortized_at_64 = pde_fixed_seconds / (64.0 * 60.0)
    pde_break_even_by_oracle = {
        seconds: ceil(
            (
                12.0
                + h10_cost_measurement["total_certificate_seconds"] / seconds
            )
            / 0.6
        )
        for seconds in (1.0, 10.0, 60.0, 600.0, 3600.0)
    }
    sensitivity = spx_sensitivity_payload["summary"]
    sensitivity_base = next(
        row
        for row in spx_sensitivity_payload["records"]
        if row["ridge"] == "1/10000"
        and row["sketch_stride"] == 10
        and row["tolerance_power"] == 10
    )
    proxy_horizons = sorted(
        max(max(pair) for pair in record["pairs"])
        for record in payload["records"]
    )
    proxy_horizon_median = (
        proxy_horizons[len(proxy_horizons) // 2 - 1]
        + proxy_horizons[len(proxy_horizons) // 2]
    ) / 2
    proxy_horizon_p90 = proxy_horizons[ceil(0.9 * len(proxy_horizons)) - 1]
    nonlinear_actual = nonlinear_pep_payload["actual_instance"]
    dependence_gap = summary["joint_accept_count"] - summary["rectangle_accept_count"]
    solver_benchmark = {
        (row["solver"], row["horizon"]): row
        for row in solver_benchmark_payload["summary"]
    }
    pepit_comparison = {
        (row["backend"], row["horizon"]): row
        for row in pepit_comparison_payload["summary"]
    }
    contract_sensitivity = {
        row["contract_radius"]: row
        for row in full_class_joint_only_payload[
            "diagnostic_contract_radius_sensitivity"
        ]
    }
    misspecification = summary["contract_misspecification"]
    h10_recovery_grid = h10_dual_payload["summary"]["recovery_grid"]
    h10_recovery_attempts = sum(row["attempted_cells"] for row in h10_recovery_grid)
    h10_recovery_failures = sum(row["failed_cells"] for row in h10_recovery_grid)
    h10_recovery_successes = sum(row["successful_cells"] for row in h10_recovery_grid)
    h10_recovery_reached = sum(row["attempted_cells"] > 0 for row in h10_recovery_grid)
    family_sources = [h10_dual_payload, h10_candidate_payload, h10_tight_payload]
    family_recovery_attempts = sum(
        row["attempted_cells"]
        for source in family_sources
        for row in source["summary"]["recovery_grid"]
    )
    family_recovery_failures = sum(
        row["failed_cells"]
        for source in family_sources
        for row in source["summary"]["recovery_grid"]
    )

    def nonlinear_norm(field: str) -> float:
        return sqrt(sum(float(value) ** 2 for value in nonlinear_actual[field]))

    metrics = {
        "TranscriptCases": f"{summary['case_count']:,}",
        "JointAcceptCount": str(summary["joint_accept_count"]),
        "JointAcceptRate": _pct(summary["joint_accept_rate"]),
        "RectangleAcceptCount": str(summary["rectangle_accept_count"]),
        "RectangleAcceptRate": _pct(summary["rectangle_accept_rate"]),
        "TwoBinAcceptCount": str(summary["two_bin_accept_count"]),
        "TwoBinAcceptRate": _pct(summary["two_bin_accept_rate"]),
        "FourBinAcceptCount": str(summary["four_bin_accept_count"]),
        "FourBinAcceptRate": _pct(summary["four_bin_accept_rate"]),
        "TwoBinRecoveredDependencePct": (
            f"{100 * (summary['two_bin_accept_count'] - summary['rectangle_accept_count']) / dependence_gap:.1f}\\%"
        ),
        "FourBinRecoveredDependencePct": (
            f"{100 * (summary['four_bin_accept_count'] - summary['rectangle_accept_count']) / dependence_gap:.1f}\\%"
        ),
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
        "ProxyHorizonMin": str(proxy_horizons[0]),
        "ProxyHorizonMedian": f"{proxy_horizon_median:.0f}",
        "ProxyHorizonNinety": str(proxy_horizon_p90),
        "ProxyHorizonMax": str(proxy_horizons[-1]),
        "ProxyHorizonAtMostTwenty": str(
            sum(horizon <= 20 for horizon in proxy_horizons)
        ),
        "ProxyNominalCells": f"{sum((horizon + 1) ** 2 for horizon in proxy_horizons):,}",
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
        "TwoBinPolicyMeanRatio": (
            f"{summary['two_bin_policy_cost_ratio']['mean']:.3f}"
        ),
        "TwoBinPolicyMedianRatio": (
            f"{summary['two_bin_policy_cost_ratio']['median']:.3f}"
        ),
        "FourBinPolicyMeanRatio": (
            f"{summary['four_bin_policy_cost_ratio']['mean']:.3f}"
        ),
        "FourBinPolicyMedianRatio": (
            f"{summary['four_bin_policy_cost_ratio']['median']:.3f}"
        ),
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
        "NonlinearPepDimension": str(nonlinear_actual["dimension"]),
        "NonlinearPepNaturalHorizon": str(
            nonlinear_pep_payload["parameters"]["natural_horizon"]
        ),
        "NonlinearPepAuditPadding": str(
            nonlinear_pep_payload["parameters"]["audit_padding"]
        ),
        "NonlinearPepAuditHorizon": str(
            nonlinear_pep_payload["parameters"]["horizon"]
        ),
        "NonlinearPepCurrentGradientNorm": f"{nonlinear_norm('gradient_x'):.7f}",
        "NonlinearPepBaselineOneGradientNorm": (
            f"{nonlinear_norm('gradient_x_one'):.7f}"
        ),
        "NonlinearPepCandidateGradientNorm": f"{nonlinear_norm('gradient_y'):.7f}",
        "NonlinearPepProposalNorm": f"{float(nonlinear_actual['proposal_norm']):.7f}",
        "NonlinearPepResidualNorm": (
            f"{float(nonlinear_actual['candidate_residual_norm']):.4f}"
        ),
        "NonlinearPepSpanDeterminant": (
            f"{float(nonlinear_actual['trajectory_span_determinant']):.7f}"
        ),
        "NonlinearPepCostRatio": (
            f"{nonlinear_pep_payload['gate']['declared_all_in_cost_ratio']:.3f}"
        ),
        "NonlinearPepPayloadHash": nonlinear_pep_payload["payload_sha256"],
        "GenericDualUpper": (
            f"{float(Fraction(generic_dual_payload['summary']['maximum_certified_upper_bound'])):.6f}"
        ),
        "GenericDualCertificates": str(
            generic_dual_payload["summary"]["certificate_count"]
        ),
        "GenericDualMinors": str(
            generic_dual_payload["summary"]["total_positive_leading_minors"]
        ),
        "GenericDualPayloadHash": generic_dual_payload["payload_sha256"],
        "HtenDualCertificates": str(h10_dual_payload["summary"]["certificate_count"]),
        "HtenDualPivots": f"{h10_dual_payload['summary']['positive_leading_principal_minor_count']:,}",
        "HtenDualUpper": (
            f"{float(Fraction(h10_dual_payload['summary']['maximum_certified_upper_bound'])):.6f}"
        ),
        "HtenDualGram": str(h10_dual_payload["summary"]["maximum_gram_order"]),
        "HtenDualInequalities": f"{h10_dual_payload['summary']['maximum_inequality_count']:,}",
        "HtenDualGenerationSeconds": (
            f"{h10_dual_payload['summary']['generation_wall_seconds']:.1f}"
        ),
        "HtenDualPayloadHash": h10_dual_payload["payload_sha256"],
        "HtenMarginalGradientUpper": (
            f"{float(Fraction(h10_marginal_payload['certificate']['dual']['certified_gradient_squared_upper_bound'])):.6f}"
        ),
        "HtenMarginalRectangleValue": str(
            h10_marginal_payload["exact_consequences"][
                "rectangle_gate_value_with_max_cost_one"
            ]
        ),
        "HtenMarginalPayloadHash": h10_marginal_payload["payload_sha256"],
        "HtenFamilyProfiles": str(h10_family_payload["declaration"]["profile_count"]),
        "HtenFamilyIndependentProfiles": str(
            h10_family_payload["declaration"]["independently_recovered_profile_count"]
        ),
        "HtenFamilyExactCells": str(
            h10_family_payload["declaration"]["profile_count"]
            * h10_family_payload["declaration"]["bad_cells_per_profile"]
        ),
        "HtenFamilyIndependentCells": str(3 * 66),
        "HtenFamilyTransportedCells": str(2 * 66),
        "HtenFamilyRecoveryAttempts": str(family_recovery_attempts),
        "HtenFamilyRecoveryFailures": str(family_recovery_failures),
        "HtenCandidateHeavyUpper": (
            f"{float(Fraction(h10_candidate_payload['summary']['maximum_certified_upper_bound'])):.6f}"
        ),
        "HtenTightContractUpper": (
            f"{float(Fraction(h10_tight_payload['summary']['maximum_certified_upper_bound'])):.6f}"
        ),
        "HtenFamilyPayloadHash": h10_family_payload["payload_sha256"],
        "HtenRecoveryAttempts": str(h10_recovery_attempts),
        "HtenRecoveryFailures": str(h10_recovery_failures),
        "HtenRecoverySuccesses": str(h10_recovery_successes),
        "HtenRecoveryReachedConfigs": str(h10_recovery_reached),
        "HtenRecoveryProgress": h10_dual_payload["summary"][
            "certified_cell_progress"
        ].split()[0],
        "JointOnlyHorizon": str(joint_only_payload["declaration"]["formula_horizon"]),
        "JointOnlyRectangleValue": joint_only_payload["certificate"][
            "rectangle_certificate_value"
        ],
        "JointOnlyPayloadHash": joint_only_payload["payload_sha256"],
        "FullClassJointCertificates": str(
            full_class_joint_only_payload["summary"]["certificate_count"]
        ),
        "FullClassJointPivots": str(
            full_class_joint_only_payload["summary"]["positive_ldl_pivot_count"]
        ),
        "FullClassJointUpper": (
            f"{float(Fraction(full_class_joint_only_payload['summary']['maximum_certified_upper_bound'])):.6f}"
        ),
        "FullClassJointHorizon": str(
            full_class_joint_only_payload["declaration"]["horizon"]
        ),
        "FullClassJointRectangleValue": full_class_joint_only_payload[
            "marginal_certificate"
        ]["rectangle_certificate_value"],
        "FullClassJointGenerationSeconds": (
            f"{full_class_joint_only_payload['summary']['generation_wall_seconds']:.2f}"
        ),
        "FullClassJointPayloadHash": full_class_joint_only_payload[
            "payload_sha256"
        ],
        "FullClassMarginZero": (
            f"{contract_sensitivity['0']['maximum_floating_signed_margin']:.6f}"
        ),
        "FullClassMarginOneHundred": (
            f"{contract_sensitivity['1/100']['maximum_floating_signed_margin']:.6f}"
        ),
        "FullClassMarginOneFifty": (
            f"{contract_sensitivity['1/50']['maximum_floating_signed_margin']:.6f}"
        ),
        "FullClassMarginThreeHundred": (
            f"{contract_sensitivity['3/100']['maximum_floating_signed_margin']:.6f}"
        ),
        "FullClassMarginOneTwenty": (
            f"{contract_sensitivity['1/20']['maximum_floating_signed_margin']:.6f}"
        ),
        "ClarabelHtenWall": (
            f"{solver_benchmark[('CLARABEL', 10)]['wall_seconds']['median']:.2f}"
        ),
        "ScsHtenWall": (
            f"{solver_benchmark[('SCS', 10)]['wall_seconds']['median']:.2f}"
        ),
        "ClarabelHtenMemory": (
            f"{solver_benchmark[('CLARABEL', 10)]['peak_rss_mib']['median']:.0f}"
        ),
        "ScsHtenMemory": (
            f"{solver_benchmark[('SCS', 10)]['peak_rss_mib']['median']:.0f}"
        ),
        "SolverBenchmarkPayloadHash": solver_benchmark_payload["payload_sha256"],
        "ScsRecoveryCells": str(scs_recovery_payload["summary"]["cell_count"]),
        "ScsRecoverySuccesses": str(
            scs_recovery_payload["summary"]["recovery_success_count"]
        ),
        "ScsRecoveryFailures": str(
            scs_recovery_payload["summary"]["recovery_failure_count"]
        ),
        "ScsRecoveryPayloadHash": scs_recovery_payload["payload_sha256"],
        "SympyCrosscheckSlacks": str(
            sympy_crosscheck_payload["summary"]["certificate_count"]
        ),
        "SympyCrosscheckPivots": f"{sympy_crosscheck_payload['summary']['positive_ldl_pivot_count']:,}",
        "SympyCrosscheckSeconds": (
            f"{sympy_crosscheck_payload['summary']['wall_seconds']:.1f}"
        ),
        "SympyCrosscheckPayloadHash": sympy_crosscheck_payload["payload_sha256"],
        "CtwoHtenSerialWall": (
            f"{pepit_comparison[('c2ogate', 10)]['wall_seconds']['median']:.2f}"
        ),
        "PepitHtenSerialWall": (
            f"{pepit_comparison[('pepit', 10)]['wall_seconds']['median']:.2f}"
        ),
        "PepitVersion": pepit_comparison_payload["environment"]["pepit"],
        "PepitComparisonPayloadHash": pepit_comparison_payload["payload_sha256"],
        "MisspecTenFalseConditional": _pct(
            misspecification["0.90"]["false_accept_rate_conditional_on_accept"]
        ),
        "MisspecTenAcceptCount": str(
            misspecification["0.90"]["claim_accept_count"]
        ),
        "MisspecTenFalseCount": str(
            misspecification["0.90"]["false_accept_count"]
        ),
        "MisspecTenExcluded": _pct(
            misspecification["0.90"]["realized_member_excluded_rate"]
        ),
        "MisspecTenFalseOverall": _pct(
            misspecification["0.90"]["false_accept_rate"]
        ),
        "MisspecTenRealizedViolation": _pct(
            misspecification["0.90"]["realized_violation_rate"]
        ),
        "MisspecTwentyFiveFalseConditional": _pct(
            misspecification["0.75"]["false_accept_rate_conditional_on_accept"]
        ),
        "MisspecTwentyFiveAcceptCount": str(
            misspecification["0.75"]["claim_accept_count"]
        ),
        "MisspecTwentyFiveFalseCount": str(
            misspecification["0.75"]["false_accept_count"]
        ),
        "MisspecTwentyFiveFalseOverall": _pct(
            misspecification["0.75"]["false_accept_rate"]
        ),
        "MisspecTwentyFiveExcluded": _pct(
            misspecification["0.75"]["realized_member_excluded_rate"]
        ),
        "MisspecHalfAcceptCount": str(
            misspecification["0.50"]["claim_accept_count"]
        ),
        "MisspecHalfFalseCount": str(
            misspecification["0.50"]["false_accept_count"]
        ),
        "MisspecHalfFalseConditional": _pct(
            misspecification["0.50"]["false_accept_rate_conditional_on_accept"]
        ),
        "CertificateCostSeconds": f"{cost_measurement['total_certificate_seconds']:.3f}",
        "CertificateVerifyMillis": (
            f"{1000.0 * cost_measurement['median_verification_seconds']:.2f}"
        ),
        "CertificateUnitsTinyOracle": (
            f"{cost_scenarios[0.0001]['certificate_cost_exact_call_units'] / 10**4:.3f}"
        ),
        "CertificateUnitsOneSecond": (
            f"{cost_scenarios[1.0]['certificate_cost_exact_call_units']:.3f}"
        ),
        "CertificateUnitsTenSecond": (
            f"{cost_scenarios[10.0]['certificate_cost_exact_call_units']:.3f}"
        ),
        "CertificateUnitsSixtySecond": (
            f"{cost_scenarios[60.0]['certificate_cost_exact_call_units']:.3f}"
        ),
        "CertificateBreakEvenTinyOracle": str(
            cost_scenarios[0.0001]["minimum_offline_reuses"]
        ),
        "CertificateBreakEvenOneSecond": str(
            cost_scenarios[1.0]["minimum_offline_reuses"]
        ),
        "CertificateBreakEvenTenSecond": str(
            cost_scenarios[10.0]["minimum_offline_reuses"]
        ),
        "CertificateBreakEvenSixtySecond": str(
            cost_scenarios[60.0]["minimum_offline_reuses"]
        ),
        "CertificateCostPayloadHash": certificate_cost_payload["payload_sha256"],
        "HtenCertificateSearchSeconds": (
            f"{h10_cost_measurement['solver_and_rational_recovery_seconds']:.1f}"
        ),
        "HtenCertificateVerifySeconds": (
            f"{h10_cost_measurement['median_verification_seconds']:.1f}"
        ),
        "HtenCertificateTotalSeconds": (
            f"{h10_cost_measurement['total_certificate_seconds']:.1f}"
        ),
        "HtenCertificateBudget": (
            f"{h10_certificate_cost_payload['declaration']['certificate_budget_exact_call_units']:.1f}"
        ),
        "HtenCertificateBreakEvenOneSecond": str(
            h10_cost_scenarios[1.0]["minimum_offline_reuses"]
        ),
        "HtenCertificateBreakEvenTenSeconds": str(
            h10_cost_scenarios[10.0]["minimum_offline_reuses"]
        ),
        "HtenCertificateBreakEvenSixtySeconds": str(
            h10_cost_scenarios[60.0]["minimum_offline_reuses"]
        ),
        "HtenCertificateBreakEvenSixHundredSeconds": str(
            h10_cost_scenarios[600.0]["minimum_offline_reuses"]
        ),
        "HtenCertificateBreakEvenHour": str(
            h10_cost_scenarios[3600.0]["minimum_offline_reuses"]
        ),
        "HtenCertificateCostPayloadHash": h10_certificate_cost_payload[
            "payload_sha256"
        ],
        "PdeIllustrationBreakEven": str(pde_break_even),
        "PdeBreakEvenOneSecond": str(pde_break_even_by_oracle[1.0]),
        "PdeBreakEvenTenSeconds": str(pde_break_even_by_oracle[10.0]),
        "PdeBreakEvenSixtySeconds": str(pde_break_even_by_oracle[60.0]),
        "PdeBreakEvenSixHundredSeconds": str(pde_break_even_by_oracle[600.0]),
        "PdeBreakEvenHour": str(pde_break_even_by_oracle[3600.0]),
        "PdeIllustrationAmortizedAtSixtyFour": f"{pde_amortized_at_64:.3f}",
        "PdeIllustrationTotalAtSixtyFour": f"{0.4 + pde_amortized_at_64:.3f}",
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
        "PositiveSpxShortBaselineLower": str(short_baseline_lower),
        "PositiveSpxShortHybridUpper": f"{short_hybrid_upper:,}",
        "PositiveSpxShortNominalCells": f"{(short_hybrid_upper + 1) ** 2:,}",
        "PositiveSpxShortGramOrder": f"{2 * (short_hybrid_upper + 1) + 2:,}",
        "SpxSensitivityConfigurations": str(sensitivity["configuration_count"]),
        "SpxSensitivityAccepted": str(sensitivity["accepted_count"]),
        "SpxSensitivityMinRatio": f"{sensitivity['minimum_total_cost_ratio']:.3f}",
        "SpxSensitivityMaxRatio": f"{sensitivity['maximum_total_cost_ratio']:.3f}",
        "SpxSensitivityMinSaved": str(sensitivity["minimum_saved_calls"]),
        "SpxSensitivityMaxSaved": f"{sensitivity['maximum_saved_calls']:,}",
        "SpxSensitivityBaseRatio": f"{sensitivity_base['total_cost_ratio']:.3f}",
        "SpxSensitivityPayloadHash": spx_sensitivity_payload["payload_sha256"],
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
