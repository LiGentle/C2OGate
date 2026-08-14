"""Integrity and adversarial tests for the positive real-SPX certificate."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools.verify_real_spx_ill_conditioned_certificate import verify_payload


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
RESULT = ROOT / "results" / "real_spx_ill_conditioned_study.json"
EXPECTED_HASH = "5af3c0b51de9f862285bfdab86e524fa6988330e4cfafb0f528066d503437395"


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


def _rehash(payload: dict) -> None:
    payload.pop("payload_sha256", None)
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()


def test_positive_real_payload_sources_and_exact_verifier_are_bound() -> None:
    payload = _load()
    recorded = payload.pop("payload_sha256")
    assert recorded == EXPECTED_HASH
    assert sha256(_canonical(payload)).hexdigest() == recorded
    environment = payload["environment"]
    assert environment["runner_sha256"] == _file_hash(
        ROOT / "experiments" / "run_real_spx_ill_conditioned_study.py"
    )
    assert environment["verifier_sha256"] == _file_hash(
        ROOT / "tools" / "verify_real_spx_ill_conditioned_certificate.py"
    )
    for relative, expected in environment["input_sha256"].items():
        source = PROJECT_ROOT / relative
        if source.is_file():
            assert _file_hash(source) == expected
    payload["payload_sha256"] = recorded
    summary = verify_payload(payload)
    assert summary["baseline_calls"] == 7_840
    assert summary["hybrid_calls"] == 3_803
    assert Fraction(summary["condition_lower"]) > 1_325
    assert not summary["source_rebuilt"]
    chain = PROJECT_ROOT / "data" / "market_data" / "spx_options_2026-08-08.csv"
    if chain.is_file():
        source_summary = verify_payload(payload, source_root=PROJECT_ROOT)
        assert source_summary["source_rebuilt"]


def test_positive_real_instance_has_reachable_total_cost_dominance() -> None:
    payload = _load()
    assert payload["schema"] == "c2o-real-spx-ill-conditioned-v2"
    assert payload["data"]["filtered_quote_count"] == 6_162
    assert payload["data"]["expiry_count"] == 38
    certificate = payload["certificate"]
    assert certificate["baseline_calls"] - certificate["hybrid_calls"] == 4_037
    assert Fraction(certificate["condition_lower"]) > 1_325
    assert Fraction(certificate["condition_upper"]) == 1_680
    cost = payload["cost_accounting"]
    assert cost["gate_accepts"]
    assert cost["candidate_to_baseline_ratio"] < 0.5
    assert cost["total_cost_slack_units"] > 3_900
    timing = payload["timing"]
    assert timing["repeat_count"] == 3
    assert timing["measured_break_even_reuses"] == 2
    assert timing["measured_ratio_at_break_even"] < 0.9
    assert timing["measured_warm_speedup"] > 2.0


@pytest.mark.parametrize("target", ["candidate", "minor", "calls", "cost"])
def test_rehashed_certificate_tampering_is_rejected(target: str) -> None:
    payload = deepcopy(_load())
    if target == "candidate":
        payload["certificate"]["candidate"][0] = str(
            Fraction(payload["certificate"]["candidate"][0]) + Fraction(1, 10**6)
        )
    elif target == "minor":
        payload["certificate"]["lower_leading_minors"][0] = "1"
    elif target == "calls":
        payload["certificate"]["hybrid_calls"] -= 1
    else:
        payload["cost_accounting"]["candidate_to_baseline_ratio"] = 0.1
    _rehash(payload)
    with pytest.raises(ValueError):
        verify_payload(payload)
