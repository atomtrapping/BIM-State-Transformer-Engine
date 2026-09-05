"""Read-only factor-graph bridge at the opening-fit reference linearization."""
from copy import deepcopy
import math

import numpy as np

from gat.engine.propagate import jacobian_rows
from gat.gaussian.factors import FactorVariable, GaussianFactorGraph
from gat.geometry.opening_fit import assess_opening_fit, assessment_digest, margin_linearization


class OpeningFitGraph:
    """World raw dimensions plus two local pose tangent blocks.

    Factor observations must be expressed in these explicit coordinates.
    Nonlinear factors, frame rebasing and state commitment are not supported.
    ``prior_dependencies`` must declare every source already in the joint
    prior, including dimension/pose evidence and shared calibration inputs.
    """

    def __init__(self, world, frames, binding, *, prior_dependencies, **assessment_options):
        self._reference = assess_opening_fit(world, frames, binding, **assessment_options)
        self._n = len(world.belief.index)
        pose = np.asarray(self._reference["pose"]["covariance"])
        cross = np.asarray(self._reference["pose"]["raw_pose_cross_covariance"])
        dimensions = tuple(FactorVariable(v.qualified, world.module.slot(v).unit.value) for v in world.belief.index.vars)
        components = (("tx", "m"), ("ty", "m"), ("tz", "m"), ("rx", "rad"), ("ry", "rad"), ("rz", "rad"))
        poses = tuple(FactorVariable(f"pose:{frame}:{component}", unit)
                      for frame in (binding.opening_frame, binding.assembly_frame) for component, unit in components)
        self.graph = GaussianFactorGraph(dimensions + poses, np.r_[world.belief.mu, np.zeros(12)],
                                        np.block([[world.belief.sigma, cross], [cross.T, pose]]), prior_dependencies)
        self._dimension_rows, dimension_means = jacobian_rows(world.binding, world.belief, binding.dimensions)
        self._margin_means, local_rows = margin_linearization(dimension_means, frames.between(binding.assembly_frame, binding.opening_frame))
        projection = np.zeros((17, self._n + 12))
        projection[:5, :self._n] = self._dimension_rows
        projection[5:, self._n:] = np.eye(12)
        self._margin_rows = local_rows @ projection

    def predict(self, factors=()):
        graph = self.graph
        for factor in factors:
            graph = graph.with_factor(factor)
        posterior = graph.solve()
        change = posterior.mean - graph.prior_mean
        means = self._margin_means + self._margin_rows @ change
        covariance = self._margin_rows @ posterior.covariance @ self._margin_rows.T
        covariance = (covariance + covariance.T) / 2
        report = deepcopy(self._reference)
        sigmas = np.sqrt(np.maximum(np.diag(covariance), 0))
        required, confidence = report["required_clearance_m"], report["confidence"]
        for risk, mean, sigma in zip(report["risks"], means, sigmas):
            probability = float(mean < required) if sigma == 0 else 0.5 * math.erfc((mean - required)/(sigma * math.sqrt(2)))
            risk.update(mean_m=float(mean), sigma_m=float(sigma), p_violates=probability)
        lower = max(r["p_violates"] for r in report["risks"])
        upper = min(1.0, sum(r["p_violates"] for r in report["risks"]))
        report.update(margin_covariance_m2=covariance.tolist(), p_any_violation_lower=lower, p_any_violation_upper=upper,
                      model_prediction="SATISFIED" if upper <= 1-confidence else "VIOLATED" if lower >= confidence else "UNRESOLVED",
                      deterministic_nominal_fit=bool(np.all(means >= required)))
        report["binding"]["dimensions_m"] = (np.asarray(report["binding"]["dimensions_m"]) + self._dimension_rows @ change[:self._n]).tolist()
        if min(report["binding"]["dimensions_m"]) <= 0:
            raise ValueError("conditioned linear dimensions must remain positive")
        report["pose"]["covariance"] = posterior.covariance[self._n:, self._n:].tolist()
        report["pose"]["raw_pose_cross_covariance"] = posterior.covariance[:self._n, self._n:].tolist()
        report["pose"]["mean_tangent"] = posterior.mean[self._n:].tolist()
        report["inference"] = {"contract": "gat-opening-factor-bridge-v1", "graph_digest": graph.digest(),
                               "graph": graph.record(), "posterior_mean": posterior.mean.tolist(),
                               "posterior_covariance": posterior.covariance.tolist(), "residuals": list(posterior.residuals),
                               "reference_assessment_digest": self._reference["assessment_digest"],
                               "reference_dimensions_m": self._reference["binding"]["dimensions_m"],
                               "geometry_evaluation": "fixed_first_order_linearization",
                               "canonical_state_committed": False}
        report["limitations"].append("factor inference uses the fixed reference frames and first-order Jacobian; pose means are local tangent corrections, not rebased placements")
        report["limitations"].append("factor residuals are in-sample diagnostics, not independent calibration or evidence receipts")
        report["assessment_digest"] = assessment_digest(report)
        return report
