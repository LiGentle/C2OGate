from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path

from tools.verify_h6_medium_radius_pep_dual import verify_payload


ROOT = Path(__file__).resolve().parents[1]


def test_h6_medium_radius_suite_is_complete_and_strict() -> None:
    payload = json.loads(
        (ROOT / "certificates" / "h6_medium_radius_pep_dual.json").read_text(
            encoding="utf-8"
        )
    )
    result = verify_payload(payload)
    assert result["certificate_count"] == 28
    assert result["positive_ldl_pivots"] == 448
    assert Fraction(result["maximum_certified_upper_bound"]) < 0
