from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "signed_boundary_audit.json"


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_signed_boundary_frequency_is_complete_and_hash_bound():
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    claimed = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == claimed
    assert payload["summary"]["cell_count"] == 142
    assert payload["summary"]["exact_zero_count"] == 0
    assert payload["summary"]["accepted_workload_transcript_count"] == 46
    assert payload["summary"]["accepted_workload_zero_boundary_count"] == 0
