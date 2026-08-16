#!/usr/bin/env python3
"""Real-data short-transcript benchmark on the UCI WDBC dataset."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import platform
import sys
from time import perf_counter
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
DATA = ROOT / "data" / "uci_wdbc" / "wdbc.data"
CERTIFICATE = ROOT / "certificates" / "h6_joint_only_pep_dual.json"
COST_PAYLOAD = ROOT / "results" / "h6_certificate_cost_study.json"
OUTPUT = ROOT / "results" / "uci_wdbc_gate_benchmark.json"
SCHEMA = "c2o-uci-wdbc-gate-benchmark-v3"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def _load_data() -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.reader(DATA.open(encoding="utf-8", newline="")))
    features = np.asarray(
        [[float(value) for value in row[2:]] for row in rows], dtype=float
    )
    labels = np.asarray([1.0 if row[1] == "M" else 0.0 for row in rows])
    means = np.mean(features, axis=0)
    scales = np.std(features, axis=0)
    if np.any(scales <= 0.0):
        raise RuntimeError("WDBC preprocessing encountered a constant feature")
    features = (features - means) / scales
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    features /= norms
    if features.shape != (569, 30) or set(labels) != {0.0, 1.0}:
        raise RuntimeError("unexpected WDBC shape or labels")
    return features, labels


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
) -> int:
    point = start.copy()
    for calls in range(horizon + 1):
        gradient = (
            ridge * (point - anchor)
            + loss_scale
            * (features.T @ (_sigmoid(features @ point) - labels))
            / len(labels)
        )
        if float(np.linalg.norm(gradient)) <= tolerance:
            return calls
        point -= gradient
    raise RuntimeError("WDBC continuation exceeded the certified horizon")


def _quantiles(values: list[float]) -> dict[str, float]:
    data = np.asarray(values, dtype=float)
    return {
        "minimum": float(np.min(data)),
        "q25": float(np.quantile(data, 0.25)),
        "median": float(np.median(data)),
        "q75": float(np.quantile(data, 0.75)),
        "maximum": float(np.max(data)),
    }


def run_benchmark(
    *,
    seed: int = 20260816,
    episode_count: int = 512,
    sketch_fraction: Fraction = Fraction(1, 10),
) -> dict[str, Any]:
    features, labels = _load_data()
    rng = np.random.default_rng(seed)
    ridge = Fraction(4, 5)
    loss_scale = Fraction(79, 100)
    proposal_step = Fraction(11, 10)
    proposal_lower = Fraction(27, 50)
    proposal_upper = Fraction(14, 25)
    contract_radius = Fraction(1, 100)
    distance_upper = Fraction(9, 5)
    tolerance = Fraction(7, 25)
    correction_cap = 9.0 / 1000.0
    horizon = 6
    sketch_count = int(round(float(sketch_fraction) * len(labels)))

    exact_data_gradient = exact_linear_data_gradient(
        features, labels, loss_scale
    )
    maximum_row_squared_norm = exact_max_row_squared_norm(features)
    smoothness_upper = ridge + loss_scale * maximum_row_squared_norm / 4
    if smoothness_upper > 1:
        raise RuntimeError("preprocessed WDBC rows do not certify L <= 1")

    certificate = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    if certificate["summary"]["certificate_count"] != 28:
        raise RuntimeError("the H=6 certificate is incomplete")
    records: list[dict[str, Any]] = []
    proposal_seconds: list[float] = []
    exact_gradient_seconds: list[float] = []
    for episode in range(episode_count):
        direction = features[int(rng.integers(len(features)))].copy()
        direction /= np.linalg.norm(direction)
        anchor = rng.uniform(0.30, 0.95) * direction
        anchor_fraction = binary64_vector(anchor)
        gradient_fraction = tuple(
            data_value - ridge * anchor_value
            for data_value, anchor_value in zip(
                exact_data_gradient, anchor_fraction, strict=True
            )
        )
        gradient = np.asarray([float(value) for value in gradient_fraction])
        gradient_squared = rational_squared_norm(gradient_fraction)
        attempted = bool(
            (proposal_lower - contract_radius) ** 2
            <= proposal_step**2 * gradient_squared
            <= (proposal_upper + contract_radius) ** 2
        )

        indices = rng.choice(len(labels), size=sketch_count, replace=False)
        proposal_started = perf_counter()
        diagonal_model = np.asarray(
            [float(ridge)] * features.shape[1]
        ) + 0.25 * float(loss_scale) * np.mean(features[indices] ** 2, axis=0)
        raw_reduced_newton = -gradient / diagonal_model
        gradient_center = -float(proposal_step) * gradient
        correction = raw_reduced_newton - gradient_center
        raw_correction_norm = float(np.linalg.norm(correction))
        if raw_correction_norm > correction_cap:
            correction *= correction_cap / raw_correction_norm
        candidate = gradient_center + correction
        proposal_seconds.append(perf_counter() - proposal_started)

        membership = certify_h6_envelope_membership(
            candidate,
            gradient_fraction,
            proposal_step=proposal_step,
            proposal_lower=proposal_lower,
            proposal_upper=proposal_upper,
            contract_radius=contract_radius,
            strong_monotonicity=ridge,
            distance_upper=distance_upper,
        )
        accepted = attempted and membership.accepted
        decision_outcome = (
            "accept" if accepted else "uncertified" if attempted else "not_attempted"
        )
        uncertified_reasons = []
        if attempted and not accepted:
            if not membership.proposal_band_passed:
                uncertified_reasons.append("proposal_band")
            if not membership.residual_ball_passed:
                uncertified_reasons.append("residual_ball")
            if not membership.distance_bound_passed:
                uncertified_reasons.append("distance_bound")

        exact_started = perf_counter()
        _ = (
            float(ridge) * (np.zeros(features.shape[1]) - anchor)
            + float(loss_scale)
            * (features.T @ (0.5 - labels))
            / len(labels)
        )
        exact_gradient_seconds.append(perf_counter() - exact_started)
        baseline_calls = _remaining_calls(
            np.zeros(features.shape[1]),
            anchor,
            features=features,
            labels=labels,
            ridge=float(ridge),
            loss_scale=float(loss_scale),
            tolerance=float(tolerance),
            horizon=horizon,
        )
        candidate_calls = _remaining_calls(
            candidate,
            anchor,
            features=features,
            labels=labels,
            ridge=float(ridge),
            loss_scale=float(loss_scale),
            tolerance=float(tolerance),
            horizon=horizon,
        )
        if accepted and candidate_calls >= baseline_calls:
            raise RuntimeError("accepted WDBC episode violates the H=6 proof")
        records.append(
            {
                "episode": episode,
                "attempted_after_exact_prefilter": attempted,
                "accepted_by_joint_gate": accepted,
                "decision_outcome": decision_outcome,
                "uncertified_reasons": uncertified_reasons,
                "proposal_squared_norm_exact": str(
                    membership.proposal_squared_norm
                ),
                "residual_squared_norm_exact": str(
                    membership.residual_squared_norm
                ),
                "gradient_squared_norm_exact": str(
                    membership.gradient_squared_norm
                ),
                "raw_reduced_newton_correction_norm": raw_correction_norm,
                "safeguarded_correction_norm": float(np.linalg.norm(correction)),
                "safeguarded_correction_cosine_with_gradient": float(
                    np.dot(correction, gradient)
                    / max(
                        float(np.linalg.norm(correction))
                        * float(np.linalg.norm(gradient)),
                        1.0e-30,
                    )
                ),
                "baseline_calls_post_decision": baseline_calls,
                "candidate_calls_post_decision": candidate_calls,
            }
        )

    attempts = sum(row["attempted_after_exact_prefilter"] for row in records)
    accepted = sum(row["accepted_by_joint_gate"] for row in records)
    rejected = sum(row["decision_outcome"] == "reject" for row in records)
    uncertified = sum(
        row["decision_outcome"] == "uncertified" for row in records
    )
    reason_counts = {
        reason: sum(reason in row["uncertified_reasons"] for row in records)
        for reason in ("proposal_band", "residual_ball", "distance_bound")
    }
    baseline_calls = sum(row["baseline_calls_post_decision"] for row in records)
    gated_calls = sum(
        row["candidate_calls_post_decision"]
        if row["accepted_by_joint_gate"]
        else row["baseline_calls_post_decision"]
        for row in records
    )
    cheap_units = attempts * float(sketch_fraction)
    warm_units = gated_calls + cheap_units
    marginal_units = baseline_calls + cheap_units
    greedy_prefilter_exact_calls = sum(
        row["candidate_calls_post_decision"]
        if row["attempted_after_exact_prefilter"]
        else row["baseline_calls_post_decision"]
        for row in records
    )
    greedy_prefilter_units = greedy_prefilter_exact_calls + cheap_units
    greedy_prefilter_overruns = sum(
        row["attempted_after_exact_prefilter"]
        and row["candidate_calls_post_decision"] + float(sketch_fraction)
        > row["baseline_calls_post_decision"]
        for row in records
    )
    greedy_prefilter_nonimproving = sum(
        row["attempted_after_exact_prefilter"]
        and row["candidate_calls_post_decision"]
        >= row["baseline_calls_post_decision"]
        for row in records
    )
    always_units = sum(
        row["candidate_calls_post_decision"] for row in records
    ) + episode_count * float(sketch_fraction)
    always_overruns = sum(
        row["candidate_calls_post_decision"] + float(sketch_fraction)
        > row["baseline_calls_post_decision"]
        for row in records
    )
    risk_penalty = (
        max(0.0, warm_units - always_units) / always_overruns
        if always_overruns
        else None
    )
    proposal_timing = _quantiles(proposal_seconds)
    exact_timing = _quantiles(exact_gradient_seconds)
    measured_proposal_exact_unit_ratio = (
        proposal_timing["median"] / exact_timing["median"]
    )
    measured_warm_cost_ratio = (
        gated_calls + attempts * measured_proposal_exact_unit_ratio
    ) / baseline_calls
    measured_greedy_prefilter_cost_ratio = (
        greedy_prefilter_exact_calls
        + attempts * measured_proposal_exact_unit_ratio
    ) / baseline_calls
    net_saving_per_episode = (baseline_calls - warm_units) / episode_count
    certificate_cost = json.loads(COST_PAYLOAD.read_text(encoding="utf-8"))
    certificate_seconds = float(
        certificate_cost["measurement"]["total_certificate_seconds"]
    )
    economic_scenarios = []
    for exact_oracle_seconds in (1.0, 10.0, 60.0, 600.0):
        certificate_units = certificate_seconds / exact_oracle_seconds
        economic_scenarios.append(
            {
                "exact_oracle_seconds": exact_oracle_seconds,
                "certificate_cost_exact_units": certificate_units,
                "break_even_episodes": ceil(
                    certificate_units / net_saving_per_episode
                ),
                "observed_batch_all_in_ratio": (
                    warm_units + certificate_units
                )
                / baseline_calls,
                "observed_batch_self_financing": (
                    warm_units + certificate_units <= baseline_calls
                ),
            }
        )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "dataset": "UCI Breast Cancer Wisconsin (Diagnostic), dataset 17",
            "dataset_doi": "10.24432/C5DW2B",
            "dataset_license": "CC BY 4.0",
            "role": (
                "real-data external benchmark for a short-transcript decision; "
                "not a clinical claim or a production deployment"
            ),
            "proposal": (
                "10% sampled diagonal-Hessian reduced-Newton step, safeguarded "
                "by a 0.009 correction around the gradient center"
            ),
            "membership": (
                "all accepted proposal, residual, distance, row-norm, and class "
                "bounds are recomputed from stored binary64 inputs with exact "
                "fractions.Fraction arithmetic"
            ),
            "marginal_comparator": (
                "the sharp independent-marginal certificate for the same H=6 "
                "envelope rejects at value one"
            ),
            "greedy_comparator": (
                "every proposal passing the free prefilter is accepted without a "
                "certificate; its cost and violations are computed only in the "
                "post-decision audit and carry no robust guarantee"
            ),
            "economic_scope": (
                "row-scan units and hypothetical expensive-oracle conversions "
                "are reported separately from measured small-dataset wall time"
            ),
        },
        "configuration": {
            "seed": seed,
            "episode_count": episode_count,
            "row_count": len(labels),
            "dimension": features.shape[1],
            "sketch_count": sketch_count,
            "sketch_fraction": float(sketch_fraction),
            "anchor_radius_range": [0.30, 0.95],
            "anchor_distribution_selected_to_cross_band": False,
            "ridge": str(ridge),
            "loss_scale": str(loss_scale),
            "tolerance": str(tolerance),
            "horizon": horizon,
        },
        "summary": {
            "proposal_attempt_count": attempts,
            "joint_accept_count": accepted,
            "joint_reject_count": rejected,
            "joint_uncertified_count": uncertified,
            "joint_three_valued_attempt_count": accepted + rejected + uncertified,
            "uncertified_reason_counts": reason_counts,
            "marginal_accept_count": 0,
            "accepted_violation_count": sum(
                row["accepted_by_joint_gate"]
                and row["candidate_calls_post_decision"]
                >= row["baseline_calls_post_decision"]
                for row in records
            ),
            "baseline_exact_calls": baseline_calls,
            "gated_exact_calls": gated_calls,
            "warm_cost_ratio": warm_units / baseline_calls,
            "measured_time_warm_cost_ratio": measured_warm_cost_ratio,
            "measured_proposal_exact_unit_ratio": (
                measured_proposal_exact_unit_ratio
            ),
            "marginal_cost_ratio": marginal_units / baseline_calls,
            "greedy_prefilter_accept_count": attempts,
            "greedy_prefilter_exact_calls": greedy_prefilter_exact_calls,
            "greedy_prefilter_cost_ratio": greedy_prefilter_units / baseline_calls,
            "greedy_prefilter_measured_time_cost_ratio": (
                measured_greedy_prefilter_cost_ratio
            ),
            "greedy_prefilter_candidate_nonimprovement_count": (
                greedy_prefilter_nonimproving
            ),
            "greedy_prefilter_pointwise_overrun_count": (
                greedy_prefilter_overruns
            ),
            "always_query_cost_ratio": always_units / baseline_calls,
            "always_query_pointwise_overrun_count": always_overruns,
            "always_query_risk_break_even_penalty_exact_units_per_overrun": (
                risk_penalty
            ),
            "exact_membership_decision_count": episode_count,
            "exact_maximum_feature_row_squared_norm": str(
                maximum_row_squared_norm
            ),
            "exact_smoothness_upper": str(smoothness_upper),
            "safeguarded_correction_norm": _quantiles(
                [row["safeguarded_correction_norm"] for row in records]
            ),
            "safeguarded_correction_cosine_with_gradient": _quantiles(
                [
                    row["safeguarded_correction_cosine_with_gradient"]
                    for row in records
                ]
            ),
            "measured_proposal_seconds": proposal_timing,
            "measured_single_full_gradient_seconds": exact_timing,
        },
        "economic_scenarios": economic_scenarios,
        "records": records,
        "evidence": {
            "data_sha256": _file_hash(DATA),
            "certificate_payload_sha256": certificate["payload_sha256"],
            "certificate_file_sha256": _file_hash(CERTIFICATE),
            "certificate_cost_payload_sha256": certificate_cost["payload_sha256"],
            "runner_sha256": _file_hash(Path(__file__)),
        },
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = run_benchmark()
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = payload["summary"]
    print(
        "FROZEN: UCI-WDBC exact-membership gate, "
        f"joint={summary['joint_accept_count']}/"
        f"{summary['proposal_attempt_count']}, marginal=0, "
        f"warm_ratio={summary['warm_cost_ratio']:.3f}, "
        f"violations={summary['accepted_violation_count']}, "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
