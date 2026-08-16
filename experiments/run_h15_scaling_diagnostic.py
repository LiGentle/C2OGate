#!/usr/bin/env python3
"""Freeze one generic non-shift H=15 ragged scaling run."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from typing import Any

import cvxpy as cp
import numpy as np

from run_generic_pep_solver_benchmark import _single_run


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "h15_scaling_diagnostic.json"
SCHEMA = "c2o-h15-ragged-scaling-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> None:
    run = _single_run(15, "CLARABEL", 4)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": (
                "generic non-shift floating diagnostic using implemented ragged "
                "cell construction and four-worker enumeration"
            ),
            "proof_status": "uncertified",
            "purpose": (
                "quantify the next scaling point beyond the exact H=10 envelope; "
                "solver statuses are not acceptance evidence"
            ),
            "qualification": (
                "this is not shared-dual or chordal exact recovery; it measures "
                "the remaining barrier rather than claiming to solve it"
            ),
        },
        "run": run,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "cvxpy": cp.__version__,
            "clarabel": __import__("clarabel").__version__,
            "runner_sha256": _file_hash(Path(__file__)),
            "benchmark_sha256": _file_hash(
                ROOT / "experiments" / "run_generic_pep_solver_benchmark.py"
            ),
            "cell_builder_sha256": _file_hash(
                ROOT / "experiments" / "run_generic_pep_scaling_study.py"
            ),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "FROZEN: H=15 ragged floating diagnostic, "
        f"cells={run['bad_cell_count']}, wall={run['wall_seconds']:.1f}s, "
        f"rss={run['peak_rss_mib']:.1f}MiB, status=uncertified, "
        f"payload={payload['payload_sha256']}"
    )


if __name__ == "__main__":
    main()
