#!/usr/bin/env python3
"""Verify all successfully recovered SCS duals and the diagnostic ledger."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import verify_h10_generic_pep_dual as base


SCHEMA = "c2o-scs-recovery-diagnostic-v1"
CELLS = [(0, 0), (0, 5), (0, 10), (3, 3), (3, 7), (5, 5), (5, 10), (8, 8), (10, 10)]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def verify_payload(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    unsigned = dict(payload)
    recorded = unsigned.pop("payload_sha256", None)
    _require(recorded == sha256(_canonical(unsigned)).hexdigest(), "payload hash")
    _require(payload.get("schema") == SCHEMA, "schema")
    _require(payload["declaration"]["cells"] == [list(cell) for cell in CELLS], "cells")
    rows = payload["rows"]
    _require([row["cell"] for row in rows] == [list(cell) for cell in CELLS], "row order")
    successes = []
    for row in rows:
        _require(row["recovery_outcome"] in {"success", "failure"}, "outcome")
        if row["recovery_outcome"] == "success":
            upper, pivots = base._verify_certificate(row["certificate"])
            _require(upper < 0 and pivots == 24, "exact recovered certificate")
            successes.append(row)
        else:
            _require("certificate" not in row, "failed recovery certificate")
            _require(bool(row.get("diagnostic")), "failure diagnostic")
    summary = payload["summary"]
    _require(summary["cell_count"] == len(rows) == 9, "cell count")
    _require(summary["recovery_success_count"] == len(successes), "success count")
    _require(summary["recovery_failure_count"] == 9 - len(successes), "failure count")
    _require(
        summary["exact_positive_ldl_pivot_count"] == 24 * len(successes),
        "pivot count",
    )
    if root is not None:
        environment = payload["environment"]
        _require(
            environment["runner_sha256"]
            == _file_hash(root / "experiments" / "run_scs_recovery_diagnostic.py"),
            "runner hash",
        )
        _require(environment["verifier_sha256"] == _file_hash(Path(__file__)), "verifier hash")
    return {
        "payload_sha256": recorded,
        "success_count": len(successes),
        "failure_count": 9 - len(successes),
        "positive_ldl_pivots": 24 * len(successes),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    result = verify_payload(
        json.loads(args.payload.read_text(encoding="utf-8")), root=args.root
    )
    print(
        "VERIFIED: SCS producer diagnostic, "
        f"{result['success_count']}/9 exact recoveries, "
        f"{result['failure_count']} fail-closed outcomes"
    )


if __name__ == "__main__":
    main()
