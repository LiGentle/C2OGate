from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "uci_wdbc_gate_benchmark.json"
RUNNER = ROOT / "experiments" / "run_uci_wdbc_gate_benchmark.py"
DATA = ROOT / "data" / "uci_wdbc" / "wdbc.data"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_wdbc_payload_and_sources_are_hash_bound() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    assert recorded == sha256(_canonical(payload)).hexdigest()
    assert payload["evidence"]["runner_sha256"] == sha256(
        RUNNER.read_bytes()
    ).hexdigest()
    assert payload["evidence"]["data_sha256"] == sha256(
        DATA.read_bytes()
    ).hexdigest()


def test_wdbc_joint_gate_changes_a_real_data_decision_exactly() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["proposal_attempt_count"] == 45
    assert summary["joint_accept_count"] == 28
    assert summary["joint_reject_count"] == 0
    assert summary["joint_uncertified_count"] == 17
    assert summary["joint_three_valued_attempt_count"] == 45
    assert summary["marginal_accept_count"] == 0
    assert summary["accepted_violation_count"] == 0
    assert summary["exact_membership_decision_count"] == 512
    assert summary["warm_cost_ratio"] < 0.95
    assert summary["measured_time_warm_cost_ratio"] > 1.0
    assert payload["declaration"]["economic_scope"].startswith(
        "row-scan units and hypothetical"
    )
    assert summary["always_query_pointwise_overrun_count"] > 0
    assert summary["greedy_prefilter_accept_count"] == 45
    assert summary["greedy_prefilter_cost_ratio"] < summary["warm_cost_ratio"]
    assert summary["greedy_prefilter_candidate_nonimprovement_count"] == 0
    assert summary["greedy_prefilter_pointwise_overrun_count"] == 0
    assert payload["declaration"]["dataset_doi"] == "10.24432/C5DW2B"
    assert all(
        row["decision_outcome"] in {"accept", "uncertified", "not_attempted"}
        for row in payload["records"]
    )


def test_wdbc_expensive_oracle_scenario_is_separate_from_measured_runtime() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    scenarios = {
        row["exact_oracle_seconds"]: row
        for row in payload["economic_scenarios"]
    }
    assert scenarios[60.0]["observed_batch_self_financing"]
    assert scenarios[60.0]["break_even_episodes"] <= 30
    assert payload["summary"]["measured_single_full_gradient_seconds"]["median"] < 0.01
