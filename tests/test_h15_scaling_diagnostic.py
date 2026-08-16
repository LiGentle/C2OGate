from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "h15_scaling_diagnostic.json"
RUNNER = ROOT / "experiments" / "run_h15_scaling_diagnostic.py"
EXPECTED_HASH = "185679ccb57f336db729d31a80ba4e6aa410530cb2fe999c128c324894d5167e"


def test_h15_diagnostic_is_frozen_and_explicitly_uncertified() -> None:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    recorded = payload.pop("payload_sha256")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    assert recorded == EXPECTED_HASH == sha256(canonical).hexdigest()
    assert payload["environment"]["runner_sha256"] == sha256(
        RUNNER.read_bytes()
    ).hexdigest()
    assert payload["declaration"]["proof_status"] == "uncertified"
    run = payload["run"]
    assert run["horizon"] == 15
    assert run["bad_cell_count"] == 136
    assert run["maximum_gram_order"] == 34
    assert run["peak_rss_mib"] > 1000
