"""Proof-carrying continuation decisions and exact transcript checks."""

from .core import (
    CountEnvelope,
    GateDecision,
    contraction_count_envelope,
    robust_cost_gate,
)
from .certificates import (
    ModalCertificate,
    modal_approximate_newton_post_upper,
    modal_gradient_descent_envelope,
    relative_modal_certificate,
    smooth_gradient_call_lower_bound,
)
from .quadratic import DiagonalQuadratic
from .costs import (
    AccountedGateDecision,
    CostBreakdown,
    ProductiveCertificateDecision,
    cost_accounted_gate,
    productive_certificate_gate,
)
from .exact_membership import (
    ExactEnvelopeMembership,
    binary64_vector,
    certify_h6_envelope_membership,
    exact_linear_data_gradient,
    exact_max_row_squared_norm,
    rational_squared_norm,
)
from .transcript import (
    StoppingPair,
    TranscriptGateDecision,
    transcript_optimal_gate,
)
from .workflow import (
    CellProof,
    CellProofStatus,
    GateOutcome,
    ProofCarryingDecision,
    TranscriptConstraintForm,
    TranscriptConstraintSpec,
    TranscriptInterfaceAdmission,
    certified_branch_workflow,
    proof_carrying_gate,
    validate_transcript_interface,
)

__all__ = [
    "AccountedGateDecision",
    "CellProof",
    "CellProofStatus",
    "CountEnvelope",
    "CostBreakdown",
    "DiagonalQuadratic",
    "GateDecision",
    "GateOutcome",
    "ExactEnvelopeMembership",
    "ModalCertificate",
    "ProductiveCertificateDecision",
    "ProofCarryingDecision",
    "StoppingPair",
    "TranscriptGateDecision",
    "TranscriptConstraintForm",
    "TranscriptConstraintSpec",
    "TranscriptInterfaceAdmission",
    "binary64_vector",
    "certify_h6_envelope_membership",
    "contraction_count_envelope",
    "cost_accounted_gate",
    "certified_branch_workflow",
    "exact_linear_data_gradient",
    "exact_max_row_squared_norm",
    "modal_approximate_newton_post_upper",
    "modal_gradient_descent_envelope",
    "productive_certificate_gate",
    "proof_carrying_gate",
    "rational_squared_norm",
    "relative_modal_certificate",
    "robust_cost_gate",
    "smooth_gradient_call_lower_bound",
    "transcript_optimal_gate",
    "validate_transcript_interface",
]
