"""Bounded rectangular aperture fit; first-order prediction, never field approval.

The aperture is centred on its frame origin in local X/Z; local Y is the
unbounded passage direction. The assembly is a centred box. All eight box
corners must lie inside all four aperture half-planes. This does not test
an insertion trajectory, wall depth, contacts, or arbitrary IFC geometry.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import hashlib
import json
import math

import numpy as np

from gat.engine.propagate import jacobian_rows
from gat.geometry.frames import FrameGraph, POSE_CONVENTION, _array, _covariance, _skew
from gat.ids import VarId
from gat.ir.core import Unit


CONTRACT = "gat-opening-fit-v1"
SIGNS = tuple(product((-1, 1), repeat=3))
EDGES = (("left", 0, 1, 0), ("right", 0, -1, 0),
         ("bottom", 2, 1, 1), ("top", 2, -1, 1))


def assessment_digest(record):
    """Representation identity, including assumptions; not an evidence receipt."""
    payload = {k: v for k, v in record.items() if k != "assessment_digest"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class OpeningFitBinding:
    """Explicit semantic association; dimensions in canonical metres.

    Variable order: opening width/height, assembly X/Y/Z extents. Frame
    origins are geometric centres, not the IR's corner-origin placements.
    The caller must supply this association; names/proximity never infer it.
    """
    opening_frame: str
    assembly_frame: str
    dimensions: tuple[VarId, ...]

    def __post_init__(self):
        dimensions = tuple(self.dimensions)
        if len(dimensions) != 5 or any(not isinstance(v, VarId) for v in dimensions):
            raise ValueError("five dimension VarIds are required")
        if len(set(dimensions)) != 5:
            raise ValueError("dimension variables must be distinct")
        if dimensions[0].entity != dimensions[1].entity or len({v.entity for v in dimensions[2:]}) != 1:
            raise ValueError("dimensions must belong to one opening and one assembly")
        if dimensions[0].entity == dimensions[2].entity:
            raise ValueError("opening and assembly must be distinct entities")
        object.__setattr__(self, "dimensions", dimensions)


def margin_linearization(dimensions_m, opening_from_assembly):
    """Return 32 corner margins and Jacobian in 17 declared coordinates.

    Order: five dimensions, opening right-local pose (6), assembly pose (6).
    Retaining every half-plane avoids differentiating min/abs at ties.
    """
    d = _array(dimensions_m, (5,), "dimensions_m")
    if np.any(d <= 0):
        raise ValueError("nominal dimensions must be positive")
    transform = opening_from_assembly
    means, rows = [], []
    for signs in SIGNS:
        local = np.asarray(signs) * d[2:] / 2
        point = transform.point(local)
        point_jacobian = np.zeros((3, 17))
        point_jacobian[:, 2:5] = transform.rotation @ np.diag(np.asarray(signs) / 2)
        point_jacobian[:, 5:8] = -np.eye(3)
        point_jacobian[:, 8:11] = _skew(point)
        point_jacobian[:, 11:14] = transform.rotation
        point_jacobian[:, 14:17] = -transform.rotation @ _skew(local)
        for _, axis, sign, dimension in EDGES:
            means.append(d[dimension] / 2 + sign * point[axis])
            row = sign * point_jacobian[axis].copy()
            row[dimension] += 0.5
            rows.append(row)
    return np.asarray(means), np.asarray(rows)


def assess_opening_fit(world, frames: FrameGraph, binding: OpeningFitBinding, *,
                       pose_covariance, raw_pose_cross_covariance,
                       assumption_id: str, required_clearance_m=0.0, confidence=0.95):
    """Push the world's dimensional belief plus an explicit pose sidecar.

    pose_covariance: 12x12, opening then assembly right-local tangent poses.
    raw_pose_cross_covariance: n_raw x 12, in world.belief.index order.
    Both are mandatory: zero blocks explicitly declare independence/exactness.
    Sidecar poses are not canonical IR variables or calibrated evidence.
    """
    if not isinstance(assumption_id, str) or not assumption_id.strip():
        raise ValueError("assumption_id must identify the supplied pose assumptions")
    if not math.isfinite(required_clearance_m) or required_clearance_m < 0:
        raise ValueError("required clearance must be finite and nonnegative")
    if not math.isfinite(confidence) or not 0.5 < confidence < 1:
        raise ValueError("confidence must be between 0.5 and 1")
    for var in binding.dimensions:
        if world.module.slot(var).unit is not Unit.M:
            raise ValueError("bound dimensions must use canonical metres")
    transform = frames.between(binding.assembly_frame, binding.opening_frame)
    dimension_rows, dimensions = jacobian_rows(world.binding, world.belief, binding.dimensions)
    n = len(world.belief.index)
    pose = _covariance(pose_covariance, 12)
    cross = _array(raw_pose_cross_covariance, (n, 12), "raw_pose_cross_covariance")
    joint = _covariance(np.block([[world.belief.sigma, cross], [cross.T, pose]]), n + 12)
    projection = np.zeros((17, n + 12))
    projection[:5, :n] = dimension_rows
    projection[5:, n:] = np.eye(12)
    means, local_jacobian = margin_linearization(dimensions, transform)
    jacobian = local_jacobian @ projection
    covariance = jacobian @ joint @ jacobian.T
    covariance = (covariance + covariance.T) / 2
    sigmas = np.sqrt(np.maximum(np.diag(covariance), 0))
    risks = []
    opening_id, assembly_id = binding.dimensions[0].entity, binding.dimensions[2].entity
    for i, (mean, sigma) in enumerate(zip(means, sigmas)):
        probability = (float(mean < required_clearance_m) if sigma == 0 else
                       0.5 * math.erfc((mean - required_clearance_m) / (sigma * math.sqrt(2))))
        risks.append({"id": f"corner-{i // 4}:{EDGES[i % 4][0]}",
                      "quantity_class": "corner_clearance", "frame_id": binding.opening_frame,
                      "mean_m": float(mean), "sigma_m": float(sigma), "p_violates": probability})
    lower = max(r["p_violates"] for r in risks)
    upper = min(1.0, sum(r["p_violates"] for r in risks))
    prediction = "SATISFIED" if upper <= 1 - confidence else "VIOLATED" if lower >= confidence else "UNRESOLVED"
    record = {
        "contract": CONTRACT, "world_digest": world.digest(),
        "frame_representation_digest": frames.representation_digest(),
        "subjects": [{"ifc_class": e.ifc_class, "global_id": e.global_id} for e in (opening_id, assembly_id)],
        "frames": [{"id": f.frame_id, "parent_id": f.parent_id, "unit": f.unit.value,
                    "rotation": f.to_parent.rotation.tolist(), "translation_m": f.to_parent.translation_m.tolist()}
                   for _, f in sorted(frames.frames.items())],
        "binding": {"opening_frame": binding.opening_frame, "assembly_frame": binding.assembly_frame,
                    "dimensions": [v.qualified for v in binding.dimensions], "dimensions_m": dimensions.tolist()},
        "pose": {"convention": POSE_CONVENTION, "order": [binding.opening_frame, binding.assembly_frame],
                 "covariance": pose.tolist(), "raw_pose_cross_covariance": cross.tolist(),
                 "raw_order": [v.qualified for v in world.belief.index.vars], "assumption_id": assumption_id,
                 "canonical_placement_uncertainty": False},
        "required_clearance_m": required_clearance_m, "confidence": confidence,
        "risks": risks, "margin_covariance_m2": covariance.tolist(),
        "p_any_violation_lower": lower, "p_any_violation_upper": upper,
        "model_prediction": prediction, "deterministic_nominal_fit": bool(np.all(means >= required_clearance_m)),
        "calibration_status": "UNVALIDATED", "acceptance": "REQUEST_EVIDENCE",
        "limitations": ["first-order local Gaussian approximation", "centred rectangular aperture and box only",
                        "no wall-depth, insertion-path or interference assessment", "no independent measurements supplied",
                        "probability bounds may be conservative; corner events are not independent"],
    }
    record["assessment_digest"] = assessment_digest(record)
    return record
