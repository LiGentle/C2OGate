"""Representative exact checks for the full natural-H=10 dual suite."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_h10_generic_pep_dual import _verify_certificate  # noqa: E402


PAYLOAD = ROOT / "certificates" / "h10_generic_pep_dual.json"
EXPECTED_HASH = "657a8b91d025ab66d610251981e3d1e0604baea6385f1682c640f864c616700f"


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _load() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_h10_payload_and_representative_cells_verify_exactly() -> None:
    payload = _load()
    assert payload["payload_sha256"] == EXPECTED_HASH
    assert payload["summary"]["certificate_count"] == 66
    assert payload["summary"]["positive_leading_principal_minor_count"] == 1584
    assert payload["summary"]["certified_cell_progress"] == (
        "66/66 independently replayable exclusions constructed"
    )
    assert payload["summary"]["incomplete_recovery_outcome"] == "uncertified"
    assert sum(
        row["successful_cells"] for row in payload["summary"]["recovery_grid"]
    ) == 66
    assert payload["parameters"]["derived_trace_bound"] == "49"
    environment = payload["environment"]
    assert environment["generator_sha256"] == _file_hash(
        ROOT / "experiments" / "generate_h10_generic_pep_dual_certificate.py"
    )
    assert environment["verifier_sha256"] == _file_hash(
        ROOT / "tools" / "verify_h10_generic_pep_dual.py"
    )
    certificates = payload["certificates"]
    for certificate in (certificates[0], certificates[32], certificates[-1]):
        upper, pivots = _verify_certificate(certificate)
        assert upper < 0
        assert pivots == 24


def test_h10_rehashed_multiplier_tampering_is_rejected() -> None:
    certificate = deepcopy(_load()["certificates"][0])
    multipliers = certificate["dual"]["inequality_multipliers"]
    key = next(key for key, value in multipliers.items() if value != "0")
    multipliers[key] = "0"
    with pytest.raises(ValueError):
        _verify_certificate(certificate)


def test_h10_recovery_grid_metadata_tampering_is_rejected() -> None:
    certificate = deepcopy(_load()["certificates"][0])
    certificate["recovery"]["selected_configuration"]["active_threshold"] = "0"
    with pytest.raises(ValueError, match="selected recovery configuration"):
        _verify_certificate(certificate)


def test_h10_class_has_exact_quadratic_witness() -> None:
    # f(t)=t^2/2+(4/5)t, x=0, y=-4/5.  This exact witness is the
    # nonvacuity argument used in the manuscript; the verifier's additional
    # 80-digit nonquadratic realization is only a numerical cross-check.
    gradient = Fraction(4, 5)
    candidate = -Fraction(4, 5)
    assert abs(candidate) >= Fraction(79, 100)
    assert abs(candidate) <= Fraction(81, 100)
    assert candidate + gradient == 0
    assert abs(gradient) <= 1
    assert abs(gradient) > Fraction(2, 3)
