"""A transparent quadratic testbed with provable two-oracle contracts."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np


@dataclass(frozen=True)
class DiagonalQuadratic:
    """f(x)=0.5 (x-x_star)^T Q (x-x_star), with diagonal SPD Q."""

    eigenvalues: np.ndarray
    x_star: np.ndarray
    exact_step_size: float

    def __post_init__(self) -> None:
        eigenvalues = np.asarray(self.eigenvalues, dtype=float)
        x_star = np.asarray(self.x_star, dtype=float)
        if eigenvalues.ndim != 1 or x_star.shape != eigenvalues.shape:
            raise ValueError("eigenvalues and x_star must be matching vectors")
        if np.any(eigenvalues <= 0.0):
            raise ValueError("Q must be positive definite")
        if not 0.0 < self.exact_step_size < 1.0 / float(eigenvalues.max()):
            raise ValueError("step must lie strictly between 0 and 1/L")

    @property
    def mu(self) -> float:
        return float(np.min(self.eigenvalues))

    @property
    def smoothness(self) -> float:
        return float(np.max(self.eigenvalues))

    @property
    def lower_contraction(self) -> float:
        return 1.0 - self.exact_step_size * self.smoothness

    @property
    def upper_contraction(self) -> float:
        return 1.0 - self.exact_step_size * self.mu

    def residual(self, x: np.ndarray) -> float:
        error = np.asarray(x, dtype=float) - self.x_star
        return sqrt(float(np.dot(self.eigenvalues * error, error)))

    def normalize_residual(self, x: np.ndarray, target: float = 1.0) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        error = x - self.x_star
        current = self.residual(x)
        if current == 0.0:
            raise ValueError("cannot normalize the optimum")
        return self.x_star + error * (target / current)

    def exact_step(self, x: np.ndarray) -> np.ndarray:
        error = np.asarray(x, dtype=float) - self.x_star
        return x - self.exact_step_size * self.eigenvalues * error

    def exact_calls_to_tolerance(
        self, x: np.ndarray, tolerance: float, *, max_calls: int = 100_000
    ) -> int:
        point = np.asarray(x, dtype=float).copy()
        calls = 0
        while self.residual(point) > tolerance:
            if calls >= max_calls:
                raise RuntimeError("exact iteration cap reached")
            point = self.exact_step(point)
            calls += 1
        return calls

    def approximate_newton_step(
        self, x: np.ndarray, relative_diagonal_error: np.ndarray
    ) -> np.ndarray:
        """Use Q_tilde^{-1} grad f, where Q_tilde_i=Q_i(1+error_i)."""

        relative_error = np.asarray(relative_diagonal_error, dtype=float)
        if relative_error.shape != self.eigenvalues.shape:
            raise ValueError("relative error has the wrong shape")
        if np.any(relative_error <= -1.0):
            raise ValueError("approximate Hessian must remain positive")
        error = np.asarray(x, dtype=float) - self.x_star
        cheap_direction = error / (1.0 + relative_error)
        return x - cheap_direction


def approximate_newton_contraction(delta: float) -> float:
    """Q-norm contraction implied by (1-delta)Q <= Q_tilde <= (1+delta)Q."""

    if not 0.0 <= delta < 1.0:
        raise ValueError("delta must lie in [0,1)")
    return delta / (1.0 - delta)
