"""Integrity checks for the repeated Clarabel/SCS benchmark."""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "generic_pep_solver_benchmark.json"
EXPECTED_HASH = "5b7f1189bbe0053fbeefa649932fd3c2cb402c57aa4a97cb035c6d8b3de2e9b8"


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_solver_benchmark_is_complete_and_hash_bound() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert recorded == EXPECTED_HASH == sha256(canonical).hexdigest()
    assert payload["environment"]["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_generic_pep_solver_benchmark.py"
    )
    assert payload["environment"]["cell_runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_generic_pep_scaling_study.py"
    )
    assert payload["declaration"]["repeat_count"] == 5
    assert len(payload["runs"]) == 2 * 5 * 5
    for run in payload["runs"]:
        expected = (run["horizon"] + 1) * (run["horizon"] + 2) // 2
        assert run["bad_cell_count"] == expected
        assert sum(run["status_counts"].values()) == expected
        assert isfinite(run["wall_seconds"]) and run["wall_seconds"] > 0
        assert isfinite(run["peak_rss_mib"]) and run["peak_rss_mib"] > 0
