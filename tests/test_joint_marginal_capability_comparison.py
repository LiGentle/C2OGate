from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "results" / "joint_marginal_capability_comparison.json"


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def test_joint_marginal_comparison_is_hash_bound_and_has_control():
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    claimed = payload.pop("payload_sha256")
    assert sha256(_canonical(payload)).hexdigest() == claimed
    assert payload["summary"] == {
        "both_accept_count": 1,
        "joint_only_accept_count": 4,
        "transcript_count": 5,
    }
    assert all(row["joint_accept"] for row in payload["rows"])
    for suffix in ("pdf", "png"):
        path = ROOT / "figures" / f"joint_vs_marginal_rectangle.{suffix}"
        assert sha256(path.read_bytes()).hexdigest() == payload["figure_sha256"][suffix]
