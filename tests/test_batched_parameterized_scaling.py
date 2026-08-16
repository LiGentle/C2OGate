import json
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "batched_parameterized_scaling.json"


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_batched_parameterized_scaling_payload():
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    claimed = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == claimed
    batched = payload["batched"]
    assert batched["horizon"] == 15
    assert batched["cell_count"] == 136
    assert batched["metadata"]["is_dpp"]
    assert batched["maximum_sample_margin_difference"] < 1.0e-5
    assert payload["ratios"]["batched_over_ragged_peak_rss"] < 1.0
    assert set(batched["status_counts"]) <= {"optimal", "optimal_inaccurate"}
    runner = ROOT / "experiments" / "run_batched_parameterized_scaling.py"
    assert payload["environment"]["runner_sha256"] == sha256(
        runner.read_bytes()
    ).hexdigest()
