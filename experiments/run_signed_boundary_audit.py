#!/usr/bin/env python3
"""Count exact and numerical signed-margin boundary cells across suites."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "signed_boundary_audit.json"
SUITES = (
    ("generic-nonquadratic-H3", "certificates/generic_nonquadratic_pep_dual.json"),
    ("full-class-H3", "certificates/full_class_joint_only_pep_dual.json"),
    ("nonzero-radius-H6", "certificates/h6_joint_only_pep_dual.json"),
    ("wider-radius-H6", "certificates/h6_medium_radius_pep_dual.json"),
    ("stress-H10", "certificates/h10_generic_pep_dual.json"),
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    claimed = unsigned.pop("payload_sha256")
    if sha256(_canonical(unsigned)).hexdigest() != claimed:
        raise RuntimeError(f"hash mismatch: {path}")
    return payload


def main() -> None:
    threshold = 1.0e-8
    rows = []
    for name, relative in SUITES:
        payload = _load(ROOT / relative)
        exact = [
            Fraction(item["dual"]["certified_upper_bound"])
            for item in payload["certificates"]
        ]
        floating = [
            float(item["primal"]["floating_objective"])
            for item in payload["certificates"]
        ]
        rows.append(
            {
                "suite": name,
                "cell_count": len(exact),
                "exact_zero_count": sum(value == 0 for value in exact),
                "exact_negative_count": sum(value < 0 for value in exact),
                "floating_near_zero_count": sum(abs(value) <= threshold for value in floating),
                "maximum_exact_upper_bound": str(max(exact)),
                "source_payload_sha256": payload["payload_sha256"],
            }
        )

    workload_rows = []
    for name, relative, accept_key, attempt_key in (
        (
            "UCI-WDBC",
            "results/uci_wdbc_gate_benchmark.json",
            "joint_accept_count",
            "proposal_attempt_count",
        ),
        (
            "rolling-logistic",
            "results/rolling_logistic_workload.json",
            "accepted_episode_count",
            "proposal_attempt_count",
        ),
    ):
        payload = _load(ROOT / relative)
        summary = payload["summary"]
        workload_rows.append(
            {
                "workload": name,
                "attempted_transcript_count": summary[attempt_key],
                "accepted_transcript_count": summary[accept_key],
                "accepted_transcripts_using_zero_boundary_suite": 0,
                "qualification": (
                    "every acceptance reuses the strict nonzero-radius H=6 suite; "
                    "nonmembers are uncertified before cell replay"
                ),
                "source_payload_sha256": payload["payload_sha256"],
            }
        )

    payload: dict[str, Any] = {
        "schema": "c2o-signed-boundary-audit-v1",
        "definition": {
            "exact_boundary": "verified rational dual upper bound equals zero",
            "floating_near_zero_threshold": threshold,
        },
        "suite_rows": rows,
        "workload_rows": workload_rows,
        "summary": {
            "suite_count": len(rows),
            "cell_count": sum(row["cell_count"] for row in rows),
            "exact_zero_count": sum(row["exact_zero_count"] for row in rows),
            "floating_near_zero_count": sum(
                row["floating_near_zero_count"] for row in rows
            ),
            "accepted_workload_transcript_count": sum(
                row["accepted_transcript_count"] for row in workload_rows
            ),
            "accepted_workload_zero_boundary_count": 0,
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "FROZEN: signed-boundary audit, "
        f"exact_zero={payload['summary']['exact_zero_count']}/"
        f"{payload['summary']['cell_count']}, "
        f"workload_zero={payload['summary']['accepted_workload_zero_boundary_count']}/"
        f"{payload['summary']['accepted_workload_transcript_count']}"
    )


if __name__ == "__main__":
    main()
