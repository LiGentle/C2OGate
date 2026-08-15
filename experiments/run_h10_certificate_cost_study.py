#!/usr/bin/env python3
"""Measure and freeze the full natural-H=10 proof-replay cost ledger."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "experiments" / "generate_h10_generic_pep_dual_certificate.py"
VERIFIER = ROOT / "tools" / "verify_h10_generic_pep_dual.py"
CERTIFICATE = ROOT / "certificates" / "h10_generic_pep_dual.json"
OUTPUT = ROOT / "results" / "h10_certificate_cost_study.json"
SCHEMA = "c2o-h10-certificate-cost-study-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _run_verifier() -> float:
    started = perf_counter()
    subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            str(CERTIFICATE),
            "--root",
            str(ROOT),
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verifier-repeats", type=int, default=1)
    args = parser.parse_args()
    if args.verifier_repeats < 1:
        raise ValueError("verifier repeats must be positive")
    certificate = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    search_seconds = float(certificate["summary"]["generation_wall_seconds"])
    verification_times = sorted(
        _run_verifier() for _ in range(args.verifier_repeats)
    )
    median_verification = verification_times[len(verification_times) // 2]
    total_seconds = search_seconds + median_verification
    saved_exact_calls = 1.0
    base_nonexact_cost = 0.4
    certificate_budget = saved_exact_calls - base_nonexact_cost
    scenarios = []
    for exact_seconds in (0.0001, 1.0, 10.0, 60.0, 600.0, 3600.0):
        overhead_units = total_seconds / exact_seconds
        scenarios.append(
            {
                "exact_oracle_seconds": exact_seconds,
                "certificate_cost_exact_call_units": overhead_units,
                "one_shot_self_financing": overhead_units <= certificate_budget,
                "minimum_offline_reuses": max(
                    1, ceil(overhead_units / certificate_budget)
                ),
            }
        )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": (
                "machine-specific all-in proof cost for the natural-H=10, "
                "66-cell generic dual suite; only offline or prepaid reuse is credited"
            ),
            "search_timing_source": (
                "generation_wall_seconds frozen by the certificate generator"
            ),
            "saved_exact_calls_per_accepted_decision": saved_exact_calls,
            "base_nonexact_cost_exact_call_units": base_nonexact_cost,
            "certificate_budget_exact_call_units": certificate_budget,
            "zero_credit_online_rejection_funded": False,
        },
        "measurement": {
            "solver_and_rational_recovery_seconds": search_seconds,
            "verification_repeats": args.verifier_repeats,
            "verification_seconds": verification_times,
            "median_verification_seconds": median_verification,
            "total_certificate_seconds": total_seconds,
        },
        "scenarios": scenarios,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__)),
            "generator_sha256": _file_hash(GENERATOR),
            "verifier_sha256": _file_hash(VERIFIER),
            "certificate_payload_sha256": certificate["payload_sha256"],
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sixty = next(
        row for row in scenarios if row["exact_oracle_seconds"] == 60.0
    )
    print(
        "FROZEN: natural-H=10 certificate cost "
        f"{total_seconds:.3f}s = {search_seconds:.3f}s search + "
        f"{median_verification:.3f}s replay; 60s-oracle break-even "
        f"{sixty['minimum_offline_reuses']} reuse(s)"
    )


if __name__ == "__main__":
    main()
