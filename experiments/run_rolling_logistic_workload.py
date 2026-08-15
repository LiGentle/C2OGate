#!/usr/bin/env python3
"""Short-transcript C2OGate audit on a rolling nonlinear calibration workload.

The gate sees the current exact gradient, a 5% minibatch proposal, and analytic
class/envelope bounds.  Full gradients at the proposed and subsequent states
are evaluated only after the branch decision for a blinded outcome audit.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "rolling_logistic_workload.json"
CERTIFICATE = ROOT / "certificates" / "h10_generic_pep_dual.json"
COST_PAYLOAD = ROOT / "results" / "h10_certificate_cost_study.json"
SCHEMA = "c2o-rolling-logistic-workload-v1"


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
        "strong_convexity": "1/10",
        "smoothness": "1",
        "step_size": "1",
        "proposal_step": "1",
        "proposal_norm_lower": "79/100",
        "proposal_norm_upper": "81/100",
        "contract_radius": "1/10",
        "initial_distance_upper": "1",
        "tolerance": "2/3",
        "derived_trace_bound": "49",
    }
    if payload.get("parameters") != expected:
        raise RuntimeError("flagship certificate parameters changed")
    summary = payload.get("summary", {})
    if summary.get("certificate_count") != 66:
        raise RuntimeError("flagship certificate is incomplete")
    if not str(summary.get("maximum_certified_upper_bound", "")).startswith("-"):
        raise RuntimeError("flagship suite lacks strict bad-cell exclusion")


def run_workload(
    *,
    seed: int = 20260815,
    sample_count: int = 40_000,
    dimension: int = 20,
    minibatch_count: int = 2_000,
    episode_count: int = 256,
) -> dict[str, Any]:
    if not (0 < minibatch_count < sample_count):
        raise ValueError("minibatch must be a strict subset of the full workload")
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(sample_count, dimension))
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    labels = rng.binomial(1, 0.5, size=sample_count).astype(float)

    ridge = 0.8
    loss_scale = 0.8
    anchor_radius_center = 0.995
    anchor_radius_relative_range = (0.97, 1.03)
    tolerance = 2.0 / 3.0
    proposal_lower = 0.79
    proposal_upper = 0.81
    contract_radius = 0.1
    horizon = 10
    exact_data_gradient = (
        loss_scale * (features.T @ (0.5 - labels)) / sample_count
    )

    certificate = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    _validate_certificate(certificate)
    records: list[dict[str, Any]] = []
    for episode in range(episode_count):
        direction = rng.normal(size=dimension)
        direction /= np.linalg.norm(direction)
        anchor_radius = anchor_radius_center * rng.uniform(
            *anchor_radius_relative_range
        )
        anchor = anchor_radius * direction
        exact_gradient = exact_data_gradient - ridge * anchor
        indices = rng.choice(sample_count, size=minibatch_count, replace=False)
        cheap_data_gradient = (
            loss_scale
            * (features[indices].T @ (0.5 - labels[indices]))
            / minibatch_count
        )
        cheap_gradient = cheap_data_gradient - ridge * anchor
        candidate = -cheap_gradient
        proposal_norm = float(np.linalg.norm(candidate))
        contract_residual = float(np.linalg.norm(exact_gradient - cheap_gradient))
        distance_bound = float(np.linalg.norm(exact_gradient) / ridge)
        accepted = bool(
            proposal_lower <= proposal_norm <= proposal_upper
            and contract_residual <= contract_radius
            and distance_bound <= 1.0
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
                "accepted_from_short_transcript": accepted,
                "proposal_norm": proposal_norm,
                "contract_residual": contract_residual,
                "distance_bound": distance_bound,
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
    cheap_units = episode_count * cheap_ratio
    warm_total_units = gated_exact_calls + cheap_units
    net_saving_per_episode = (baseline_calls - warm_total_units) / episode_count
    if not accepted or net_saving_per_episode <= 0:
        raise RuntimeError("workload does not provide a positive warm-regime result")

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
                "a drifting regularization center, and a 5% minibatch proposal"
            ),
            "role": "realistic synthetic workload, not a real-data claim",
            "gate_timing": (
                "the decision uses only the already-observed full gradient at x, "
                "the minibatch proposal, analytic class constants, and the frozen "
                "H=10 proof; all candidate/future full gradients are held out until "
                "the post-decision outcome audit"
            ),
            "function": (
                "0.8*mean(log(1+exp(a_i^T w))-b_i a_i^T w) "
                "+ 0.4*||w-anchor||^2"
            ),
            "class_proof": (
                "||a_i||=1 gives 0.8 I <= Hessian <= I because sigmoid'<=1/4; "
                "hence the workload lies in F_{0.8,1}, a subset of F_{0.1,1}. "
                "Strong monotonicity gives ||x-x_*||<=||grad f(x)||/0.8."
            ),
            "cost_model": (
                "one full-data gradient is one exact unit; the minibatch is charged "
                "by its row-scan fraction; the frozen proof's measured search plus "
                "verification time is charged separately in every cold scenario"
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
            "anchor_radius_center": anchor_radius_center,
            "anchor_radius_relative_range": list(anchor_radius_relative_range),
            "declared_pep_strong_convexity": 0.1,
            "declared_smoothness": 1.0,
            "tolerance": tolerance,
            "proposal_norm_interval": [proposal_lower, proposal_upper],
            "contract_radius": contract_radius,
            "certified_horizon": horizon,
        },
        "summary": {
            "accepted_episode_count": len(accepted),
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
            "cheap_proposal_exact_call_units": cheap_units,
            "warm_total_exact_call_units": warm_total_units,
            "warm_cost_ratio": warm_total_units / baseline_calls,
            "warm_net_saved_exact_call_units": baseline_calls - warm_total_units,
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
    parser.add_argument("--episodes", type=int, default=256)
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
