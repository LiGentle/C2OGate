import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_documented_reuse_example_accepts():
    namespace = runpy.run_path(ROOT / "examples" / "reuse_custom_stopping_rule.py")
    decision = namespace["run_example"]()
    assert decision.outcome.value == "accept"
