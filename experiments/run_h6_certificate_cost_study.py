#!/usr/bin/env python3
"""Measure the full producer-plus-consumer cost of the H=6 joint-only suite."""

from __future__ import annotations

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
CERTIFICATE = ROOT / "certificates" / "h6_joint_only_pep_dual.json"
VERIFIER = ROOT / "tools" / "verify_h6_joint_only_pep_dual.py"
OUTPUT = ROOT / "results" / "h6_certificate_cost_study.json"
SCHEMA = "c2o-h6-certificate-cost-study-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> None:
    certificate = json.loads(CERTIFICATE.read_text(encoding="utf-8"))
    verification_seconds: list[float] = []
    for _ in range(3):
        started = perf_counter()
        subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                str(CERTIFICATE),
                "--root",
                str(ROOT),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        verification_seconds.append(perf_counter() - started)
    verification_seconds.sort()
    verification_median = verification_seconds[1]
    generation_seconds = float(
        certificate["summary"]["generation_wall_seconds"]
    )
    total_seconds = generation_seconds + verification_median
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "base_nonexact_cost_exact_call_units": 0.4,
            "certificate_budget_exact_call_units": 0.6,
            "saved_exact_calls_per_accepted_decision": 1.0,
            "scope": (
                "machine-specific all-in proof cost for the natural-H=6, "
                "28-cell nonzero-radius joint-only suite"
            ),
            "zero_credit_online_rejection_funded": False,
        },
        "measurement": {
            "solver_and_rational_recovery_seconds": generation_seconds,
            "verification_repeats": 3,
            "verification_seconds": verification_seconds,
            "median_verification_seconds": verification_median,
            "total_certificate_seconds": total_seconds,
        },
        "scenarios": [
            {
                "exact_oracle_seconds": exact_seconds,
                "certificate_cost_exact_call_units": total_seconds / exact_seconds,
                "minimum_offline_reuses": ceil(
                    total_seconds / (0.6 * exact_seconds)
                ),
                "one_shot_self_financing": total_seconds / exact_seconds <= 0.6,
            }
            for exact_seconds in (0.0001, 1.0, 10.0, 60.0, 600.0, 3600.0)
        ],
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "certificate_payload_sha256": certificate["payload_sha256"],
            "certificate_file_sha256": _file_hash(CERTIFICATE),
            "runner_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(VERIFIER),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "MEASURED: H=6 proof cost, "
        f"generation={generation_seconds:.3f}s, "
        f"verification median={verification_median:.3f}s, "
        f"total={total_seconds:.3f}s"
    )


if __name__ == "__main__":
    main()
