from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_consumer_differential_fuzz_covers_randomized_parameters() -> None:
    payload = json.loads(
        (ROOT / "results" / "consumer_differential_fuzz.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema"] == "c2o-consumer-differential-fuzz-v1"
    assert payload["case_count"] == 32
    assert payload["exact_scalar_comparisons"] > 1_000_000
    assert len({tuple(row["cell"]) for row in payload["rows"]}) >= 12
