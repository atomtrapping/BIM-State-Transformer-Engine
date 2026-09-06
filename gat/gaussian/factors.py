"""Small, dense linear-Gaussian factor graphs with declared evidence lineage.

One joint prior preserves correlations and exact (zero-variance) directions.
Separate factors declare independent noise; correlated measurements belong
in a single block. This is read-only inference, not evidence authentication,
nonlinear pose optimisation, or a canonical-state commit path.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import numpy as np

from gat.geometry.frames import _array, _covariance


def _identifiers(values, label):
    if isinstance(values, str):
        raise ValueError(f"{label} must be a sequence of identifiers")
    result = tuple(values)
    if not result or any(not isinstance(v, str) or not v.strip() for v in result) or len(set(result)) != len(result):
        raise ValueError(f"{label} must be nonempty, distinct identifiers")
    return result


@dataclass(frozen=True)
class FactorVariable:
    id: str
    unit: str

    def __post_init__(self):
        _identifiers((self.id,), "variable id")
        _identifiers((self.unit,), "unit")


@dataclass(frozen=True, eq=False)
class LinearFactor:
    """Observation y = H x + noise over an ordered subset of variables.

    dependencies identify consumed evidence, including upstream derivations.
    Reusing any dependency in another factor or the prior is refused. This
    cannot detect hidden dependence or false provenance declarations.
    """
    id: str
    variables: tuple[str, ...]
    matrix: np.ndarray
    observed: np.ndarray
    noise_covariance: np.ndarray
    source_id: str
    dependencies: tuple[str, ...]
    kind: str = "observation"

    def __post_init__(self):
        _identifiers((self.id,), "factor id")
        _identifiers((self.source_id,), "source id")
        variables = _identifiers(self.variables, "factor variables")
        dependencies = _identifiers(self.dependencies, "factor dependencies")
        if self.kind not in ("observation", "structural_prior", "calibration"):
            raise ValueError("unsupported factor kind")
        observed = np.asarray(self.observed)
        if observed.ndim != 1 or not len(observed):
            raise ValueError("observed must be a nonempty vector")
        observed = _array(observed, observed.shape, "observed")
        matrix = _array(self.matrix, (len(observed), len(variables)), "matrix")
        noise = _covariance(self.noise_covariance, len(observed))
        try:
            np.linalg.cholesky(noise)
        except np.linalg.LinAlgError as exc:
            raise ValueError("factor noise must be positive definite; no implicit jitter") from exc
        for key, value in (("variables", variables), ("dependencies", dependencies),
                           ("observed", observed), ("matrix", matrix), ("noise_covariance", noise)):
            object.__setattr__(self, key, value)

    def record(self):
        return {"id": self.id, "kind": self.kind, "variables": list(self.variables),
                "matrix": self.matrix.tolist(), "observed": self.observed.tolist(),
                "noise_covariance": self.noise_covariance.tolist(), "source_id": self.source_id,
                "dependencies": list(self.dependencies)}


@dataclass(frozen=True, eq=False)
class FactorPosterior:
    mean: np.ndarray
    covariance: np.ndarray
    graph_digest: str
    residuals: tuple[dict, ...]

    def __post_init__(self):
        object.__setattr__(self, "mean", _array(self.mean, self.mean.shape, "mean"))
        object.__setattr__(self, "covariance", _covariance(self.covariance, len(self.mean)))


@dataclass(frozen=True, eq=False)
class GaussianFactorGraph:
    variables: tuple[FactorVariable, ...]
    prior_mean: np.ndarray
    prior_covariance: np.ndarray
    prior_dependencies: tuple[str, ...]
    factors: tuple[LinearFactor, ...] = ()

    def __post_init__(self):
        variables = tuple(self.variables)
        if any(not isinstance(v, FactorVariable) for v in variables):
            raise ValueError("expected FactorVariable records")
        ids = _identifiers(tuple(v.id for v in variables), "graph variables")
        dependencies = _identifiers(self.prior_dependencies, "prior dependencies")
        factors = tuple(self.factors)
        if any(not isinstance(f, LinearFactor) for f in factors):
            raise ValueError("expected LinearFactor records")
        if len({f.id for f in factors}) != len(factors):
            raise ValueError("duplicate factor id")
        consumed = set(dependencies)
        for factor in factors:
            if not set(factor.variables) <= set(ids):
                raise ValueError("factor refers to unknown variables")
            if consumed.intersection(factor.dependencies):
                raise ValueError("evidence dependency reused; combine correlated observations into one block")
            consumed.update(factor.dependencies)
        object.__setattr__(self, "variables", variables)
        object.__setattr__(self, "prior_dependencies", dependencies)
        object.__setattr__(self, "factors", tuple(sorted(factors, key=lambda f: f.id)))
        object.__setattr__(self, "prior_mean", _array(self.prior_mean, (len(ids),), "prior_mean"))
        object.__setattr__(self, "prior_covariance", _covariance(self.prior_covariance, len(ids)))

    def with_factor(self, factor):
        return GaussianFactorGraph(self.variables, self.prior_mean, self.prior_covariance,
                                   self.prior_dependencies, self.factors + (factor,))

    def record(self):
        return {"contract": "gat-linear-factor-graph-v1",
                "variables": [{"id": v.id, "unit": v.unit} for v in self.variables],
                "prior_mean": self.prior_mean.tolist(), "prior_covariance": self.prior_covariance.tolist(),
                "prior_dependencies": list(self.prior_dependencies), "factors": [f.record() for f in self.factors],
                "assumptions": ["separate factor noise blocks are independent of each other and of the prior",
                                "source/dependency declarations are not authenticated", "proper joint prior required; no free gauge solve"]}

    def digest(self):
        encoded = json.dumps(self.record(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode()).hexdigest()

    def solve(self):
        """Whiten and solve by QR in prior latent coordinates, no matrix inverse.

        x = prior_mean + B z, z ~ N(0,I). Zero prior variance remains exact;
        this is not an unanchored gauge direction. R^-1 is obtained by solve.
        Residuals are in-sample diagnostics, never held-out calibration.
        """
        n = len(self.variables)
        if not self.factors:
            return FactorPosterior(self.prior_mean, self.prior_covariance, self.digest(), ())
        # Scale heterogeneous quantities before spectral factorization so a
        # currency/length or metre/millimetre choice does not erase small modes.
        scales = np.sqrt(np.maximum(np.diag(self.prior_covariance), 0))
        divisors = np.where(scales > 0, scales, 1)
        correlation = _covariance(self.prior_covariance / divisors[:, None] / divisors[None, :], n)
        eigenvalues, vectors = np.linalg.eigh(correlation)
        root = scales[:, None] * vectors * np.sqrt(np.maximum(eigenvalues, 0))
        ids = {v.id: i for i, v in enumerate(self.variables)}
        blocks, rhs, observations = [np.eye(n)], [np.zeros(n)], []
        for factor in self.factors:
            matrix = np.zeros((len(factor.observed), n))
            matrix[:, [ids[v] for v in factor.variables]] = factor.matrix
            noise_root = np.linalg.cholesky(factor.noise_covariance)
            blocks.append(np.linalg.solve(noise_root, matrix @ root))
            rhs.append(np.linalg.solve(noise_root, factor.observed - matrix @ self.prior_mean))
            observations.append((factor, matrix, noise_root))
        design, target = np.vstack(blocks), np.concatenate(rhs)
        if not np.isfinite(design).all() or not np.isfinite(target).all():
            raise ValueError("nonfinite whitened system")
        q, r = np.linalg.qr(design, mode="reduced")
        latent = np.linalg.solve(r, q.T @ target)
        posterior_root = root @ np.linalg.solve(r, np.eye(n))
        mean = self.prior_mean + root @ latent
        covariance = posterior_root @ posterior_root.T
        residuals = tuple({"factor_id": f.id, "source_id": f.source_id,
                           "residual": (f.observed - h @ mean).tolist(),
                           "noise_whitened_residual": np.linalg.solve(l, f.observed - h @ mean).tolist(),
                           "role": "in_sample_not_calibration"} for f, h, l in observations)
        return FactorPosterior(mean, covariance, self.digest(), residuals)
