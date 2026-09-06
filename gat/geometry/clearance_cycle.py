"""Continuous linear-Gaussian width-gate design and evidence-bound updates.

The gate is (opening width - assembly width)/2 - required clearance >= 0.
Frames must be exactly aligned and X-centred under an explicit exact-pose
assumption. This is not a full aperture, trajectory, or field fit verdict.
"""
from dataclasses import dataclass
import hashlib
import math
import re
from statistics import NormalDist

import numpy as np

from gat.engine.transform import ObserveLinearized
from gat.engine.value_of_information import digest
from gat.ir.core import Unit
from gat.ids import VarId


METHOD = "gat-continuous-width-voi-v1"


def _epoch(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,20}", value) is None:
        raise ValueError("epoch must be a decimal UTC Unix nanosecond string")


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected lowercase SHA-256 digest")


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected finite number")


@dataclass(frozen=True)
class WidthGate:
    required_clearance_m: float
    false_accept_loss: float
    false_reject_loss: float
    loss_unit: str
    exact_pose_assumption: str

    def __post_init__(self):
        for v in (self.required_clearance_m, self.false_accept_loss, self.false_reject_loss):
            _finite(v)
        if self.required_clearance_m < 0 or not 0 < self.false_accept_loss <= 1e12 or not 0 < self.false_reject_loss <= 1e12:
            raise ValueError("invalid clearance or losses")
        if not self.loss_unit or not self.exact_pose_assumption:
            raise ValueError("loss unit and exact-pose assumption are required")


@dataclass(frozen=True)
class LinearSensor:
    id: str
    terms: tuple[tuple[VarId, float], ...]
    offset_m: float
    noise_sigma_m: float
    cost: float
    calibration_digest: str
    available: bool = True
    permitted: bool = True

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id or len(self.id) > 128:
            raise ValueError("sensor identity required")
        if not self.terms or len(set(v for v, _ in self.terms)) != len(self.terms):
            raise ValueError("unique sensor terms required")
        for _, coefficient in self.terms:
            _finite(coefficient)
            if abs(coefficient) > 1e6:
                raise ValueError("sensor coefficient exceeds v1 bound")
        for value in (self.offset_m, self.noise_sigma_m, self.cost):
            _finite(value)
        if not 1e-12 <= self.noise_sigma_m <= 1e6 or not 0 <= self.cost <= 1e12:
            raise ValueError("positive sensor noise and nonnegative bounded cost required")
        if type(self.available) is not bool or type(self.permitted) is not bool:
            raise ValueError("availability and permission require explicit booleans")
        _sha(self.calibration_digest)


def _row(world, terms):
    row = np.zeros(world.binding.n_raw)
    order = world.belief.index.vars
    for var, coefficient in terms:
        if var not in order or world.module.entities[var.entity].slots[var.quantity].unit != Unit.M:
            raise ValueError("v1 requires raw metre quantities")
        row[order.index(var)] += coefficient
    if not np.any(row):
        raise ValueError("nonzero affine row required")
    return row


def _probability(mean, variance):
    if variance <= 0:
        return float(mean >= 0)
    return 0.5 * math.erfc(-mean / math.sqrt(2 * variance))


def _decision(mean, variance, gate):
    p = _probability(mean, variance)
    accept, reject = (1 - p) * gate.false_accept_loss, p * gate.false_reject_loss
    return {"p_width_gate": p, "decision": "ACCEPT_WIDTH_GATE" if accept < reject else "REJECT_WIDTH_GATE",
            "expected_loss": min(accept, reject), "margin_mean_m": mean, "margin_sigma_m": math.sqrt(max(variance, 0))}


