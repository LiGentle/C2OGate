"""Cost-certified two-oracle optimization gates."""

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
from .active_set import (
    ActiveRegimeCertificate,
    box_projection_active_regime,
    box_projection_candidate_regime,
    reduced_matrix,
    soft_threshold_active_regime,
    soft_threshold_candidate_regime,
)
from .costs import (
    AccountedGateDecision,
    CostBreakdown,
    ProductiveCertificateDecision,
    cost_accounted_gate,
    productive_certificate_gate,
)
from .dynamic_certificates import (
    BranchPointHessianSchedule,
    ChartedIterationCertificate,
    DynamicResidualTube,
    LipschitzHessianSchedule,
    branch_point_hessian_schedule_from_gradient,
    composite_chart_jacobian_lipschitz,
    contraction_calls_from_residual_upper,
    dynamic_krylov_envelope,
    lipschitz_hessian_schedule_from_gradient,
    nonlinear_model_step_post_residual_upper,
    sphere_retraction_defect_coefficient,
)
from .matrix_certificates import (
    KrylovResidualTube,
    MatrixUncertainty,
    krylov_matrix_uncertainty_envelope,
    matrix_approximate_newton_post_upper,
    matrix_uncertainty_progress_factors,
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
    proof_carrying_gate,
)

__all__ = [
    "AccountedGateDecision",
    "ActiveRegimeCertificate",
    "BranchPointHessianSchedule",
    "ChartedIterationCertificate",
    "CellProof",
    "CellProofStatus",
    "CountEnvelope",
    "CostBreakdown",
    "DiagonalQuadratic",
    "GateDecision",
    "GateOutcome",
    "KrylovResidualTube",
    "DynamicResidualTube",
    "LipschitzHessianSchedule",
    "MatrixUncertainty",
    "ModalCertificate",
    "ProductiveCertificateDecision",
    "ProofCarryingDecision",
    "StoppingPair",
    "TranscriptGateDecision",
    "box_projection_active_regime",
    "box_projection_candidate_regime",
    "branch_point_hessian_schedule_from_gradient",
    "composite_chart_jacobian_lipschitz",
    "contraction_count_envelope",
    "cost_accounted_gate",
    "contraction_calls_from_residual_upper",
    "dynamic_krylov_envelope",
    "krylov_matrix_uncertainty_envelope",
    "matrix_approximate_newton_post_upper",
    "matrix_uncertainty_progress_factors",
    "lipschitz_hessian_schedule_from_gradient",
    "modal_approximate_newton_post_upper",
    "modal_gradient_descent_envelope",
    "nonlinear_model_step_post_residual_upper",
    "productive_certificate_gate",
    "proof_carrying_gate",
    "reduced_matrix",
    "relative_modal_certificate",
    "robust_cost_gate",
    "soft_threshold_active_regime",
    "soft_threshold_candidate_regime",
    "smooth_gradient_call_lower_bound",
    "sphere_retraction_defect_coefficient",
    "transcript_optimal_gate",
]
