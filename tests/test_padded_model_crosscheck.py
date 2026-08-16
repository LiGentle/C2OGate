from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "padded_model_crosscheck.json"
RUNNER = ROOT / "experiments" / "run_padded_model_crosscheck.py"
EXPECTED_HASH = "6bab28677ceea170fc4954a938be0c5722b8bff0ccd30f3e9390a1de3bf36d8c"


def test_padded_crosscheck_is_complete_and_hash_bound() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert recorded == EXPECTED_HASH == sha256(canonical).hexdigest()
    assert payload["environment"]["runner_sha256"] == sha256(
        RUNNER.read_bytes()
    ).hexdigest()
    assert payload["environment"]["pepit"] == "0.5.1"
    assert payload["summary"]["suite_count"] == 3
    assert payload["summary"]["cell_count"] == 9
    assert payload["summary"]["maximum_absolute_difference"] < 3.0e-7
    assert {row["horizon"] for row in payload["rows"]} == {3, 6, 10}
