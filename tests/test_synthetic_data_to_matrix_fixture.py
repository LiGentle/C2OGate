"""Raw-row regression test for the independently implemented market map."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from tools.verify_real_spx_ill_conditioned_certificate import (
    _file_hash,
    _rebuild_market_matrices,
)


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "synthetic_data_to_matrix_fixture.json"


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_raw_rows_rebuild_frozen_rational_matrices() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == recorded
    source = ROOT / "data" / "synthetic_option_panel.csv"
    assert payload["environment"]["input_sha256"]["data/synthetic_option_panel.csv"] == _file_hash(source)
    assert payload["environment"]["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "generate_synthetic_data_to_matrix_fixture.py"
    )
    assert payload["declaration"]["raw_row_count"] == 20
    assert payload["declaration"]["filtered_row_count"] == 17
    matrix, linear, sketch = _rebuild_market_matrices(payload, ROOT)
    objective = payload["objective"]
    assert matrix == [
        [Fraction(value) for value in row]
        for row in objective["exact_hessian"]
    ]
    assert linear == [Fraction(value) for value in objective["exact_linear"]]
    assert sketch == [
        [Fraction(value) for value in row]
        for row in objective["sketch_hessian"]
    ]