def expected_posterior_loss(mean, posterior_variance, mean_spread, gate):
    """Deterministic 1D Gaussian integration, split at the decision boundary.

    Successive Gauss-Legendre rules provide an error estimate, not a rigorous
    quadrature bound. A separate Gaussian-tail loss bound is recorded.
    """
    if mean_spread == 0:
        return _decision(mean, posterior_variance, gate)["expected_loss"], 0.0
    sigma = math.sqrt(max(posterior_variance, 0))
    threshold = NormalDist().inv_cdf(gate.false_accept_loss / (gate.false_accept_loss + gate.false_reject_loss))
    breaks = sorted({-10., 10., *[float(np.clip((sigma * x - mean) / mean_spread, -10, 10)) for x in (-8, -4, 0, 4, 8, threshold)]})
    previous = None
    tail = math.erfc(10 / math.sqrt(2)) * max(gate.false_accept_loss, gate.false_reject_loss)
    tolerance = 1e-10 * max(1, gate.false_accept_loss, gate.false_reject_loss)
    for count in (32, 64, 128, 256):
        nodes, weights = np.polynomial.legendre.leggauss(count)
        pieces = []
        for left, right in zip(breaks, breaks[1:]):
            z = (nodes + 1) * (right - left) / 2 + left
            values = [_decision(mean + mean_spread * float(v), posterior_variance, gate)["expected_loss"] * math.exp(-float(v) ** 2 / 2) / math.sqrt(2 * math.pi) for v in z]
            pieces.append(float(weights @ values) * (right - left) / 2)
        result = math.fsum(pieces)
        if previous is not None and abs(result - previous) <= tolerance:
            return result, abs(result - previous) + tail
        previous = result
    raise ValueError("expected-loss quadrature did not converge")


def plan_width_measurements(world, frames, binding, gate, sensors, *, epoch_ns):
    _epoch(epoch_ns)
    sensors = tuple(sensors)
    if len(sensors) > 32 or len(set(s.id for s in sensors)) != len(sensors):
        raise ValueError("up to 32 unique sensors required")
    relative = frames.between(binding.assembly_frame, binding.opening_frame)
    if not np.allclose(relative.rotation, np.eye(3), atol=1e-12, rtol=0) or abs(relative.translation_m[0]) > 1e-12:
        raise ValueError("width gate requires aligned, X-centred frames")
    a = _row(world, ((binding.dimensions[0], 0.5), (binding.dimensions[2], -0.5)))
    if any(world.belief.mu[world.belief.index.vars.index(v)] <= 0 for v in (binding.dimensions[0], binding.dimensions[2])):
        raise ValueError("nominal widths must be positive")
    mean = float(a @ world.belief.mu) - gate.required_clearance_m
    variance = float(a @ world.belief.sigma @ a)
    if not math.isfinite(mean) or not math.isfinite(variance) or variance < 0:
        raise ValueError("invalid width margin moments")
    baseline = _decision(mean, variance, gate)
    options, excluded = [], []
    for sensor in sorted(sensors, key=lambda s: s.id):
        h = _row(world, sensor.terms)
        description = {"id": sensor.id, "row": h.tolist(), "offset_m": sensor.offset_m,
                       "noise_sigma_m": sensor.noise_sigma_m, "cost": sensor.cost,
                       "calibration_digest": sensor.calibration_digest,
                       "available": sensor.available, "permitted": sensor.permitted}
        if not sensor.available or not sensor.permitted:
            excluded.append(description)
            continue
        innovation = float(h @ world.belief.sigma @ h) + sensor.noise_sigma_m ** 2
        covariance = float(a @ world.belief.sigma @ h)
        if not math.isfinite(innovation) or not math.isfinite(covariance) or innovation <= 0:
            raise ValueError("invalid predictive sensor moments")
        gain = covariance / innovation
        residual = a - gain * h
        posterior_variance = float(residual @ world.belief.sigma @ residual) + gain ** 2 * sensor.noise_sigma_m ** 2
        spread = abs(covariance) / math.sqrt(innovation)
        loss, error = expected_posterior_loss(mean, posterior_variance, spread, gate)
        predicted = float(h @ world.belief.mu) + sensor.offset_m
        options.append({**description, "predicted_reading_m": predicted,
                        "predictive_sigma_m": math.sqrt(innovation), "margin_gain": gain,
                        "posterior_margin_variance_m2": posterior_variance,
                        "expected_posterior_loss": loss, "numerical_error_estimate": error,
                        "net_value": baseline["expected_loss"] - loss - sensor.cost,
                        "illustrative_outcomes": [{"predictive_z": z, "reading_m": predicted + z * math.sqrt(innovation),
                            **_decision(mean + gain * z * math.sqrt(innovation), posterior_variance, gate)} for z in (-2, 0, 2)]})
    options.sort(key=lambda o: (-o["net_value"], o["id"]))
    tolerance = 1e-9 * max(1, gate.false_accept_loss, gate.false_reject_loss)
    selected = options[0]["id"] if options and options[0]["net_value"] > tolerance + options[0]["numerical_error_estimate"] else None
    result = {"schema": METHOD, "world_digest": world.digest(), "belief_digest": world.belief.digest(),
              "raw_order": [v.qualified for v in world.belief.index.vars],
              "frames_digest": frames.representation_digest(), "epoch_ns": epoch_ns, "clock_basis": "UTC_UNIX_NS",
              "temporal_scope": "AT_DECLARED_EPOCH_ONLY", "pose_assumption": gate.exact_pose_assumption,
              "opening": binding.dimensions[0].entity.global_id, "assembly": binding.dimensions[2].entity.global_id,
              "loss_unit": gate.loss_unit, "false_accept_loss": gate.false_accept_loss, "false_reject_loss": gate.false_reject_loss,
              "required_clearance_m": gate.required_clearance_m, "margin_row": a.tolist(),
              "baseline": baseline, "options": options, "excluded": excluded, "selected": selected,
              "scope": "ALIGNED_CENTRED_WIDTH_GATE_ONLY", "full_fit_certified": False,
              "field_validation": "NOT_ESTABLISHED", "selection_tolerance": tolerance}
    return {**result, "plan_digest": digest(result)}


