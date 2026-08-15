#!/usr/bin/env python3
"""Bind three independently recovered and two transported H=10 envelopes."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "certificates" / "h10_envelope_family.json"
VERIFIER = ROOT / "tools" / "verify_h10_envelope_family.py"
SCHEMA = "c2o-h10-envelope-family-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sources = [
        ("balanced", "certificates/h10_generic_pep_dual.json"),
        ("candidate_heavy", "certificates/h10_candidate_heavy_pep_dual.json"),
        ("tight_contract", "certificates/h10_tight_contract_pep_dual.json"),
    ]
    source_rows = []
    for name, relative in sources:
        path = ROOT / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_rows.append(
            {
                "name": name,
                "path": relative,
                "file_sha256": _file_hash(path),
                "payload_sha256": payload["payload_sha256"],
                "source_kind": "independent Clarabel recovery",
            }
        )
    transports = [
        {
            "name": "balanced_scale_4_5",
            "source": "balanced",
            "scale": "4/5",
            "source_kind": "exact homogeneous transport",
        },
        {
            "name": "balanced_scale_6_5",
            "source": "balanced",
            "scale": "6/5",
            "source_kind": "exact homogeneous transport",
        },
    ]
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "profile_count": 5,
            "independently_recovered_profile_count": 3,
            "transported_profile_count": 2,
            "horizon": 10,
            "bad_cells_per_profile": 66,
            "claim": (
                "all 330 profile-cell exclusions are exact; 198 are independently "
                "recovered and 132 follow by checked homogeneous transport"
            ),
        },
        "sources": source_rows,
        "transports": transports,
        "transport_rule": {
            "scaled_fields": [
                "proposal_norm_lower",
                "proposal_norm_upper",
                "contract_radius",
                "initial_distance_upper",
                "tolerance",
            ],
            "squared_field": "derived_trace_bound",
            "invariant_fields": [
                "strong_convexity",
                "smoothness",
                "step_size",
                "proposal_step",
            ],
            "dual_effect": (
                "stationarity and slack are unchanged; every dual objective is "
                "multiplied by scale^2"
            ),
        },
        "environment": {
            "builder_sha256": _file_hash(Path(__file__)),
            "verifier_sha256": _file_hash(VERIFIER),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "BOUND: five H=10 envelopes, 198 independently recovered and "
        "132 exact transported exclusions"
    )


if __name__ == "__main__":
    main()
