#!/usr/bin/env python3
"""Repeated two-solver benchmark for complete ragged joint-PEP enumerations."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from math import ceil, log
from pathlib import Path
import platform
import resource
import subprocess
import sys
from time import perf_counter
from typing import Any

import cvxpy as cp
import matplotlib.pyplot as plt
import numpy as np

from run_generic_pep_scaling_study import _solve_cell


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "generic_pep_solver_benchmark.json"
FIGURE = ROOT / "figures" / "generic_pep_solver_benchmark"
SCHEMA = "c2o-generic-pep-solver-benchmark-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _parameters(horizon: int, solver: str) -> dict[str, Any]:
    contraction = 0.9
    candidate_distance_upper = 1.81
    tolerance = candidate_distance_upper * contraction ** (horizon - 0.25)
    computed_horizon = ceil(
        log(tolerance / candidate_distance_upper) / log(contraction)
    )
    if computed_horizon != horizon:
        raise RuntimeError("parameters do not realize the requested horizon")
    return {
        "strong_convexity": 0.1,
        "smoothness": 1.0,
        "step_size": 1.0,
        "proposal_step": 1.0,
        "proposal_norm": 0.8,
        "contract_radius": 0.1,
        "initial_distance_upper": 1.0,
        "candidate_distance_upper": candidate_distance_upper,
        "contraction": contraction,
        "tolerance": tolerance,
        "solver": solver,
        "solver_tolerance": 1.0e-6,
        "solver_max_iterations": 50_000,
        "allow_solver_fallback": False,
        "signed_terminal_margin": True,
    }


def _peak_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return value / (1024.0**2)
    return value / 1024.0


def _single_run(horizon: int, solver: str, workers: int) -> dict[str, Any]:
    parameters = _parameters(horizon, solver)
    cells = [
        (baseline, hybrid)
        for baseline in range(horizon + 1)
        for hybrid in range(horizon + 1)
        if hybrid >= baseline
    ]
    tasks = [(baseline, hybrid, parameters) for baseline, hybrid in cells]
    started = perf_counter()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_solve_cell, task) for task in tasks]
        for future in as_completed(futures):
            rows.append(future.result())
    wall_seconds = perf_counter() - started
    rows.sort(key=lambda row: (row["baseline_calls"], row["hybrid_calls"]))
    return {
        "horizon": horizon,
        "solver": solver,
        "worker_count": workers,
        "bad_cell_count": len(rows),
        "wall_seconds": wall_seconds,
        "total_setup_cpu_seconds": sum(row["setup_seconds"] for row in rows),
        "total_solve_cpu_seconds": sum(row["solve_seconds"] for row in rows),
        "peak_rss_mib": _peak_rss_mib(),
        "maximum_gram_order": max(row["gram_order"] for row in rows),
        "median_gram_order": float(np.median([row["gram_order"] for row in rows])),
        "maximum_constraint_count": max(row["constraint_count"] for row in rows),
        "status_counts": {
            status: sum(row["status"] == status for row in rows)
            for status in sorted({row["status"] for row in rows})
        },
        "gram_orders": [row["gram_order"] for row in rows],
    }


def _quantiles(values: list[float]) -> dict[str, float]:
    data = np.asarray(values, dtype=float)
    return {
        "median": float(np.median(data)),
        "q25": float(np.quantile(data, 0.25)),
        "q75": float(np.quantile(data, 0.75)),
        "minimum": float(np.min(data)),
        "maximum": float(np.max(data)),
    }


def _summarize(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    keys = sorted({(row["solver"], row["horizon"]) for row in runs})
    for solver, horizon in keys:
        group = [
            row
            for row in runs
            if row["solver"] == solver and row["horizon"] == horizon
        ]
        summary.append(
            {
                "solver": solver,
                "horizon": horizon,
                "repeat_count": len(group),
                "bad_cell_count": group[0]["bad_cell_count"],
                "wall_seconds": _quantiles([row["wall_seconds"] for row in group]),
                "total_solve_cpu_seconds": _quantiles(
                    [row["total_solve_cpu_seconds"] for row in group]
                ),
                "peak_rss_mib": _quantiles([row["peak_rss_mib"] for row in group]),
                "maximum_gram_order": group[0]["maximum_gram_order"],
                "median_gram_order": group[0]["median_gram_order"],
                "maximum_constraint_count": group[0]["maximum_constraint_count"],
            }
        )
    return summary


def _plot(summary: list[dict[str, Any]], runs: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.8))
    colors = {"CLARABEL": "#4C78A8", "SCS": "#F58518"}
    for solver in sorted({row["solver"] for row in summary}):
        rows = [row for row in summary if row["solver"] == solver]
        horizons = [row["horizon"] for row in rows]
        medians = [row["wall_seconds"]["median"] for row in rows]
        lower = [
            row["wall_seconds"]["median"] - row["wall_seconds"]["q25"]
            for row in rows
        ]
        upper = [
            row["wall_seconds"]["q75"] - row["wall_seconds"]["median"]
            for row in rows
        ]
        axes[0].errorbar(
            horizons,
            medians,
            yerr=[lower, upper],
            marker="o",
            capsize=3,
            label=solver,
            color=colors[solver],
        )
        axes[1].plot(
            horizons,
            [row["peak_rss_mib"]["median"] for row in rows],
            marker="o",
            label=solver,
            color=colors[solver],
        )
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Natural horizon H")
    axes[0].set_ylabel("Wall time (s, log scale)")
    axes[0].set_title("Complete bad-cell enumeration")
    axes[0].legend(frameon=False)
    axes[1].set_xlabel("Natural horizon H")
    axes[1].set_ylabel("Peak RSS (MiB)")
    axes[1].set_title("Process memory")
    h10 = next(
        row
        for row in runs
        if row["horizon"] == 10 and row["solver"] == "CLARABEL"
    )
    axes[2].hist(
        h10["gram_orders"],
        bins=np.arange(3.5, 24.6, 2),
        color="#72B7B2",
        edgecolor="white",
    )
    axes[2].set_xlabel("Ragged Gram order")
    axes[2].set_ylabel("Number of H=10 cells")
    axes[2].set_title("Per-cell cone sizes")
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("pdf", "png"):
        fig.savefig(FIGURE.with_suffix(f".{suffix}"), dpi=220, bbox_inches="tight")
    plt.close(fig)


def _run_subprocess(horizon: int, solver: str, workers: int) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__)),
            "--single",
            "--horizon",
            str(horizon),
            "--solver",
            solver,
            "--workers",
            str(workers),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--solver", choices=("CLARABEL", "SCS"), default="CLARABEL")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--horizons", type=int, nargs="+", default=[2, 4, 6, 8, 10])
    args = parser.parse_args()
    if args.single:
        print(json.dumps(_single_run(args.horizon, args.solver, args.workers)))
        return
    installed = set(cp.installed_solvers())
    solvers = [solver for solver in ("CLARABEL", "SCS") if solver in installed]
    if solvers != ["CLARABEL", "SCS"]:
        raise RuntimeError("the benchmark requires both Clarabel and SCS")
    runs: list[dict[str, Any]] = []
    for solver in solvers:
        for horizon in args.horizons:
            for repeat in range(args.repeats):
                row = _run_subprocess(horizon, solver, args.workers)
                row["repeat"] = repeat
                runs.append(row)
                print(
                    f"solver={solver} H={horizon} repeat={repeat + 1}/{args.repeats} "
                    f"wall={row['wall_seconds']:.3f}s",
                    flush=True,
                )
    summary = _summarize(runs)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "horizons": args.horizons,
            "repeat_count": args.repeats,
            "solvers": solvers,
            "worker_count": args.workers,
            "cell_set": "all (r,s) with 0 <= r <= s <= H",
            "timing_scope": "model construction plus solve for every bad cell",
            "classification_scope": "floating diagnostic; timing is not a proof object",
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "clarabel": __import__("clarabel").__version__,
            "scs": __import__("scs").__version__,
            "runner_sha256": _file_hash(Path(__file__)),
            "cell_runner_sha256": _file_hash(
                ROOT / "experiments" / "run_generic_pep_scaling_study.py"
            ),
        },
        "summary": summary,
        "runs": runs,
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _plot(summary, runs)
    print(f"payload_sha256={payload['payload_sha256']}")


if __name__ == "__main__":
    main()
