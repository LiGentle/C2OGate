"""Integrity checks for the frozen PEP scaling audit."""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results" / "pep_scaling_study.json"
EXPECTED_HASH = "b1657bf11437d56fd8a65f736de2b05708e97675ca644a8df4483eb58cfaad87"


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


def test_scaling_payload_and_sources_are_hash_bound() -> None:
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    assert recorded == EXPECTED_HASH
    assert sha256(_canonical(payload)).hexdigest() == recorded
    environment = payload["environment"]
    assert environment["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_pep_scaling_study.py"
    )
    assert environment["dense_runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_transcript_pep_study.py"
    )


def test_medium_horizon_enumeration_is_complete_and_honest() -> None:
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    assert payload["schema"] == "c2o-pep-scaling-study-v1"
    dense = payload["dense_reference"]
    assert dense["horizon"] == 5
    assert dense["solved_sdp_cell_count"] == 36
    assert dense["maximum_gram_order"] == 14
    rows = payload["reduced_horizons"]
    assert [row["horizon"] for row in rows] == [10, 15, 20]
    assert [row["nominal_joint_cell_count"] for row in rows] == [121, 256, 441]
    assert [row["solved_sdp_cell_count"] for row in rows] == [10, 15, 20]
    assert [row["structurally_excluded_cell_count"] for row in rows] == [
        111,
        241,
        421,
    ]
    assert [row["maximum_gram_order"] for row in rows] == [12, 17, 22]
    for row in rows:
        assert len(row["cells"]) == row["solved_sdp_cell_count"]
        assert row["numerically_ambiguous_cell_count"] == 0
        assert isfinite(row["elapsed_seconds"]) and row["elapsed_seconds"] > 0.0
