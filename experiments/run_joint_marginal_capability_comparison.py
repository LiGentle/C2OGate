#!/usr/bin/env python3
"""Exact comparison of joint stopping cells with conditioned marginals."""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "joint_marginal_capability_comparison.json"
FIGURE_PDF = ROOT / "figures" / "joint_vs_marginal_rectangle.pdf"
FIGURE_PNG = ROOT / "figures" / "joint_vs_marginal_rectangle.png"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _load(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    claimed = unsigned.pop("payload_sha256")
    if sha256(_canonical(unsigned)).hexdigest() != claimed:
        raise RuntimeError(f"hash mismatch: {relative}")
    return payload


def _rows() -> list[dict[str, Any]]:
    declarations = (
        (
            "full-class H=3",
            "certificates/full_class_joint_only_pep_dual.json",
        ),
        ("nonzero-radius H=6", "certificates/h6_joint_only_pep_dual.json"),
        (
            "40% wider H=6",
            "certificates/h6_medium_radius_pep_dual.json",
        ),
    )
    rows = []
    for label, relative in declarations:
        payload = _load(relative)
        joint = payload["joint_certificate"]
        marginal = payload["marginal_certificate"]
        rows.append(
            {
                "transcript": label,
                "horizon": payload["declaration"]["horizon"],
                "joint_bad_cells_excluded": payload["summary"]["certificate_count"],
                "joint_bad_cell_count": len(payload["declaration"]["cells"]),
                "joint_certificate_value": joint["certificate_value"],
                "joint_accept": joint["joint_accept"],
                "conditioned_marginal_rectangle_value": marginal[
                    "rectangle_certificate_value"
                ],
                "conditioned_marginals_accept": joint["rectangle_accept"],
                "source_payload_sha256": payload["payload_sha256"],
            }
        )

    shift = _load("certificates/exact_shift_joint_only_h10.json")
    rows.append(
        {
            "transcript": "exact-shift H=10",
            "horizon": 10,
            "joint_bad_cells_excluded": 66,
            "joint_bad_cell_count": 66,
            "joint_certificate_value": shift["joint_certificate"]["certificate_value"],
            "joint_accept": shift["joint_certificate"]["accept"],
            "conditioned_marginal_rectangle_value": shift["marginal_rectangle"][
                "certificate_value_lower_bound"
            ],
            "conditioned_marginals_accept": shift["marginal_rectangle"]["accept"],
            "source_payload_sha256": shift["payload_sha256"],
        }
    )

    h10 = _load("certificates/h10_generic_pep_dual.json")
    marginal = _load("certificates/h10_marginal_pep_dual.json")
    rows.append(
        {
            "transcript": "balanced H=10 control",
            "horizon": 10,
            "joint_bad_cells_excluded": h10["summary"]["certificate_count"],
            "joint_bad_cell_count": len(h10["declaration"]["cells"]),
            "joint_certificate_value": "0",
            "joint_accept": True,
            "conditioned_marginal_rectangle_value": str(
                marginal["exact_consequences"][
                    "rectangle_gate_value_with_max_cost_one"
                ]
            ),
            "conditioned_marginals_accept": True,
            "source_payload_sha256": h10["payload_sha256"],
            "marginal_payload_sha256": marginal["payload_sha256"],
        }
    )
    return rows


def _figure(rows: list[dict[str, Any]]) -> None:
    plt.rcParams.update({"font.size": 8.5, "axes.titlesize": 9.5})
    figure, axes = plt.subplots(1, 2, figsize=(7.05, 2.72))

    ax = axes[0]
    rectangle = np.asarray([(r, s) for r in range(1, 11) for s in range(10)])
    joint = np.asarray([(r, r - 1) for r in range(1, 11)])
    spurious = rectangle[rectangle[:, 1] >= rectangle[:, 0]]
    ax.scatter(
        rectangle[:, 0], rectangle[:, 1], s=13, marker="s", color="#d9e2ec",
        label="marginal rectangle",
    )
    ax.scatter(
        spurious[:, 0], spurious[:, 1], s=17, marker="s", color="#d95f59",
        label="spurious bad cells",
    )
    ax.plot(
        joint[:, 0], joint[:, 1], "o-", color="#1769aa", linewidth=1.5,
        markersize=3.5, label="joint set $s=r-1$",
    )
    ax.set(xlabel="baseline calls $r$", ylabel="candidate calls $s$", xlim=(0.4, 10.6), ylim=(-0.6, 9.6))
    ax.set_title("Exact-shift transcript")
    ax.grid(alpha=0.18)
    ax.legend(frameon=False, fontsize=7, loc="upper left")

    ax = axes[1]
    labels = ["H3", "H6", "H6\nwide", "shift\nH10", "control\nH10"]
    joint_values = [float(Fraction(row["joint_certificate_value"])) for row in rows]
    rectangle_values = [
        float(Fraction(row["conditioned_marginal_rectangle_value"]))
        for row in rows
    ]
    locations = np.arange(len(rows))
    width = 0.36
    ax.bar(locations - width / 2, joint_values, width, color="#1769aa", label="joint")
    ax.bar(locations + width / 2, rectangle_values, width, color="#d95f59", label="marginals")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_xticks(locations, labels)
    ax.set_ylabel("certificate value (accept if $\leq0$)")
    ax.set_title("Same transcript, different retained information")
    ax.legend(frameon=False, fontsize=7)
    ax.grid(axis="y", alpha=0.18)
    figure.tight_layout(w_pad=2.0)
    figure.savefig(FIGURE_PDF, bbox_inches="tight")
    figure.savefig(FIGURE_PNG, dpi=220, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    rows = _rows()
    _figure(rows)
    payload: dict[str, Any] = {
        "schema": "c2o-joint-marginal-capability-v1",
        "declaration": {
            "comparison": (
                "the joint stopping-pair PEP and sharp separately conditioned "
                "single-track marginals use the same transcript and function class"
            ),
            "interpretation": (
                "marginalization preserves each endpoint but discards whether the "
                "two endpoints are attainable by the same function"
            ),
            "control": (
                "the balanced H=10 row is retained because both methods accept; "
                "the comparison is not selected to force a joint advantage"
            ),
        },
        "summary": {
            "transcript_count": len(rows),
            "joint_only_accept_count": sum(
                row["joint_accept"] and not row["conditioned_marginals_accept"]
                for row in rows
            ),
            "both_accept_count": sum(
                row["joint_accept"] and row["conditioned_marginals_accept"]
                for row in rows
            ),
        },
        "rows": rows,
        "figure_sha256": {
            "pdf": sha256(FIGURE_PDF.read_bytes()).hexdigest(),
            "png": sha256(FIGURE_PNG.read_bytes()).hexdigest(),
        },
    }
    payload["payload_sha256"] = sha256(_canonical(payload)).hexdigest()
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "FROZEN: joint versus conditioned marginals, "
        f"joint-only={payload['summary']['joint_only_accept_count']}/"
        f"{payload['summary']['transcript_count']}, "
        f"both={payload['summary']['both_accept_count']}"
    )


if __name__ == "__main__":
    main()
