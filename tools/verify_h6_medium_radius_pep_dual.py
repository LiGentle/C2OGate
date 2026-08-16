#!/usr/bin/env python3
"""Verify the natural-H=6 suite at the enlarged radius delta=7/500."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.verify_h6_joint_only_pep_dual as h6  # noqa: E402


SCHEMA = "c2o-h6-medium-radius-pep-dual-v1"
RADIUS = Fraction(7, 500)


def verify_payload(
    payload: dict[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    original_schema = h6.SCHEMA
    original_radius = h6.PARAMETERS["contract_radius"]
    h6.SCHEMA = SCHEMA
    h6.PARAMETERS["contract_radius"] = RADIUS
    try:
        result = h6.verify_payload(payload, root=root)
    finally:
        h6.SCHEMA = original_schema
        h6.PARAMETERS["contract_radius"] = original_radius
        h6._configure_base()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    result = verify_payload(
        json.loads(args.payload.read_text(encoding="utf-8")), root=args.root
    )
    print(
        "VERIFIED: natural-H=6 medium-radius joint-only PEP acceptance, "
        f"delta={RADIUS}, {result['certificate_count']} bad cells, "
        f"{result['positive_ldl_pivots']} positive LDL pivots, "
        f"maximum bound={result['maximum_certified_upper_bound']}"
    )


if __name__ == "__main__":
    main()
