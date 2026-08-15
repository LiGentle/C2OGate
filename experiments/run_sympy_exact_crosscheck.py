#!/usr/bin/env python3
"""Cross-check all flagship dual slacks with SymPy exact LDL decomposition."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import sympy as sp


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_h10_generic_pep_dual as verifier  # noqa: E402


INPUT = ROOT / "certificates" / "h10_generic_pep_dual.json"
OUTPUT = ROOT / "results" / "sympy_exact_crosscheck.json"
SCHEMA = "c2o-sympy-exact-crosscheck-v2"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _slack(certificate: dict[str, Any]) -> list[list[Fraction]]:
    inequalities, equalities = verifier._build_constraints(tuple(certificate["cell"]))
    dual = certificate["dual"]
    lambdas = [
        Fraction(dual["inequality_multipliers"].get(item.name, "0"))
        for item in inequalities
    ]
    nus = [
        Fraction(dual["equality_multipliers"].get(item.name, "0"))
        for item in equalities
    ]
    slack = verifier._zero_matrix(24)
    for multiplier, item in zip(lambdas, inequalities, strict=True):
        if multiplier:
            for i, row in enumerate(item.matrix):
                for j, value in enumerate(row):
                    if value:
                        slack[i][j] += multiplier * value
    for multiplier, item in zip(nus, equalities, strict=True):
        if multiplier:
            for i, row in enumerate(item.matrix):
                for j, value in enumerate(row):
                    if value:
                        slack[i][j] += multiplier * value
    return slack


def main() -> None:
    source = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = []
    started = perf_counter()
    for completed, certificate in enumerate(source["certificates"], start=1):
        cell_started = perf_counter()
        rational_slack = _slack(certificate)
        matrix = sp.Matrix(
            [
                [sp.Rational(value.numerator, value.denominator) for value in row]
                for row in rational_slack
            ]
        )
        _, diagonal = matrix.LDLdecomposition(hermitian=False)
        pivots = [diagonal[index, index] for index in range(24)]
        if not all(value > 0 for value in pivots):
            raise RuntimeError(f"SymPy nonpositive LDL pivot for {certificate['cell']}")
        rows.append(
            {
                "cell": certificate["cell"],
                "positive_ldl_pivot_count": len(pivots),
                "seconds": perf_counter() - cell_started,
            }
        )
        if completed % 11 == 0 or completed == len(source["certificates"]):
            print(f"sympy_exact={completed}/{len(source['certificates'])}", flush=True)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "scope": "all 66 flagship H=10 rational dual slack matrices",
            "method": (
                "SymPy Matrix LDL decomposition over QQ; require all 24 exact "
                "diagonal pivots to be positive"
            ),
            "comparison": (
                "independent computer-algebra backend cross-check of the custom "
                "Python-fractions LDL consumer"
            ),
            "external_toolchain_boundary": {
                "VSDP": "requires a MATLAB/Octave interval stack absent from the clean Python artifact",
                "SPECTRA": "requires Maple and is no longer maintained; unsuitable for the declared clean-checkout workflow",
            },
        },
        "summary": {
            "certificate_count": len(rows),
            "positive_ldl_pivot_count": sum(
                row["positive_ldl_pivot_count"] for row in rows
            ),
            "wall_seconds": perf_counter() - started,
        },
        "rows": rows,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "sympy": sp.__version__,
            "runner_sha256": _file_hash(Path(__file__)),
            "input_file_sha256": _file_hash(INPUT),
            "input_payload_sha256": source["payload_sha256"],
            "coefficient_builder_sha256": _file_hash(
                ROOT / "tools" / "verify_h10_generic_pep_dual.py"
            ),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "VERIFIED: SymPy exact LDL cross-check, "
        f"{payload['summary']['certificate_count']} slacks, "
        f"{payload['summary']['positive_ldl_pivot_count']} positive pivots"
    )


if __name__ == "__main__":
    main()
