from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_measured_heat_inverse_ledger_is_complete_and_self_financing() -> None:
    payload = json.loads(
        (ROOT / "results" / "measured_heat_inverse_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema"] == "c2o-measured-heat-inverse-benchmark-v2"
    assert payload["summary"]["attempted"] == 64
    assert payload["summary"]["accepted"] == 32
    assert payload["summary"]["rejected"] == 0
    assert payload["summary"]["uncertified_by_contract"] == 32
    assert (
        payload["summary"][
            "amortization_episode_threshold_against_unpenalized_baseline"
        ]
        == 671
    )
    assert payload["summary"]["prefilter_nonimproving_branches"] == 32
    ledger = payload["ledger_exact_call_units"]
    assert ledger["cold_gate_beats_risk_adjusted_prefilter"]
    assert not ledger["cold_gate_beats_unpenalized_baseline"]
    runner = ROOT / "experiments" / "run_measured_heat_inverse_benchmark.py"
    assert payload["environment"]["runner_sha256"] == sha256(
        runner.read_bytes()
    ).hexdigest()
