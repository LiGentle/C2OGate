#!/usr/bin/env python3
"""Reproducible stress test for the ex-ante Cost-Certified Oracle Gate."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from c2ogate import (  # noqa: E402
    DiagonalQuadratic,
    contraction_count_envelope,
    robust_cost_gate,
)
from c2ogate.quadratic import approximate_newton_contraction  # noqa: E402


SCHEMA = "c2o-quadratic-study-v1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quantiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "q05": float(np.quantile(array, 0.05)),
        "q95": float(np.quantile(array, 0.95)),
    }


def _run_case(
    rng: np.random.Generator,
    case_id: int,
    dimension: int,
    tolerance: float,
) -> dict[str, Any]:
    condition_number = float(np.exp(rng.uniform(np.log(1.0), np.log(3.0))))
    eigenvalues = np.geomspace(1.0, condition_number, dimension)
    rng.shuffle(eigenvalues)
    quadratic = DiagonalQuadratic(
        eigenvalues=eigenvalues,
        x_star=np.zeros(dimension),
        exact_step_size=0.49 / condition_number,
    )
    initial = quadratic.normalize_residual(rng.normal(size=dimension))
    initial_residual = quadratic.residual(initial)

    delta = float(np.exp(rng.uniform(np.log(1.0e-3), np.log(0.75))))
    relative_error = rng.uniform(-delta, delta, size=dimension)
    relative_error[int(rng.integers(0, dimension))] = delta * (
        -1.0 if rng.random() < 0.5 else 1.0
    )
    cheap_cost = float(rng.choice([0.25, 0.5, 1.0, 2.0, 4.0]))

    baseline_envelope = contraction_count_envelope(
        initial_residual,
        tolerance,
        quadratic.lower_contraction,
        quadratic.upper_contraction,
    )
    rho = approximate_newton_contraction(delta)
    certified_post_residual = rho * initial_residual
    post_envelope = contraction_count_envelope(
        certified_post_residual,
        tolerance,
        quadratic.lower_contraction,
        quadratic.upper_contraction,
    )
    decision = robust_cost_gate(
        baseline_envelope.lower,
        post_envelope.upper,
        cheap_cost,
        minimum_saved_calls=1,
    )

    candidate = quadratic.approximate_newton_step(initial, relative_error)
    candidate_residual = quadratic.residual(candidate)
    baseline_calls = quadratic.exact_calls_to_tolerance(initial, tolerance)
    post_calls = quadratic.exact_calls_to_tolerance(candidate, tolerance)

    gated_calls = post_calls if decision.accept else baseline_calls
    gated_cost = cheap_cost + post_calls if decision.accept else baseline_calls
    always_cost = cheap_cost + post_calls
    descent_accept = candidate_residual < initial_residual
    posthoc_calls = post_calls if descent_accept else baseline_calls
    posthoc_cost = cheap_cost + posthoc_calls

    return {
        "case_id": case_id,
        "dimension": dimension,
        "condition_number": condition_number,
        "delta_contract": delta,
        "rho_contract": rho,
        "cheap_cost_exact_units": cheap_cost,
        "initial_residual": initial_residual,
        "candidate_residual": candidate_residual,
        "candidate_contract_satisfied": candidate_residual
        <= certified_post_residual * (1.0 + 1.0e-12),
        "baseline_lower_calls": baseline_envelope.lower,
        "baseline_upper_calls": baseline_envelope.upper,
        "post_upper_calls": post_envelope.upper,
        "gate_accept": decision.accept,
        "guaranteed_saved_calls": decision.guaranteed_saved_exact_calls,
        "guaranteed_cost_slack": decision.guaranteed_cost_slack_exact_units,
        "baseline_actual_calls": baseline_calls,
        "post_actual_calls": post_calls,
        "gated_actual_calls": gated_calls,
        "gated_total_cost": gated_cost,
        "gated_cost_ratio": gated_cost / baseline_calls,
        "always_total_cost": always_cost,
        "always_cost_ratio": always_cost / baseline_calls,
        "posthoc_descent_accept": descent_accept,
        "posthoc_total_cost": posthoc_cost,
        "posthoc_cost_ratio": posthoc_cost / baseline_calls,
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in records if row["gate_accept"]]
    return {
        "case_count": len(records),
        "gate_accept_count": len(accepted),
        "gate_accept_rate": len(accepted) / len(records),
        "contract_violation_count": sum(
            not row["candidate_contract_satisfied"] for row in records
        ),
        "gate_cost_dominance_violation_count": sum(
            row["gated_total_cost"] > row["baseline_actual_calls"] + 1.0e-12
            for row in records
        ),
        "gate_exact_call_reduction_violation_count": sum(
            row["post_actual_calls"] > row["baseline_actual_calls"] - 1
            for row in accepted
        ),
        "accepted_realized_saved_calls": _quantiles([
            row["baseline_actual_calls"] - row["post_actual_calls"]
            for row in accepted
        ]) if accepted else {},
        "gated_cost_ratio": _quantiles([
            row["gated_cost_ratio"] for row in records
        ]),
        "always_cost_ratio": _quantiles([
            row["always_cost_ratio"] for row in records
        ]),
        "posthoc_cost_ratio": _quantiles([
            row["posthoc_cost_ratio"] for row in records
        ]),
        "always_worse_fraction": float(np.mean([
            row["always_cost_ratio"] > 1.0 + 1.0e-12 for row in records
        ])),
        "posthoc_worse_fraction": float(np.mean([
            row["posthoc_cost_ratio"] > 1.0 + 1.0e-12 for row in records
        ])),
        "accepted_gate_cost_ratio": _quantiles([
            row["gated_cost_ratio"] for row in accepted
        ]) if accepted else {},
    }


def _write_csv(records: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def _plot(records: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 12})
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6))

    policies = [
        ("C2O gate", "gated_cost_ratio", "#4C78A8"),
        ("Always query", "always_cost_ratio", "#F58518"),
        ("Post-hoc descent", "posthoc_cost_ratio", "#E45756"),
    ]
    data = [[row[key] for row in records] for _, key, _ in policies]
    violin = axes[0].violinplot(data, showmedians=True, showextrema=False)
    for body, (_, _, color) in zip(violin["bodies"], policies, strict=True):
        body.set_facecolor(color)
        body.set_alpha(0.75)
    axes[0].axhline(1.0, color="black", linestyle="--", linewidth=1)
    axes[0].set_xticks(range(1, 4), [label for label, _, _ in policies], rotation=16)
    axes[0].set_ylabel("Total cost / exact-only cost")
    axes[0].set_title("End-to-end cost")

    accepted = np.array([row["gate_accept"] for row in records])
    scatter = axes[1].scatter(
        [row["condition_number"] for row in records],
        [row["delta_contract"] for row in records],
        c=np.where(accepted, 1.0, 0.0),
        cmap="coolwarm",
        vmin=0,
        vmax=1,
        alpha=0.55,
        s=10,
    )
    del scatter
    axes[1].set_yscale("log")
    axes[1].set_xlabel("Condition number")
    axes[1].set_ylabel("Certified relative oracle error delta")
    axes[1].set_title("Pre-query gate (red = accept)")

    gate_rows = [row for row in records if row["gate_accept"]]
    axes[2].scatter(
        [row["guaranteed_saved_calls"] for row in gate_rows],
        [row["baseline_actual_calls"] - row["post_actual_calls"]
         for row in gate_rows],
        alpha=0.5,
        s=13,
        color="#54A24B",
    )
    max_value = max(
        [row["baseline_actual_calls"] - row["post_actual_calls"]
         for row in gate_rows] + [1]
    )
    axes[2].plot([0, max_value], [0, max_value], "k--", linewidth=1)
    axes[2].set_xlabel("Certified saved exact calls")
    axes[2].set_ylabel("Realized saved exact calls")
    axes[2].set_title("Certificate conservatism")

    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"c2o_study.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=2000)
    parser.add_argument("--dimension", type=int, default=64)
    parser.add_argument("--tolerance", type=float, default=1.0e-6)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--figure-dir", type=Path, default=ROOT / "figures")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    records = [
        _run_case(rng, index, args.dimension, args.tolerance)
        for index in range(args.cases)
    ]
    summary = _summarize(records)
    payload = {
        "schema": SCHEMA,
        "declaration": {
            "case_count": args.cases,
            "dimension": args.dimension,
            "tolerance": args.tolerance,
            "seed": args.seed,
            "condition_number_range": [1.0, 3.0],
            "delta_contract_range": [1.0e-3, 0.75],
            "cheap_cost_exact_units": [0.25, 0.5, 1.0, 2.0, 4.0],
            "exact_step": "alpha=0.49/L",
            "cheap_oracle": "one spectrally-certified approximate Newton step",
        },
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__).resolve()),
            "source_sha256": {
                str(path.relative_to(ROOT)): _file_hash(path)
                for path in sorted((ROOT / "src" / "c2ogate").glob("*.py"))
            },
        },
        "summary": summary,
        "records": records,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "study.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_csv(records, args.output_dir / "cases.csv")
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _plot(records, args.figure_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
