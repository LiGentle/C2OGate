from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "pepit_verified_baseline.json"


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_pepit_frontend_produces_complete_exactly_verifiable_h6_suite():
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    claimed = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == claimed
    assert payload["summary"]["attempted_cell_count"] == 28
    assert (
        payload["summary"]["certificate_count"]
        + payload["summary"]["uncertified_cell_count"]
        == 28
    )
    assert {row["outcome"] for row in payload["rows"]} <= {
        "verified",
        "uncertified",
    }
    assert payload["environment"]["pepit"] == "0.5.1"
