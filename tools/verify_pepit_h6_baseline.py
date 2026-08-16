#!/usr/bin/env python3
"""Replay every certificate recovered from the PEPit H=6 comparator."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import tools.verify_h6_joint_only_pep_dual as h6


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def verify(payload):
    unsigned = dict(payload)
    claimed = unsigned.pop("payload_sha256")
    if sha256(_canonical(unsigned)).hexdigest() != claimed:
        raise ValueError("payload hash")
    if payload.get("schema") != "c2o-pepit-verified-baseline-v1":
        raise ValueError("schema")
    h6._configure_base()
    verified = [h6._verify_certificate(item) for item in payload["certificates"]]
    summary = payload["summary"]
    if summary["attempted_cell_count"] != 28:
        raise ValueError("attempted count")
    if summary["certificate_count"] != len(verified):
        raise ValueError("verified count")
    if summary["uncertified_cell_count"] + len(verified) != 28:
        raise ValueError("three-valued accounting")
    return len(verified), sum(item[1] for item in verified)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    count, pivots = verify(payload)
    print(
        "VERIFIED: PEPit comparator, "
        f"{count}/28 exact exclusions, {pivots} exact positive pivots"
    )


if __name__ == "__main__":
    main()
