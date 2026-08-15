#!/usr/bin/env python3
"""Exact standard-library verifier for the five-profile H=10 envelope family."""

from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import verify_h10_generic_pep_dual as base


SCHEMA = "c2o-h10-envelope-family-v1"
PROFILE_SCHEMA = "c2o-h10-envelope-profile-v1"
EXPECTED_SOURCES = {
    "balanced": "certificates/h10_generic_pep_dual.json",
    "candidate_heavy": "certificates/h10_candidate_heavy_pep_dual.json",
    "tight_contract": "certificates/h10_tight_contract_pep_dual.json",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _parse_parameters(payload: dict[str, Any]) -> dict[str, Fraction]:
    parameters = {key: Fraction(value) for key, value in payload["parameters"].items()}
    _require(set(parameters) == set(base.PARAMETERS), "parameter fields")
    _require(parameters["strong_convexity"] == Fraction(1, 10), "mu")
    _require(parameters["smoothness"] == 1, "L")
    _require(parameters["step_size"] == 1, "step size")
    _require(parameters["proposal_step"] == 1, "proposal step")
    residual = parameters["initial_distance_upper"] + parameters["proposal_norm_upper"]
    value = residual
    horizon = 0
    while value > parameters["tolerance"]:
        value *= Fraction(9, 10)
        horizon += 1
    _require(horizon == 10, "formula-derived horizon")
    trace_consequence = (
        11 * parameters["initial_distance_upper"] ** 2
        + 11
        * (
            parameters["initial_distance_upper"]
            + parameters["proposal_norm_upper"]
        )
        ** 2
        + parameters["initial_distance_upper"] ** 2
        + parameters["proposal_norm_upper"] ** 2
    )
    _require(trace_consequence < parameters["derived_trace_bound"], "trace bound")
    # A one-dimensional quadratic proves that every profile class is nonempty.
    midpoint = (
        parameters["proposal_norm_lower"] + parameters["proposal_norm_upper"]
    ) / 2
    _require(midpoint <= parameters["initial_distance_upper"], "quadratic witness R")
    _require(midpoint > parameters["tolerance"], "quadratic witness stopping time")
    _require(Fraction(0) <= parameters["contract_radius"], "quadratic witness contract")
    return parameters


def _verify_profile(
    name: str,
    payload: dict[str, Any],
    *,
    progress: bool,
) -> dict[str, Any]:
    unsigned = dict(payload)
    recorded = unsigned.pop("payload_sha256", None)
    _require(recorded == sha256(_canonical(unsigned)).hexdigest(), f"{name} payload hash")
    if name == "balanced":
        _require(payload["schema"] == base.SCHEMA, "balanced schema")
    else:
        _require(payload["schema"] == PROFILE_SCHEMA, f"{name} schema")
        _require(payload["declaration"]["profile"] == name, f"{name} declaration")
    parameters = _parse_parameters(payload)
    certificates = payload["certificates"]
    _require(
        [item["cell"] for item in certificates] == [list(cell) for cell in base.BAD_CELLS],
        f"{name} certificate order",
    )
    original = base.PARAMETERS
    base.PARAMETERS = parameters
    try:
        verified = []
        for completed, certificate in enumerate(certificates, start=1):
            verified.append(base._verify_certificate(certificate))
            if progress and (completed % 22 == 0 or completed == len(certificates)):
                print(f"profile={name} verified={completed}/66", flush=True)
    finally:
        base.PARAMETERS = original
    bounds = [bound for bound, _ in verified]
    pivots = sum(count for _, count in verified)
    summary = payload["summary"]
    _require(summary["certificate_count"] == 66, f"{name} certificate count")
    _require(summary["maximum_gram_order"] == 24, f"{name} Gram order")
    _require(summary["maximum_inequality_count"] == 534, f"{name} inequalities")
    _require(
        summary["positive_leading_principal_minor_count"] == pivots == 1584,
        f"{name} pivot count",
    )
    _require(
        Fraction(summary["maximum_certified_upper_bound"]) == max(bounds),
        f"{name} maximum upper",
    )
    _require(
        summary["recovery_grid"] == base._expected_recovery_grid(certificates),
        f"{name} recovery grid",
    )
    _require(
        summary["certified_cell_progress"]
        == "66/66 independently replayable exclusions constructed",
        f"{name} progress",
    )
    return {
        "name": name,
        "payload_sha256": recorded,
        "parameters": parameters,
        "maximum_upper": max(bounds),
        "positive_ldl_pivots": pivots,
        "recovery_attempts": sum(
            len(item["recovery"]["ordered_grid_attempts"])
            for item in certificates
        ),
        "recovery_failures": sum(
            attempt["outcome"] == "failure"
            for item in certificates
            for attempt in item["recovery"]["ordered_grid_attempts"]
        ),
    }


def verify_payload(
    manifest: dict[str, Any],
    *,
    root: Path,
    progress: bool = False,
) -> dict[str, Any]:
    unsigned = dict(manifest)
    recorded = unsigned.pop("payload_sha256", None)
    _require(recorded == sha256(_canonical(unsigned)).hexdigest(), "manifest hash")
    _require(manifest.get("schema") == SCHEMA, "manifest schema")
    declaration = manifest["declaration"]
    _require(declaration["profile_count"] == 5, "profile count")
    _require(declaration["independently_recovered_profile_count"] == 3, "source count")
    _require(declaration["transported_profile_count"] == 2, "transport count")
    source_rows = manifest["sources"]
    _require(
        {row["name"]: row["path"] for row in source_rows} == EXPECTED_SOURCES,
        "source paths",
    )
    verified_sources: dict[str, dict[str, Any]] = {}
    source_payloads: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        path = root / row["path"]
        _require(_file_hash(path) == row["file_sha256"], f"{row['name']} file hash")
        payload = json.loads(path.read_text(encoding="utf-8"))
        _require(payload["payload_sha256"] == row["payload_sha256"], f"{row['name']} binding")
        source_payloads[row["name"]] = payload
        verified_sources[row["name"]] = _verify_profile(
            row["name"], payload, progress=progress
        )
    transports = manifest["transports"]
    _require(
        [(row["name"], row["source"], row["scale"]) for row in transports]
        == [
            ("balanced_scale_4_5", "balanced", "4/5"),
            ("balanced_scale_6_5", "balanced", "6/5"),
        ],
        "transport declarations",
    )
    transported = []
    for row in transports:
        source = verified_sources[row["source"]]
        scale = Fraction(row["scale"])
        parameters = source["parameters"]
        target = deepcopy(parameters)
        for key in (
            "proposal_norm_lower",
            "proposal_norm_upper",
            "contract_radius",
            "initial_distance_upper",
            "tolerance",
        ):
            target[key] *= scale
        target["derived_trace_bound"] *= scale**2
        _require(_parse_parameters({"parameters": {key: str(value) for key, value in target.items()}}) == target, f"{row['name']} target")
        transported_upper = source["maximum_upper"] * scale**2
        _require(transported_upper < 0, f"{row['name']} transported upper")
        transported.append(
            {
                "name": row["name"],
                "maximum_upper": transported_upper,
                "cell_count": 66,
                "positive_ldl_pivots": source["positive_ldl_pivots"],
            }
        )
    environment = manifest["environment"]
    _require(
        environment["builder_sha256"]
        == _file_hash(root / "experiments" / "build_h10_envelope_family.py"),
        "builder hash",
    )
    _require(environment["verifier_sha256"] == _file_hash(Path(__file__)), "verifier hash")
    return {
        "payload_sha256": recorded,
        "profile_count": 5,
        "exact_cell_exclusion_count": 330,
        "independent_cell_exclusion_count": 198,
        "transported_cell_exclusion_count": 132,
        "independent_positive_ldl_pivots": sum(
            row["positive_ldl_pivots"] for row in verified_sources.values()
        ),
        "total_recovery_attempts": sum(
            row["recovery_attempts"] for row in verified_sources.values()
        ),
        "total_recovery_failures": sum(
            row["recovery_failures"] for row in verified_sources.values()
        ),
        "transported": transported,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = verify_payload(
        json.loads(args.payload.read_text(encoding="utf-8")),
        root=args.root,
        progress=True,
    )
    print(
        "VERIFIED: five natural-H=10 envelopes, "
        f"{result['independent_cell_exclusion_count']} independently recovered + "
        f"{result['transported_cell_exclusion_count']} transported exact exclusions, "
        f"{result['independent_positive_ldl_pivots']} independent positive LDL pivots"
    )


if __name__ == "__main__":
    main()
