#!/usr/bin/env python3
"""Short-transcript C2OGate audit on a rolling nonlinear calibration workload.

The gate sees the current exact gradient, a 5% minibatch proposal, and analytic
class/envelope bounds.  Full gradients at the proposed and subsequent states
are evaluated only after the continuation decision for a blinded outcome audit.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np

from c2ogate.exact_membership import (
    binary64_vector,
    certify_h6_envelope_membership,
    exact_linear_data_gradient,
    exact_max_row_squared_norm,
    rational_squared_norm,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "rolling_logistic_workload.json"
CERTIFICATE = ROOT / "certificates" / "h6_joint_only_pep_dual.json"
COST_PAYLOAD = ROOT / "results" / "h6_certificate_cost_study.json"
SCHEMA = "c2o-rolling-logistic-workload-v5"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def _quantiles(values: list[float]) -> dict[str, float]:
    data = np.asarray(values, dtype=float)
    return {
        "minimum": float(np.min(data)),
        "q25": float(np.quantile(data, 0.25)),
        "median": float(np.median(data)),
        "q75": float(np.quantile(data, 0.75)),
        "maximum": float(np.max(data)),
    }


def _remaining_calls(
    start: np.ndarray,
    anchor: np.ndarray,
    *,
    features: np.ndarray,
    labels: np.ndarray,
    ridge: float,
    loss_scale: float,
    tolerance: float,
    horizon: int,
) -> tuple[int, float]:
    point = start.copy()
    for calls in range(horizon + 1):
        probabilities = _sigmoid(features @ point)
        gradient = (
            ridge * (point - anchor)
            + loss_scale * (features.T @ (probabilities - labels)) / len(labels)
        )
        norm = float(np.linalg.norm(gradient))
        if norm <= tolerance:
            return calls, norm
        point -= gradient
    raise RuntimeError("realized continuation exceeded the certified horizon")


def _validate_certificate(payload: dict[str, Any]) -> None:
    expected = {
        "strong_convexity": "3/10",
        "smoothness": "1",
        "step_size": "1",
        "proposal_step": "11/10",
        "proposal_norm_lower": "27/50",
        "proposal_norm_upper": "14/25",
        "contract_radius": "1/100",
        "initial_distance_upper": "9/5",
        "tolerance": "7/25",
        "derived_trace_bound": "66",
    }
    if payload.get("parameters") != expected:
        raise RuntimeError("flagship certificate parameters changed")
    summary = payload.get("summary", {})
    if summary.get("certificate_count") != 28:
        raise RuntimeError("flagship certificate is incomplete")
    if not str(summary.get("maximum_certified_upper_bound", "")).startswith("-"):
        raise RuntimeError("flagship suite lacks strict bad-cell exclusion")


def run_workload(
    *,
    seed: int = 20260815,
    sample_count: int = 40_000,
    dimension: int = 20,
    minibatch_count: int = 2_000,
    episode_count: int = 512,
) -> dict[str, Any]:
    if not (0 < minibatch_count < sample_count):
        raise ValueError("minibatch must be a strict subset of the full workload")
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(sample_count, dimension))
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    labels = rng.binomial(1, 0.5, size=sample_count).astype(float)

    ridge = 0.8
    loss_scale = 0.79
    anchor_radius_range = (0.30, 0.95)
    tolerance = 7.0 / 25.0
    proposal_step = 11.0 / 10.0
    proposal_lower = 27.0 / 50.0
    proposal_upper = 14.0 / 25.0
    contract_radius = 1.0 / 100.0
    distance_upper = 9.0 / 5.0
    horizon = 6
    ridge_fraction = Fraction(4, 5)
    loss_scale_fraction = Fraction(79, 100)
    proposal_step_fraction = Fraction(11, 10)
    proposal_lower_fraction = Fraction(27, 50)
    proposal_upper_fraction = Fraction(14, 25)
    contract_radius_fraction = Fraction(1, 100)
    distance_upper_fraction = Fraction(9, 5)
    exact_data_gradient_fraction = exact_linear_data_gradient(
        features, labels, loss_scale_fraction
    )
    maximum_row_squared_norm = exact_max_row_squared_norm(features)
    exact_smoothness_upper = (
        ridge_fraction
        + loss_scale_fraction * maximum_row_squared_norm / 4
    )
    if exact_smoothness_upper > 1:
        raise RuntimeError("binary64 feature rows do not certify L <= 1")

    certificate = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    _validate_certificate(certificate)
    records: list[dict[str, Any]] = []
    for episode in range(episode_count):
        direction = rng.normal(size=dimension)
        direction /= np.linalg.norm(direction)
        anchor_radius = rng.uniform(*anchor_radius_range)
        anchor = anchor_radius * direction
        anchor_fraction = binary64_vector(anchor)
        exact_gradient_fraction = tuple(
            data_value - ridge_fraction * anchor_value
            for data_value, anchor_value in zip(
                exact_data_gradient_fraction, anchor_fraction, strict=True
            )
        )
        exact_gradient = np.asarray(
            [float(value) for value in exact_gradient_fraction], dtype=float
        )
        gradient_squared_norm = rational_squared_norm(exact_gradient_fraction)
        # Triangle inequality gives a free necessary condition for any future
        # proposal to satisfy both the displacement band and residual ball.
        proposal_attempted = bool(
            (proposal_lower_fraction - contract_radius_fraction) ** 2
            <= proposal_step_fraction**2 * gradient_squared_norm
            <= (proposal_upper_fraction + contract_radius_fraction) ** 2
        )
        indices = rng.choice(sample_count, size=minibatch_count, replace=False)
        # A sampled Hessian supplies a genuine curvature-dependent proposal.
        # The raw reduced-Newton step is safeguarded by projecting only its
        # correction into the certified residual ball around -gamma*g(x).
        sampled_hessian = (
            ridge * np.eye(dimension)
            + 0.25
            * loss_scale
            * (features[indices].T @ features[indices])
            / minibatch_count
        )
        raw_reduced_newton = -np.linalg.solve(sampled_hessian, exact_gradient)
        gradient_center = -proposal_step * exact_gradient
        correction = raw_reduced_newton - gradient_center
        raw_correction_norm = float(np.linalg.norm(correction))
        correction_cap = 9.0 / 1000.0
        if raw_correction_norm > correction_cap:
            correction *= correction_cap / raw_correction_norm
        candidate = gradient_center + correction
        membership = certify_h6_envelope_membership(
            candidate,
            exact_gradient_fraction,
            proposal_step=proposal_step_fraction,
            proposal_lower=proposal_lower_fraction,
            proposal_upper=proposal_upper_fraction,
            contract_radius=contract_radius_fraction,
            strong_monotonicity=ridge_fraction,
            distance_upper=distance_upper_fraction,
        )
        proposal_norm = float(membership.proposal_squared_norm) ** 0.5
        contract_residual = float(membership.residual_squared_norm) ** 0.5
        distance_bound = float(membership.gradient_squared_norm) ** 0.5 / ridge
        accepted = bool(proposal_attempted and membership.accepted)
        decision_outcome = (
            "accept"
            if accepted
            else "uncertified"
            if proposal_attempted
            else "not_attempted"
        )
        uncertified_reasons = []
        if proposal_attempted and not accepted:
            if not membership.proposal_band_passed:
                uncertified_reasons.append("proposal_band")
            if not membership.residual_ball_passed:
                uncertified_reasons.append("residual_ball")
            if not membership.distance_bound_passed:
                uncertified_reasons.append("distance_bound")
        correction_norm = float(np.linalg.norm(correction))
        correction_cosine = float(
            np.dot(correction, exact_gradient)
            / max(correction_norm * float(np.linalg.norm(exact_gradient)), 1.0e-30)
        )

        # These full-model continuations are a post-decision evaluation only.
        baseline_calls, baseline_terminal_norm = _remaining_calls(
            np.zeros(dimension),
            anchor,
            features=features,
            labels=labels,
            ridge=ridge,
            loss_scale=loss_scale,
            tolerance=tolerance,
            horizon=horizon,
        )
        candidate_calls, candidate_terminal_norm = _remaining_calls(
            candidate,
            anchor,
            features=features,
            labels=labels,
            ridge=ridge,
            loss_scale=loss_scale,
            tolerance=tolerance,
            horizon=horizon,
        )
        if accepted and candidate_calls >= baseline_calls:
            raise RuntimeError("an accepted episode violates the exact suite")
        records.append(
            {
                "episode": episode,
                "anchor_radius": anchor_radius,
                "proposal_attempted_after_free_prefilter": proposal_attempted,
                "accepted_from_short_transcript": accepted,
                "decision_outcome": decision_outcome,
                "uncertified_reasons": uncertified_reasons,
                "proposal_norm": proposal_norm,
                "contract_residual": contract_residual,
                "distance_bound": distance_bound,
                "proposal_squared_norm_exact": str(
                    membership.proposal_squared_norm
                ),
                "contract_residual_squared_exact": str(
                    membership.residual_squared_norm
                ),
                "gradient_squared_norm_exact": str(
                    membership.gradient_squared_norm
                ),
                "proposal_band_passed_exactly": membership.proposal_band_passed,
                "residual_ball_passed_exactly": membership.residual_ball_passed,
                "distance_bound_passed_exactly": membership.distance_bound_passed,
                "raw_reduced_newton_correction_norm": raw_correction_norm,
                "safeguarded_correction_norm": correction_norm,
                "safeguarded_correction_cosine_with_gradient": correction_cosine,
                "baseline_calls_post_decision": baseline_calls,
                "candidate_calls_post_decision": candidate_calls,
                "baseline_terminal_norm_post_decision": baseline_terminal_norm,
                "candidate_terminal_norm_post_decision": candidate_terminal_norm,
            }
        )

    accepted = [row for row in records if row["accepted_from_short_transcript"]]
    baseline_calls = sum(row["baseline_calls_post_decision"] for row in records)
    gated_exact_calls = sum(
        row["candidate_calls_post_decision"]
        if row["accepted_from_short_transcript"]
        else row["baseline_calls_post_decision"]
        for row in records
    )
    saved_calls = baseline_calls - gated_exact_calls
    cheap_ratio = minibatch_count / sample_count
    attempted_count = sum(
        row["proposal_attempted_after_free_prefilter"] for row in records
    )
    rejected_count = sum(row["decision_outcome"] == "reject" for row in records)
    uncertified_count = sum(
        row["decision_outcome"] == "uncertified" for row in records
    )
    uncertified_reason_counts = {
        reason: sum(reason in row["uncertified_reasons"] for row in records)
        for reason in ("proposal_band", "residual_ball", "distance_bound")
    }
    cheap_units = attempted_count * cheap_ratio
    warm_total_units = gated_exact_calls + cheap_units
    marginal_exact_calls = baseline_calls
    marginal_total_units = marginal_exact_calls + cheap_units
    greedy_prefilter_exact_calls = sum(
        row["candidate_calls_post_decision"]
        if row["proposal_attempted_after_free_prefilter"]
        else row["baseline_calls_post_decision"]
        for row in records
    )
    greedy_prefilter_total_units = greedy_prefilter_exact_calls + cheap_units
    greedy_prefilter_pointwise_overruns = sum(
        row["proposal_attempted_after_free_prefilter"]
        and row["candidate_calls_post_decision"] + cheap_ratio
        > row["baseline_calls_post_decision"]
        for row in records
    )
    greedy_prefilter_nonimproving = sum(
        row["proposal_attempted_after_free_prefilter"]
        and row["candidate_calls_post_decision"]
        >= row["baseline_calls_post_decision"]
        for row in records
    )
    always_exact_calls = sum(
        row["candidate_calls_post_decision"] for row in records
    )
    always_cheap_units = episode_count * cheap_ratio
    always_total_units = always_exact_calls + always_cheap_units
    always_pointwise_overruns = sum(
        row["candidate_calls_post_decision"] + cheap_ratio
        > row["baseline_calls_post_decision"]
        for row in records
    )
    always_risk_break_even_penalty = (
        max(0.0, warm_total_units - always_total_units)
        / always_pointwise_overruns
        if always_pointwise_overruns
        else None
    )
    net_saving_per_episode = (baseline_calls - warm_total_units) / episode_count
    if not accepted or net_saving_per_episode <= 0:
        raise RuntimeError(
            "workload does not provide a positive warm-regime result: "
            f"accepted={len(accepted)}, baseline={baseline_calls}, "
            f"gated={gated_exact_calls}, cheap={cheap_units}"
        )

    cost_payload = json.loads(COST_PAYLOAD.read_text(encoding="utf-8"))
    certificate_seconds = float(
        cost_payload["measurement"]["total_certificate_seconds"]
    )
    cost_scenarios = []
    for exact_oracle_seconds in (1.0, 10.0, 60.0, 600.0, 3600.0):
        certificate_units = certificate_seconds / exact_oracle_seconds
        break_even_episodes = ceil(certificate_units / net_saving_per_episode)
        cold_total = warm_total_units + certificate_units
        cost_scenarios.append(
            {
                "exact_oracle_seconds": exact_oracle_seconds,
                "certificate_cost_exact_call_units": certificate_units,
                "break_even_episode_count": break_even_episodes,
                "observed_batch_all_in_cost_ratio": cold_total / baseline_calls,
                "observed_batch_self_financing": cold_total <= baseline_calls,
            }
        )

    return {
        "schema": SCHEMA,
        "declaration": {
            "workload": (
                "rolling proximal logistic calibration with normalized features, "
                "a drifting regularization center, and a 5% sampled-Hessian "
                "reduced-Newton proposal"
            ),
            "role": (
                "neutral-range synthetic decision replay, not a real-data or "
                "production-frequency claim"
            ),
            "gate_timing": (
                "the decision uses only the already-observed full gradient at x, "
                "a free necessary-condition prefilter, a sampled-Hessian proposal, "
                "analytic class constants, and the frozen "
                "natural-H=6 proof; all candidate/future full gradients are held "
                "out until "
                "the post-decision outcome audit"
            ),
            "function": (
                "0.79*mean(log(1+exp(a_i^T w))-b_i a_i^T w) "
                "+ 0.4*||w-anchor||^2"
            ),
            "class_proof": (
                "exact rational row-norm replay gives 0.8 I <= Hessian <= I "
                "because sigmoid'<=1/4; "
                "hence the workload lies in F_{0.8,1}, a subset of F_{0.3,1}. "
                "Strong monotonicity gives ||x-x_*||<=||grad f(x)||/0.8."
            ),
            "cost_model": (
                "one full-data gradient is one exact unit; the minibatch is charged "
                "by its row-scan fraction (an explicit linear-scaling assumption); "
                "the frozen H=6 proof-cost measurement is a reused "
                "offline charge in every cold scenario"
            ),
            "decision_comparison": (
                "the exact joint H=6 certificate accepts qualifying transcripts; "
                "the exact independent-marginal rectangle for the same envelope "
                "rejects at certificate value one; direct acceptance after the free "
                "prefilter and always-query are reported as uncertified post-hoc "
                "comparators"
            ),
            "runtime_membership_verification": (
                "the runner reconstructs the full gradient at the origin and all "
                "proposal, residual, and distance squared norms as exact rationals "
                "from the stored binary64 inputs; no acceptance comparison uses "
                "an IEEE-754 norm"
            ),
            "zero_credit_first_decision_self_financing": False,
        },
        "configuration": {
            "seed": seed,
            "sample_count": sample_count,
            "dimension": dimension,
            "minibatch_count": minibatch_count,
            "episode_count": episode_count,
            "minibatch_fraction": cheap_ratio,
            "ridge_strong_convexity": ridge,
            "loss_scale": loss_scale,
            "proposal_mechanism": (
                "sampled-Hessian reduced-Newton step with a 0.009 safeguarded "
                "correction around -1.1*g(x)"
            ),
            "anchor_radius_range": list(anchor_radius_range),
            "anchor_distribution_selected_to_cross_band": False,
            "declared_pep_strong_convexity": 0.3,
            "declared_smoothness": 1.0,
            "tolerance": tolerance,
            "proposal_step": proposal_step,
            "proposal_norm_interval": [proposal_lower, proposal_upper],
            "contract_radius": contract_radius,
            "initial_distance_upper": distance_upper,
            "certified_horizon": horizon,
        },
        "summary": {
            "accepted_episode_count": len(accepted),
            "rejected_episode_count": rejected_count,
            "uncertified_episode_count": uncertified_count,
            "three_valued_attempt_count": (
                len(accepted) + rejected_count + uncertified_count
            ),
            "uncertified_reason_counts": uncertified_reason_counts,
            "acceptance_rate": len(accepted) / episode_count,
            "accepted_safety_violation_count": sum(
                row["accepted_from_short_transcript"]
                and row["candidate_calls_post_decision"]
                >= row["baseline_calls_post_decision"]
                for row in records
            ),
            "baseline_exact_calls": baseline_calls,
            "gated_exact_calls": gated_exact_calls,
            "saved_exact_calls_before_cheap_cost": saved_calls,
            "proposal_attempt_count": attempted_count,
            "cheap_proposal_exact_call_units": cheap_units,
            "warm_total_exact_call_units": warm_total_units,
            "warm_cost_ratio": warm_total_units / baseline_calls,
            "warm_net_saved_exact_call_units": baseline_calls - warm_total_units,
            "marginal_gate_accepted_episode_count": 0,
            "marginal_gate_total_exact_call_units": marginal_total_units,
            "marginal_gate_cost_ratio": marginal_total_units / baseline_calls,
            "greedy_prefilter_accept_count": attempted_count,
            "greedy_prefilter_exact_calls": greedy_prefilter_exact_calls,
            "greedy_prefilter_total_exact_call_units": (
                greedy_prefilter_total_units
            ),
            "greedy_prefilter_cost_ratio": (
                greedy_prefilter_total_units / baseline_calls
            ),
            "greedy_prefilter_candidate_nonimprovement_count": (
                greedy_prefilter_nonimproving
            ),
            "greedy_prefilter_pointwise_overrun_count": (
                greedy_prefilter_pointwise_overruns
            ),
            "always_query_total_exact_call_units": always_total_units,
            "always_query_cheap_proposal_exact_call_units": always_cheap_units,
            "always_query_cost_ratio": always_total_units / baseline_calls,
            "always_query_pointwise_overrun_count": always_pointwise_overruns,
            "always_query_risk_break_even_penalty_exact_units_per_overrun": (
                always_risk_break_even_penalty
            ),
            "exact_membership_decision_count": episode_count,
            "exact_maximum_feature_row_squared_norm": str(
                maximum_row_squared_norm
            ),
            "exact_smoothness_upper": str(exact_smoothness_upper),
            "safeguarded_correction_norm": _quantiles(
                [row["safeguarded_correction_norm"] for row in records]
            ),
            "safeguarded_correction_cosine_with_gradient": _quantiles(
                [
                    row["safeguarded_correction_cosine_with_gradient"]
                    for row in records
                ]
            ),
            "mean_warm_net_saving_per_episode": net_saving_per_episode,
            "proposal_norm": _quantiles(
                [row["proposal_norm"] for row in records]
            ),
            "contract_residual": _quantiles(
                [row["contract_residual"] for row in records]
            ),
            "distance_bound": _quantiles(
                [row["distance_bound"] for row in records]
            ),
            "maximum_realized_baseline_calls": max(
                row["baseline_calls_post_decision"] for row in records
            ),
            "maximum_realized_candidate_calls": max(
                row["candidate_calls_post_decision"] for row in records
            ),
        },
        "cold_cost_scenarios": cost_scenarios,
        "records": records,
        "evidence": {
            "certificate_payload_sha256": certificate["payload_sha256"],
            "certificate_file_sha256": _file_hash(CERTIFICATE),
            "certificate_cost_payload_sha256": cost_payload["payload_sha256"],
            "certificate_cost_file_sha256": _file_hash(COST_PAYLOAD),
            "runner_sha256": _file_hash(Path(__file__)),
        },
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--episodes", type=int, default=512)
    args = parser.parse_args()
    payload = run_workload(episode_count=args.episodes)
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = payload["summary"]
    print(
        "FROZEN: rolling logistic short-transcript gate, "
        f"accepted={summary['accepted_episode_count']}/{args.episodes}, "
        f"warm_ratio={summary['warm_cost_ratio']:.3f}, "
        f"violations={summary['accepted_safety_violation_count']}, "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
