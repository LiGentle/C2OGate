#!/usr/bin/env python3
"""Measure and freeze the cost of the ten-cell generic PEP dual suite."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import ceil
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "experiments" / "generate_generic_pep_dual_certificate.py"
VERIFIER = ROOT / "tools" / "verify_generic_nonquadratic_pep_dual.py"
CERTIFICATE = ROOT / "certificates" / "generic_nonquadratic_pep_dual.json"
OUTPUT = ROOT / "results" / "certificate_cost_study.json"
SCHEMA = "c2o-certificate-cost-study-v2"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, environment: dict[str, str] | None = None) -> float:
    started = perf_counter()
    subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verifier-repeats", type=int, default=5)
    args = parser.parse_args()
    if args.verifier_repeats < 1:
        raise ValueError("verifier repeats must be positive")
    environment = dict(os.environ)
    pep_path = "/tmp/c2o-mpc-deps"
    environment["PYTHONPATH"] = f"{pep_path}:{ROOT / 'src'}"
    recovery_seconds = _run([sys.executable, str(GENERATOR)], environment=environment)
    verification_times = [
        _run(
            [
                sys.executable,
                str(VERIFIER),
                str(CERTIFICATE),
                "--root",
                str(ROOT),
            ]
        )
        for _ in range(args.verifier_repeats)
    ]
    verification_times.sort()
    median_verification = verification_times[len(verification_times) // 2]
    certificate_seconds = recovery_seconds + median_verification
    saved_exact_calls = 1
    exact_oracle_scenarios = [0.0001, 1.0, 10.0, 60.0]
    scenarios = []
    for exact_seconds in exact_oracle_scenarios:
        overhead_units = certificate_seconds / exact_seconds
        break_even_reuses = ceil(overhead_units / saved_exact_calls)
        scenarios.append(
            {
                "exact_oracle_seconds": exact_seconds,
                "certificate_cost_exact_call_units": overhead_units,
                "one_shot_self_financing": overhead_units <= saved_exact_calls,
                "minimum_offline_reuses": max(1, break_even_reuses),
            }
        )
    certificate_payload = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": (
                "machine-specific wall-clock accounting for the complete H=3 "
                "ten-cell generic dual suite; "
                "only offline or prepaid reuse is credited"
            ),
            "saved_exact_calls_per_accepted_decision": saved_exact_calls,
            "zero_credit_online_rejection_funded": False,
            "spx_exact_gradient_seconds_reference": 0.0001,
        },
        "measurement": {
            "solver_and_rational_recovery_seconds": recovery_seconds,
            "verification_repeats": args.verifier_repeats,
            "verification_seconds": verification_times,
            "median_verification_seconds": median_verification,
            "total_certificate_seconds": certificate_seconds,
        },
        "scenarios": scenarios,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "runner_sha256": _file_hash(Path(__file__)),
            "generator_sha256": _file_hash(GENERATOR),
            "verifier_sha256": _file_hash(VERIFIER),
            "certificate_payload_sha256": certificate_payload["payload_sha256"],
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"FROZEN: ten-cell generic PEP certificate cost {certificate_seconds:.3f}s; "
        f"60s-oracle break-even {scenarios[-1]['minimum_offline_reuses']} reuse(s)"
    )


if __name__ == "__main__":
    main()
