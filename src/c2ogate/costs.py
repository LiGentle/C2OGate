"""End-to-end cost accounting for online and amortized certificates."""

from __future__ import annotations

from dataclasses import dataclass

from .core import GateDecision


@dataclass(frozen=True)
class CostBreakdown:
    """Wall-clock costs converted to exact-oracle-call units."""

    exact_call_seconds: float
    cheap_oracle_seconds: float
    certificate_seconds: float = 0.0
    verification_seconds: float = 0.0
    certificate_amortization_count: int = 1

    def __post_init__(self) -> None:
        values = (
            self.exact_call_seconds,
            self.cheap_oracle_seconds,
            self.certificate_seconds,
            self.verification_seconds,
        )
        if self.exact_call_seconds <= 0.0 or any(value < 0.0 for value in values[1:]):
            raise ValueError("costs must be nonnegative and exact cost positive")
        if self.certificate_amortization_count < 1:
            raise ValueError("certificate_amortization_count must be positive")

    @property
    def predecision_exact_units(self) -> float:
        return (
            self.certificate_seconds
            / self.certificate_amortization_count
            / self.exact_call_seconds
        )

    @property
    def accepted_incremental_exact_units(self) -> float:
        total = (
            self.cheap_oracle_seconds
            + self.verification_seconds
            + self.certificate_seconds / self.certificate_amortization_count
        )
        return total / self.exact_call_seconds


@dataclass(frozen=True)
class AccountedGateDecision:
    """Gate result including the cost of deciding and the reject path."""

    gate: GateDecision
    reject_path_noninferior: bool
    predecision_cost_exact_units: float
    accepted_incremental_cost_exact_units: float
    banked_credit_before: float
    guaranteed_credit_after: float


@dataclass(frozen=True)
class ProductiveCertificateDecision:
    """Zero-credit decision whose certificate work produces a fallback."""

    run_certificate: bool
    use_proposal: bool
    fallback_path_noninferior: bool
    selected_upper_calls: int | None
    guaranteed_cost_slack_exact_units: float
    guaranteed_saved_exact_calls: int


def cost_accounted_gate(
    baseline_lower_calls: int,
    post_upper_calls: int,
    costs: CostBreakdown,
    *,
    minimum_saved_calls: int = 1,
    banked_credit_exact_units: float = 0.0,
) -> AccountedGateDecision:
    """Apply the robust gate after charging certificate construction.

    Online certificate work is paid before the accept/reject decision.  Thus a
    rejected branch is instance-wise non-inferior only when that work is free,
    shared with the baseline, amortized to zero, or covered by previously
    banked credit.  Accepted branches charge certificate, cheap oracle, and
    verification work together.
    """

    if banked_credit_exact_units < 0.0:
        raise ValueError("banked credit must be nonnegative")
    if baseline_lower_calls < 0 or post_upper_calls < 0:
        raise ValueError("call bounds must be nonnegative")
    if minimum_saved_calls < 0:
        raise ValueError("minimum_saved_calls must be nonnegative")
    accepted_cost = costs.accepted_incremental_exact_units
    saved = baseline_lower_calls - post_upper_calls
    slack = saved + banked_credit_exact_units - accepted_cost
    gate = GateDecision(
        accept=bool(saved >= minimum_saved_calls and slack >= -1.0e-12),
        baseline_lower_calls=int(baseline_lower_calls),
        post_upper_calls=int(post_upper_calls),
        cheap_cost_exact_units=float(accepted_cost),
        guaranteed_saved_exact_calls=int(saved),
        guaranteed_cost_slack_exact_units=float(slack),
        minimum_saved_calls=int(minimum_saved_calls),
    )
    reject_safe = (
        costs.predecision_exact_units <= banked_credit_exact_units + 1.0e-12
    )
    if gate.accept:
        credit_after = banked_credit_exact_units + saved - accepted_cost
    else:
        credit_after = banked_credit_exact_units - costs.predecision_exact_units
    return AccountedGateDecision(
        gate=gate,
        reject_path_noninferior=reject_safe,
        predecision_cost_exact_units=costs.predecision_exact_units,
        accepted_incremental_cost_exact_units=accepted_cost,
        banked_credit_before=banked_credit_exact_units,
        guaranteed_credit_after=float(credit_after),
    )


def productive_certificate_gate(
    free_baseline_lower_calls: int,
    fallback_upper_calls: int,
    refined_baseline_lower_calls: int,
    proposal_upper_calls: int,
    certificate_cost_exact_units: float,
    *,
    proposal_cost_exact_units: float = 0.0,
    minimum_saved_calls: int = 1,
) -> ProductiveCertificateDecision:
    """Fund the first paid decision with guaranteed fallback progress.

    Certificate construction is allowed to cost money before its accept/reject
    result is known only if that same computation returns a fallback state
    ``z`` satisfying ``d + U_z <= L_free``.  If a reduction of at least ``m``
    exact calls is requested on every branch, it must also satisfy
    ``U_z <= L_free-m``.  A rejected proposal then continues from ``z``, not
    from the unchanged branch state.  These are the endpoint tests for cost
    noninferiority and call reduction, respectively.
    """

    integer_values = (
        free_baseline_lower_calls,
        fallback_upper_calls,
        refined_baseline_lower_calls,
        proposal_upper_calls,
        minimum_saved_calls,
    )
    if any(value < 0 for value in integer_values):
        raise ValueError("call counts and requested savings must be nonnegative")
    if certificate_cost_exact_units < 0.0 or proposal_cost_exact_units < 0.0:
        raise ValueError("costs must be nonnegative")
    if refined_baseline_lower_calls < free_baseline_lower_calls:
        raise ValueError("the refined lower certificate cannot be weaker")

    fallback_saved = free_baseline_lower_calls - fallback_upper_calls
    fallback_slack = (
        free_baseline_lower_calls
        - certificate_cost_exact_units
        - fallback_upper_calls
    )
    run = bool(
        fallback_saved >= minimum_saved_calls
        and fallback_slack >= -1.0e-12
    )
    proposal_total_cost = (
        certificate_cost_exact_units
        + proposal_cost_exact_units
        + proposal_upper_calls
    )
    proposal_saved = refined_baseline_lower_calls - proposal_upper_calls
    use_proposal = bool(
        run
        and proposal_saved >= minimum_saved_calls
        and proposal_total_cost <= refined_baseline_lower_calls + 1.0e-12
    )
    if not run:
        selected_upper = None
        slack = 0.0
        saved = 0
    elif use_proposal:
        selected_upper = proposal_upper_calls
        slack = refined_baseline_lower_calls - proposal_total_cost
        saved = proposal_saved
    else:
        selected_upper = fallback_upper_calls
        slack = fallback_slack
        saved = free_baseline_lower_calls - fallback_upper_calls
    return ProductiveCertificateDecision(
        run_certificate=run,
        use_proposal=use_proposal,
        fallback_path_noninferior=bool(fallback_slack >= -1.0e-12),
        selected_upper_calls=(
            None if selected_upper is None else int(selected_upper)
        ),
        guaranteed_cost_slack_exact_units=float(slack),
        guaranteed_saved_exact_calls=int(saved),
    )