def observe_planned(session, plan, *, sensor_id, value_m, epoch_ns, source_bytes, evidence_kind):
    """Condition through GAT's verified executor; caller preserves original bytes.

    Evidence may be a recorded reading or an explicitly synthetic fixture. This
    function does not authenticate a sensor or infer a timestamp from raw bytes.
    """
    if digest({k: v for k, v in plan.items() if k != "plan_digest"}) != plan.get("plan_digest"):
        raise ValueError("plan digest mismatch")
    _epoch(epoch_ns)
    _finite(value_m)
    if epoch_ns != plan["epoch_ns"] or session.world.digest() != plan["world_digest"]:
        raise ValueError("observation is stale or belongs to a different state epoch")
    if evidence_kind not in ("SYNTHETIC", "RECORDED_UNVALIDATED") or not isinstance(source_bytes, bytes) or not 0 < len(source_bytes) <= 8 * 1024 * 1024:
        raise ValueError("bounded evidence bytes and explicit evidence kind required")
    options = [o for o in plan["options"] if o["id"] == sensor_id]
    if len(options) != 1:
        raise ValueError("sensor must be an eligible planned option")
    option = options[0]
    world = session.world
    row = np.array(option["row"])
    raw_order = world.belief.index.vars
    evidence_digest = hashlib.sha256(source_bytes).hexdigest()
    if any(event.kind == "transition" and event.provenance.get("evidence_digest") == evidence_digest
           for event in session.ledger.events):
        raise ValueError("evidence bytes already conditioned in this session ledger")
    operation = ObserveLinearized(row, option["predicted_reading_m"], value_m,
        option["noise_sigma_m"], tuple(v for v, coefficient in zip(raw_order, row) if coefficient != 0),
        raw_order, world.belief.digest(), world.digest(), evidence_digest, sensor_id)
    session.run(operation, provenance={"plan_digest": plan["plan_digest"], "epoch_ns": epoch_ns,
        "clock_basis": "UTC_UNIX_NS", "evidence_digest": evidence_digest, "evidence_kind": evidence_kind,
        "calibration_digest": option["calibration_digest"], "value_m": value_m})
    a = np.array(plan["margin_row"])
    actual_mean = float(a @ session.world.belief.mu) - plan["required_clearance_m"]
    actual_variance = float(a @ session.world.belief.sigma @ a)
    return {"prior_world_digest": world.digest(), "posterior_world_digest": session.world.digest(),
            "plan_digest": plan["plan_digest"], "evidence_digest": evidence_digest,
            "evidence_kind": evidence_kind, "epoch_ns": epoch_ns, "ledger_head": session.ledger.head,
            "margin_mean_m": actual_mean, "margin_variance_m2": actual_variance,
            "predicted_posterior_variance_m2": option["posterior_margin_variance_m2"],
            "field_validation": "NOT_ESTABLISHED"}
