#!/usr/bin/env python3
"""Measured C2OGate ledger on a full-grid heat inverse problem.

The expensive oracle applies a 2-D periodic heat propagator forward and
adjoint on a 640x640 grid.  A fixed 80x80 surrogate is accurate on a low
frequency mode and over-diffusive on a higher-frequency mode.  The latter
passes the free gradient prefilter but violates the certified proposal
contract, which creates a measured risk-adjusted setting where proof reuse is
self-financing.
"""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from math import ceil, cos, pi, sqrt
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import numpy as np

from c2ogate.exact_membership import (
    binary64_vector,
    certify_h6_envelope_membership,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "measured_heat_inverse_benchmark.json"
CERTIFICATE = ROOT / "certificates" / "h6_joint_only_pep_dual.json"
COST_PAYLOAD = ROOT / "results" / "h6_certificate_cost_study.json"
SCHEMA = "c2o-measured-heat-inverse-benchmark-v2"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _heat(field: np.ndarray, *, steps: int, ratio: float) -> np.ndarray:
    state = field.copy()
    for _ in range(steps):
        state += ratio * (
            np.roll(state, 1, axis=0)
            + np.roll(state, -1, axis=0)
            + np.roll(state, 1, axis=1)
            + np.roll(state, -1, axis=1)
            - 4.0 * state
        )
    return state


def _modes(grid: int, frequencies: tuple[int, ...]) -> np.ndarray:
    coordinate = np.arange(grid, dtype=float)
    return np.asarray(
        [
            sqrt(2.0)
            * np.cos(2.0 * pi * frequency * coordinate / grid)[:, None]
            * np.ones((1, grid))
            for frequency in frequencies
        ]
    )


class HeatOracle:
    def __init__(self, grid: int, steps: int, frequencies: tuple[int, ...]) -> None:
        self.grid = grid
        self.steps = steps
        self.ratio = 0.12
        self.frequencies = frequencies
        self.modes = _modes(grid, frequencies)

    def eigenvalues(self) -> np.ndarray:
        values = []
        for frequency in self.frequencies:
            propagator = 1.0 + self.ratio * (
                2.0 * cos(2.0 * pi * frequency / self.grid) + 2.0 - 4.0
            )
            values.append(0.3 + 0.7 * propagator ** (2 * self.steps))
        return np.asarray(values)

    def gradient(self, point: np.ndarray, target: np.ndarray) -> np.ndarray:
        error = point - target
        initial = sqrt(0.7) * np.tensordot(error, self.modes, axes=(0, 0))
        state = _heat(initial, steps=self.steps, ratio=self.ratio)
        adjoint = _heat(state, steps=self.steps, ratio=self.ratio)
        data_gradient = sqrt(0.7) * np.mean(
            self.modes * adjoint[None, :, :], axis=(1, 2)
        )
        return 0.3 * error + data_gradient


def _remaining_calls(
    start: np.ndarray,
    target: np.ndarray,
    oracle: HeatOracle,
    *,
    tolerance: float,
    horizon: int,
    timings: list[float],
) -> tuple[int, float]:
    point = start.copy()
    for calls in range(horizon + 1):
        started = perf_counter()
        gradient = oracle.gradient(point, target)
        timings.append(perf_counter() - started)
        norm = float(np.linalg.norm(gradient))
        if norm <= tolerance:
            return calls, norm
        point -= gradient
    raise RuntimeError("heat inverse continuation exceeded the H6 horizon")


def _quantiles(values: list[float]) -> dict[str, float]:
    data = np.asarray(values, dtype=float)
    return {
        "minimum": float(np.min(data)),
        "q25": float(np.quantile(data, 0.25)),
        "median": float(np.median(data)),
        "q75": float(np.quantile(data, 0.75)),
        "maximum": float(np.max(data)),
    }


def run_benchmark(episode_count: int = 64) -> dict[str, Any]:
    if episode_count <= 0 or episode_count % 2:
        raise ValueError("episode_count must be a positive even integer")
    frequencies = (1, 24)
    exact = HeatOracle(640, 120, frequencies)
    surrogate = HeatOracle(80, 3, frequencies)
    exact_eigenvalues = exact.eigenvalues()
    surrogate_eigenvalues = surrogate.eigenvalues()
    if not (np.min(exact_eigenvalues) > 0.3 and np.max(exact_eigenvalues) < 1.0):
        raise RuntimeError("analytic heat spectrum is outside F_{3/10,1}")

    target_amplitudes = 0.5 / exact_eigenvalues
    tolerance = 7.0 / 25.0
    proposal_step = Fraction(11, 10)
    proposal_lower = Fraction(27, 50)
    proposal_upper = Fraction(14, 25)
    contract_radius = Fraction(1, 100)
    distance_upper = Fraction(9, 5)
    exact_timings: list[float] = []
    surrogate_timings: list[float] = []
    rows = []
    for episode in range(episode_count):
        mode = episode % 2
        sign = -1.0 if (episode // 2) % 2 else 1.0
        target = np.zeros(2)
        target[mode] = sign * target_amplitudes[mode]
        origin = np.zeros(2)

        started = perf_counter()
        exact_gradient = exact.gradient(origin, target)
        exact_timings.append(perf_counter() - started)
        started = perf_counter()
        surrogate_gradient = surrogate.gradient(origin, target)
        surrogate_timings.append(perf_counter() - started)
        candidate = -float(proposal_step) * surrogate_gradient
        exact_gradient_fraction = binary64_vector(exact_gradient)
        membership = certify_h6_envelope_membership(
            candidate,
            exact_gradient_fraction,
            proposal_step=proposal_step,
            proposal_lower=proposal_lower,
            proposal_upper=proposal_upper,
            contract_radius=contract_radius,
            strong_monotonicity=Fraction(3, 10),
            distance_upper=distance_upper,
        )
        baseline_calls, baseline_terminal = _remaining_calls(
            origin,
            target,
            exact,
            tolerance=tolerance,
            horizon=6,
            timings=exact_timings,
        )
        candidate_calls, candidate_terminal = _remaining_calls(
            candidate,
            target,
            exact,
            tolerance=tolerance,
            horizon=6,
            timings=exact_timings,
        )
        attempted = bool(
            (proposal_lower - contract_radius) ** 2
            <= proposal_step**2
            * sum((value * value for value in exact_gradient_fraction), Fraction(0))
            <= (proposal_upper + contract_radius) ** 2
        )
        accepted = attempted and membership.accepted
        if accepted and candidate_calls >= baseline_calls:
            raise RuntimeError("accepted heat episode violates the H6 certificate")
        rows.append(
            {
                "episode": episode,
                "mode": "resolved-low-frequency" if mode == 0 else "underresolved-high-frequency",
                "frequency": frequencies[mode],
                "attempted_after_free_prefilter": attempted,
                "accepted_by_joint_gate": accepted,
                "decision_outcome": "accept" if accepted else "uncertified",
                "proposal_norm": float(np.linalg.norm(candidate)),
                "contract_residual_norm": float(
                    membership.residual_squared_norm
                )
                ** 0.5,
                "baseline_calls": baseline_calls,
                "candidate_calls": candidate_calls,
                "baseline_terminal_norm": baseline_terminal,
                "candidate_terminal_norm": candidate_terminal,
            }
        )

    baseline_calls = sum(row["baseline_calls"] for row in rows)
    gated_calls = sum(
        row["candidate_calls"] if row["accepted_by_joint_gate"] else row["baseline_calls"]
        for row in rows
    )
    prefilter_calls = sum(row["candidate_calls"] for row in rows)
    overruns = sum(
        row["attempted_after_free_prefilter"]
        and row["candidate_calls"] >= row["baseline_calls"]
        for row in rows
    )
    exact_timing = _quantiles(exact_timings)
    surrogate_timing = _quantiles(surrogate_timings)
    cheap_ratio = surrogate_timing["median"] / exact_timing["median"]
    cheap_units = episode_count * cheap_ratio
    certificate_cost = json.loads(COST_PAYLOAD.read_text(encoding="utf-8"))
    certificate_seconds = float(
        certificate_cost["measurement"]["total_certificate_seconds"]
    )
    certificate_units = certificate_seconds / exact_timing["median"]
    per_decision_unpenalized_saving = (
        baseline_calls - gated_calls - cheap_units
    ) / episode_count
    unpenalized_reuse_threshold = ceil(
        certificate_units / per_decision_unpenalized_saving
    )
    risk_penalty = 12.0
    gate_cold_units = gated_calls + cheap_units + certificate_units
    prefilter_risk_units = (
        prefilter_calls + cheap_units + risk_penalty * overruns
    )
    if not gate_cold_units < prefilter_risk_units:
        raise RuntimeError(
            "measured risk ledger is not self-financing: "
            f"gate={gate_cold_units}, comparator={prefilter_risk_units}"
        )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "declaration": {
            "workload": (
                "two-mode inverse problem for the periodic 2-D heat equation; "
                "the exact oracle executes full-grid forward and adjoint solves"
            ),
            "expensive_oracle": (
                "640x640 grid, 120 forward and 120 adjoint explicit heat steps"
            ),
            "cheap_oracle": (
                "80x80 grid, three forward and three adjoint heat steps"
            ),
            "claim": (
                "measured cold certificate cost is dominated by a declared "
                "risk-adjusted prefilter ledger, not by the unpenalized baseline"
            ),
            "risk_penalty": (
                "12 exact-call units for each attempted branch that fails to "
                "save the required call; this is a deployment preference, not "
                "an empirical loss estimate"
            ),
        },
        "configuration": {
            "episode_count": episode_count,
            "frequencies": list(frequencies),
            "tolerance": tolerance,
            "risk_penalty_exact_units": risk_penalty,
        },
        "spectral_contract": {
            "exact_eigenvalues": exact_eigenvalues.tolist(),
            "surrogate_eigenvalues": surrogate_eigenvalues.tolist(),
            "declared_strong_convexity": 0.3,
            "declared_smoothness": 1.0,
            "maximum_exact_gradient_norm_error_against_diagonal_formula": max(
                abs(
                    float(np.linalg.norm(exact.gradient(np.zeros(2), np.eye(2)[index])))
                    - exact_eigenvalues[index]
                )
                for index in range(2)
            ),
        },
        "timing_seconds": {
            "exact_oracle": exact_timing,
            "cheap_oracle": surrogate_timing,
            "measured_cheap_to_exact_ratio": cheap_ratio,
            "frozen_certificate_search_plus_replay": certificate_seconds,
        },
        "ledger_exact_call_units": {
            "baseline": baseline_calls,
            "gate_warm": gated_calls + cheap_units,
            "gate_cold_including_certificate": gate_cold_units,
            "prefilter_unpenalized": prefilter_calls + cheap_units,
            "prefilter_risk_adjusted": prefilter_risk_units,
            "certificate": certificate_units,
            "risk_penalty_total": risk_penalty * overruns,
            "gate_to_risk_adjusted_prefilter_ratio": gate_cold_units
            / prefilter_risk_units,
            "cold_gate_beats_risk_adjusted_prefilter": True,
            "cold_gate_beats_unpenalized_baseline": gate_cold_units <= baseline_calls,
            "break_even_risk_penalty_per_overrun": (
                gate_cold_units - prefilter_calls - cheap_units
            )
            / overruns,
        },
        "summary": {
            "attempted": sum(row["attempted_after_free_prefilter"] for row in rows),
            "accepted": sum(row["accepted_by_joint_gate"] for row in rows),
            "rejected": 0,
            "uncertified_by_contract": sum(
                row["attempted_after_free_prefilter"]
                and not row["accepted_by_joint_gate"]
                for row in rows
            ),
            "prefilter_nonimproving_branches": overruns,
            "baseline_calls": baseline_calls,
            "gated_calls": gated_calls,
            "prefilter_calls": prefilter_calls,
            "amortization_episode_threshold_against_risk_adjusted_prefilter": ceil(
                certificate_units
                / ((prefilter_calls + risk_penalty * overruns - gated_calls) / episode_count)
            ),
            "amortization_episode_threshold_against_unpenalized_baseline": (
                unpenalized_reuse_threshold
            ),
            "per_decision_unpenalized_saving_before_certificate": (
                per_decision_unpenalized_saving
            ),
        },
        "rows": rows,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "runner_sha256": _file_hash(Path(__file__)),
            "certificate_file_sha256": _file_hash(CERTIFICATE),
            "certificate_cost_file_sha256": _file_hash(COST_PAYLOAD),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    return payload


def main() -> None:
    payload = run_benchmark()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    ledger = payload["ledger_exact_call_units"]
    print(
        "MEASURED: heat inverse benchmark, "
        f"exact median={payload['timing_seconds']['exact_oracle']['median']:.3f}s, "
        f"gate/risk-prefilter={ledger['gate_to_risk_adjusted_prefilter_ratio']:.3f}, "
        f"accepted={payload['summary']['accepted']}, "
        f"protected={payload['summary']['prefilter_nonimproving_branches']}"
    )


if __name__ == "__main__":
    main()
