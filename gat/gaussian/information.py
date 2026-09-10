"""Sparse information-form belief over RAW variables.

Dense ``Sigma`` is the bitwise digest oracle on small worlds. It is the
wrong resident representation for a storey of MEP: covariance is dense
even when the precision graph is sparse, and Cholesky of an ``n x n``
dense matrix is ``O(n^3)``.

This module stores the raw Gaussian in information form

    ``Lambda = Sigma^{-1}``, ``eta = Lambda mu``

and keeps only the nonzero precision entries implied by the current
correlation graph. Connected components are factored with the existing
dense Cholesky path, so a building made of independent storeys costs
``O(sum k_c^3)`` rather than ``O(n^3)``.

The world digest is not computed from this object. Crossing from sparse
to dense requires an explicit ``to_dense()`` call and is refused when
``n`` exceeds ``DENSE_MATERIALIZE_LIMIT``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gat.errors import ConditioningError, NumericalError
from gat.gaussian.condition import ConditioningRecord, condition
from gat.gaussian.linalg import chol_psd, chol_solve
from gat.gaussian.state import GaussianState, VarIndex
from gat.ids import VarId


DENSE_MATERIALIZE_LIMIT = 256


def _canon(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i >= j else (j, i)


@dataclass(frozen=True)
class SparseInformationBelief:
    """Raw-space Gaussian stored as ``(eta, Lambda)`` with sparse ``Lambda``."""

    index: VarIndex
    eta: np.ndarray
    precision: dict[tuple[int, int], float]

    def __post_init__(self) -> None:
        n = len(self.index)
        eta = np.asarray(self.eta, dtype=np.float64).reshape(n).copy()
        if not np.isfinite(eta).all():
            raise NumericalError("information vector contains non-finite entries")
        eta.setflags(write=False)
        object.__setattr__(self, "eta", eta)
        cleaned: dict[tuple[int, int], float] = {}
        for key, value in self.precision.items():
            i, j = key
            if not (0 <= i < n and 0 <= j < n):
                raise NumericalError("precision index is outside the raw space")
            if not np.isfinite(value):
                raise NumericalError("precision contains non-finite entries")
            if value == 0.0:
                continue
            slot = _canon(i, j)
            cleaned[slot] = cleaned.get(slot, 0.0) + float(value)
        object.__setattr__(self, "precision", cleaned)

    @property
    def n(self) -> int:
        return len(self.index)

    @property
    def nnz(self) -> int:
        """Stored lower-triangle entries, including the diagonal."""
        return len(self.precision)

    @property
    def dense_covariance_entries(self) -> int:
        return self.n * self.n

    def resident_bytes(self) -> int:
        """Information vector plus one float64 and two intp per stored entry."""
        return 8 * self.n + self.nnz * (8 + 2 * 8)

    def components(self) -> tuple[tuple[int, ...], ...]:
        parent = list(range(self.n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        for i, j in self.precision:
            if i != j:
                union(i, j)
        buckets: dict[int, list[int]] = {}
        for index in range(self.n):
            buckets.setdefault(find(index), []).append(index)
        return tuple(tuple(sorted(members)) for _, members in sorted(buckets.items()))

    def _block(self, rows: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
        local = {row: offset for offset, row in enumerate(rows)}
        k = len(rows)
        precision = np.zeros((k, k), dtype=np.float64)
        for (i, j), value in self.precision.items():
            if i in local and j in local:
                precision[local[i], local[j]] = value
                precision[local[j], local[i]] = value
        return precision, self.eta[list(rows)]

    def mean_vector(self) -> np.ndarray:
        mu = np.zeros(self.n, dtype=np.float64)
        for rows in self.components():
            precision, eta = self._block(rows)
            factor, _ = chol_psd(precision)
            mu[list(rows)] = chol_solve(factor, eta)
        return mu

    def mean(self, var: VarId) -> float:
        return float(self.mean_vector()[self.index.row(var)])

    def variance(self, var: VarId) -> float:
        row = self.index.row(var)
        for rows in self.components():
            if row not in rows:
                continue
            precision, _ = self._block(rows)
            factor, _ = chol_psd(precision)
            eye = np.zeros(len(rows), dtype=np.float64)
            eye[rows.index(row)] = 1.0
            return float(chol_solve(factor, eye)[rows.index(row)])
        raise NumericalError(f"variable {var} is missing from the precision graph")

    def quadratic_form(self, weights: np.ndarray) -> float:
        """Compute ``w^T Sigma w`` without materializing ``Sigma``."""
        weights = np.asarray(weights, dtype=np.float64).reshape(self.n)
        total = 0.0
        for rows in self.components():
            local = np.asarray(rows, dtype=np.intp)
            w = weights[local]
            if not np.any(w):
                continue
            precision, _ = self._block(rows)
            factor, _ = chol_psd(precision)
            solved = chol_solve(factor, w)
            total += float(w @ solved)
        return total

    def to_dense(self) -> GaussianState:
        if self.n > DENSE_MATERIALIZE_LIMIT:
            raise NumericalError(
                f"refusing to materialize a dense {self.n}x{self.n} covariance; "
                f"limit is {DENSE_MATERIALIZE_LIMIT}"
            )
        mu = self.mean_vector()
        sigma = np.zeros((self.n, self.n), dtype=np.float64)
        for rows in self.components():
            precision, _ = self._block(rows)
            factor, _ = chol_psd(precision)
            identity = np.eye(len(rows), dtype=np.float64)
            block = np.column_stack(
                [chol_solve(factor, identity[:, k]) for k in range(len(rows))]
            )
            idx = np.asarray(rows, dtype=np.intp)
            sigma[np.ix_(idx, idx)] = 0.5 * (block + block.T)
        return GaussianState(self.index, mu, sigma)

    def condition(
        self,
        H: np.ndarray,
        predicted: np.ndarray,
        observed: np.ndarray,
        noise_variances: np.ndarray,
    ) -> tuple["SparseInformationBelief", ConditioningRecord]:
        """Condition using the dense Joseph path on the affected components only."""
        H = np.asarray(H, dtype=np.float64)
        if H.ndim != 2 or H.shape[1] != self.n:
            raise ConditioningError(f"H has shape {H.shape}, expected (*, {self.n})")
        support = {int(col) for col in np.flatnonzero(np.any(H != 0.0, axis=0))}
        if not support and H.size:
            raise ConditioningError("observation Jacobian has empty raw support")
        touched: set[int] = set()
        for rows in self.components():
            if support.intersection(rows):
                touched.update(rows)
        if not touched:
            raise ConditioningError("observation does not touch the raw belief")
        order = tuple(sorted(touched))
        local = {row: offset for offset, row in enumerate(order)}
        dense = _component_state(self, order)
        H_local = np.zeros((H.shape[0], len(order)), dtype=np.float64)
        for col in support:
            H_local[:, local[col]] = H[:, col]
        posterior, record = condition(
            dense, H_local, predicted, observed, noise_variances
        )
        return _splice_component(self, order, posterior), record


def from_prior_belief(belief: GaussianState) -> SparseInformationBelief:
    """Lift a raw belief. Diagonal covariances stay sparse; dense priors factorize."""
    n = len(belief.index)
    off = belief.sigma.copy()
    np.fill_diagonal(off, 0.0)
    if float(np.max(np.abs(off))) <= 1e-15 * max(float(np.max(np.abs(belief.sigma))), 1.0):
        precision: dict[tuple[int, int], float] = {}
        eta = np.zeros(n, dtype=np.float64)
        for i in range(n):
            variance = float(belief.sigma[i, i])
            if variance <= 0.0:
                raise NumericalError("raw prior variance must be positive")
            precision[(i, i)] = 1.0 / variance
            eta[i] = belief.mu[i] / variance
        return SparseInformationBelief(belief.index, eta, precision)
    if n > DENSE_MATERIALIZE_LIMIT:
        raise NumericalError(
            "dense raw prior exceeds the materialize limit; "
            "supply an already-sparse information belief"
        )
    factor, _ = chol_psd(belief.sigma)
    identity = np.eye(n, dtype=np.float64)
    precision_dense = np.column_stack(
        [chol_solve(factor, identity[:, k]) for k in range(n)]
    )
    precision_dense = 0.5 * (precision_dense + precision_dense.T)
    eta = precision_dense @ belief.mu
    entries = {
        (i, j): float(precision_dense[i, j])
        for i in range(n)
        for j in range(i + 1)
        if precision_dense[i, j] != 0.0
    }
    return SparseInformationBelief(belief.index, eta, entries)


def from_world(world) -> SparseInformationBelief:
    return from_prior_belief(world.belief)


def _component_state(
    belief: SparseInformationBelief, rows: tuple[int, ...]
) -> GaussianState:
    precision, eta = belief._block(rows)
    factor, _ = chol_psd(precision)
    mu = chol_solve(factor, eta)
    identity = np.eye(len(rows), dtype=np.float64)
    sigma = np.column_stack(
        [chol_solve(factor, identity[:, k]) for k in range(len(rows))]
    )
    sigma = 0.5 * (sigma + sigma.T)
    variables = tuple(belief.index.var(row) for row in rows)
    return GaussianState(VarIndex(variables), mu, sigma)


def _splice_component(
    belief: SparseInformationBelief,
    rows: tuple[int, ...],
    posterior: GaussianState,
) -> SparseInformationBelief:
    local = set(rows)
    precision = {
        key: value
        for key, value in belief.precision.items()
        if key[0] not in local and key[1] not in local
    }
    eta = belief.eta.copy()
    factor, _ = chol_psd(posterior.sigma)
    identity = np.eye(len(rows), dtype=np.float64)
    lambda_block = np.column_stack(
        [chol_solve(factor, identity[:, k]) for k in range(len(rows))]
    )
    lambda_block = 0.5 * (lambda_block + lambda_block.T)
    eta_block = lambda_block @ posterior.mu
    for offset, row in enumerate(rows):
        eta[row] = eta_block[offset]
        for other, source in enumerate(rows):
            if source > row:
                continue
            value = float(lambda_block[offset, other])
            if value != 0.0:
                precision[_canon(row, source)] = value
    return SparseInformationBelief(belief.index, eta, precision)
