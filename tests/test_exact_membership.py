from fractions import Fraction

from c2ogate.exact_membership import (
    binary64_vector,
    certify_h6_envelope_membership,
    exact_linear_data_gradient,
    rational_squared_norm,
)


def test_binary64_conversion_and_squared_norm_are_exact() -> None:
    vector = binary64_vector([0.5, -0.25])
    assert vector == (Fraction(1, 2), Fraction(-1, 4))
    assert rational_squared_norm(vector) == Fraction(5, 16)


def test_logistic_gradient_at_origin_is_rebuilt_exactly() -> None:
    gradient = exact_linear_data_gradient(
        [[0.5, 0.25], [-0.5, 0.75]],
        [0.0, 1.0],
        Fraction(4, 5),
    )
    assert gradient == (Fraction(1, 5), Fraction(-1, 10))


def test_h6_membership_uses_exact_closed_boundaries() -> None:
    gradient = (Fraction(1, 2), Fraction(0))
    accepted = certify_h6_envelope_membership(
        [-0.55, 0.0],
        gradient,
        proposal_step=Fraction(11, 10),
        proposal_lower=Fraction(27, 50),
        proposal_upper=Fraction(14, 25),
        contract_radius=Fraction(1, 100),
        strong_monotonicity=Fraction(4, 5),
        distance_upper=Fraction(9, 5),
    )
    assert accepted.accepted
    rejected = certify_h6_envelope_membership(
        [-0.57, 0.0],
        gradient,
        proposal_step=Fraction(11, 10),
        proposal_lower=Fraction(27, 50),
        proposal_upper=Fraction(14, 25),
        contract_radius=Fraction(1, 100),
        strong_monotonicity=Fraction(4, 5),
        distance_upper=Fraction(9, 5),
    )
    assert not rejected.accepted
    assert not rejected.residual_ball_passed
