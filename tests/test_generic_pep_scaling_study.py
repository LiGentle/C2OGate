"""Integrity checks for the generic ragged H=20 PEP audit."""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from collections import Counter


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results" / "generic_pep_scaling_study.json"
EXPECTED_HASH = "c95b62e10f20ad9786559c8693ad2495eed285da06caee6f7890e3d8376b95fd"


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_generic_payload_and_runner_are_hash_bound() -> None:
    payload = _load()
    recorded = payload.pop("payload_sha256")
    assert recorded == EXPECTED_HASH
    assert sha256(_canonical(payload)).hexdigest() == recorded
    assert payload["environment"]["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_generic_pep_scaling_study.py"
    )


def test_every_cost_violating_cell_is_present_once() -> None:
    payload = _load()
    declaration = payload["declaration"]
    assert payload["schema"] == "c2o-generic-ragged-pep-scaling-v1"
    assert declaration["horizon"] == 20
    assert declaration["nominal_joint_cell_count"] == 441
    assert declaration["bad_cell_count"] == 231
    assert declaration["formulation"].endswith("no exact-shift identity")
    expected = {(r, s) for r in range(21) for s in range(21) if s >= r}
    actual = {
        (cell["baseline_calls"], cell["hybrid_calls"]) for cell in payload["cells"]
    }
    assert actual == expected
    assert len(payload["cells"]) == len(actual) == 231


def test_rejection_witnesses_and_ragged_dimensions_are_consistent() -> None:
    payload = _load()
    summary = payload["summary"]
    cells = payload["cells"]
    assert Counter(cell["status"] for cell in cells) == {
        "optimal": 24,
        "optimal_inaccurate": 186,
        "infeasible": 19,
        "infeasible_inaccurate": 2,
    }
    positive = [cell for cell in cells if cell["attainable"]]
    assert [(cell["baseline_calls"], cell["hybrid_calls"]) for cell in positive] == [
        (1, 1),
        (2, 2),
        (3, 3),
    ]
    assert summary["positive_margin_bad_cell_count"] == len(positive) == 3
    assert summary["numerically_ambiguous_bad_cell_count"] == 0
    assert summary["joint_gate_rejects_from_positive_witness"]
    assert summary["maximum_attainable_call_difference"] == 0
    assert summary["maximum_gram_order"] == 44
    assert summary["median_gram_order"] == 24.0
    assert summary["maximum_constraint_count"] == 1854
    for cell in cells:
        assert cell["gram_order"] == (cell["baseline_calls"] + cell["hybrid_calls"] + 4)
        assert isfinite(cell["setup_seconds"]) and cell["setup_seconds"] > 0.0
        assert isfinite(cell["solve_seconds"]) and cell["solve_seconds"] > 0.0
    assert isfinite(summary["wall_seconds"]) and summary["wall_seconds"] > 0.0
