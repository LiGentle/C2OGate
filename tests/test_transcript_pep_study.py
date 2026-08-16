"""Integrity checks for the transcript-conditioned PEP study."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results" / "transcript_pep_study.json"


def _load() -> dict:
    return json.loads(RESULT.read_text(encoding="utf-8"))


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


def test_transcript_payload_hash_is_self_consistent() -> None:
    payload = _load()
    recorded = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == recorded
    assert recorded == (
        "5b7fe99bfa34c07d0252582244f22d27df3f32f8d2cd93ced08b8df369dd5597"
    )


def test_transcript_source_and_runner_hashes_match() -> None:
    environment = _load()["environment"]
    assert environment["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_transcript_pep_study.py"
    )
    for relative, expected in environment["source_sha256"].items():
        assert _file_hash(ROOT / relative) == expected


def test_joint_gate_retains_dependence_without_certified_violations() -> None:
    payload = _load()
    assert payload["schema"] == "c2o-transcript-pep-study-v2"
    assert len(payload["records"]) == 2000
    summary = payload["summary"]
    assert summary["pep_cell_count"] == 36
    assert summary["pep_attainable_pair_count"] == 3
    assert summary["pep_off_shift_attainable_count"] == 0
    assert summary["pep_numerically_ambiguous_cell_count"] == 4
    assert summary["joint_accept_count"] == 896
    assert summary["rectangle_accept_count"] == 160
    assert summary["joint_only_accept_count"] == 736
    assert summary["two_bin_accept_count"] == 338
    assert summary["four_bin_accept_count"] == 487
    assert summary["two_bin_without_joint_count"] == 0
    assert summary["four_bin_without_joint_count"] == 0
    assert summary["rectangle_accept_without_joint_count"] == 0
    assert summary["accepted_joint_violation_count"] == 0
    assert summary["joint_policy_cost_ratio"]["mean"] == 0.9948683016716258
    assert summary["rectangle_policy_cost_ratio"]["mean"] == 0.9988441068175596
    assert summary["two_bin_policy_cost_ratio"]["mean"] == 0.9975966149052984
    assert summary["four_bin_policy_cost_ratio"]["mean"] == 0.9968052811637943
    assert summary["always_policy_cost_ratio"]["mean"] == 0.9927754269785753
    assert summary["joint_policy_worse_fraction"] == 0.0
    assert summary["rectangle_policy_worse_fraction"] == 0.0
    assert summary["always_policy_worse_fraction"] == 0.2415


def test_realized_member_policy_accounting_is_exact() -> None:
    payload = _load()
    for row in payload["records"]:
        baseline = row["realized_baseline_calls"]
        hybrid = row["realized_hybrid_calls"]
        cost = row["cost_exact_units"]
        expected_joint = cost + hybrid if row["joint_accept"] else baseline
        expected_rectangle = cost + hybrid if row["rectangle_accept"] else baseline
        expected_two_bin = cost + hybrid if row["two_bin_accept"] else baseline
        expected_four_bin = cost + hybrid if row["four_bin_accept"] else baseline
        assert row["joint_total_cost"] == expected_joint
        assert row["rectangle_total_cost"] == expected_rectangle
        assert row["two_bin_total_cost"] == expected_two_bin
        assert row["four_bin_total_cost"] == expected_four_bin
        assert row["always_total_cost"] == cost + hybrid
        assert row["joint_cost_ratio"] <= 1.0 + 1.0e-12
        assert row["rectangle_cost_ratio"] <= 1.0 + 1.0e-12
        assert row["two_bin_cost_ratio"] <= 1.0 + 1.0e-12
        assert row["four_bin_cost_ratio"] <= 1.0 + 1.0e-12
