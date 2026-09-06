"""Exact, bounded Bayesian decision design over declared joint hypotheses.

This is value of sample information, not expected free energy. It does not
acquire evidence, update a World, establish a Markov blanket, or certify fit.
Joint outcome tables retain shared calibration and sensor dependencies; the
module never multiplies marginal sensor likelihoods to invent independence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any


METHOD = "gat.finite-decision-voi.v1"


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Hypothesis:
    id: str
    probability: float
    fits: bool
    # Joint latent values for inspection; no independent marginal expansion.
    values: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class Measurement:
    id: str
    cost: float
    availability: str  # AVAILABLE, UNAVAILABLE, UNKNOWN
    permission: str  # PERMITTED, FORBIDDEN, UNKNOWN; declaration, not authorization
    quantity: str
    unit: str


@dataclass(frozen=True)
class JointOutcome:
    hypothesis_id: str
    probability: float  # Conditional on this hypothesis.
    readings: tuple[tuple[str, float], ...]  # Every measurement, including unavailable ones.


@dataclass(frozen=True)
class DecisionModel:
    source_digest: str
    provenance: str
    model_status: str  # SYNTHETIC or DECLARED_UNVALIDATED
    loss_unit: str
    false_fit_loss: float
    false_reject_loss: float
    hypotheses: tuple[Hypothesis, ...]
    measurements: tuple[Measurement, ...]
    outcomes: tuple[JointOutcome, ...]


def _number(value: float, *, probability: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite number")
    if probability and not 0 <= value <= 1:
        raise ValueError("probability must be in [0, 1]")


def _ids(values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values) or any(
        not isinstance(v, str) or not v or len(v) > 128 for v in values
    ):
        raise ValueError("identifiers must be nonempty, unique, and bounded")


def canonical_model(model: DecisionModel) -> dict:
    """Validate before computing; canonicalize records, never change probabilities."""
    if not (1 <= len(model.hypotheses) <= 256 and 1 <= len(model.measurements) <= 16
            and 1 <= len(model.outcomes) <= 4096):
        raise ValueError("finite model exceeds bounds")
    if (not isinstance(model.source_digest, str) or len(model.source_digest) != 71
            or not model.source_digest.startswith("sha256:")
            or any(c not in "0123456789abcdef" for c in model.source_digest[7:])):
        raise ValueError("source_digest must be an exact SHA-256 binding")
    for value in (model.provenance, model.loss_unit):
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise ValueError("provenance and loss unit are required")
    if model.model_status not in ("SYNTHETIC", "DECLARED_UNVALIDATED"):
        raise ValueError("model validity is not established by this module")
    for value in (model.false_fit_loss, model.false_reject_loss):
        _number(value)
        if not 0 < value <= 1e12:
            raise ValueError("decision losses must be positive and bounded")
    hids = tuple(h.id for h in model.hypotheses)
    mids = tuple(m.id for m in model.measurements)
    _ids(hids)
    _ids(mids)
    latent_keys = None
    for h in model.hypotheses:
        _number(h.probability, probability=True)
        if type(h.fits) is not bool or not 1 <= len(h.values) <= 64:
            raise ValueError("hypothesis needs a boolean fit and bounded joint values")
        _ids(tuple(k for k, _ in h.values))
        keys = set(k for k, _ in h.values)
        if latent_keys is not None and keys != latent_keys:
            raise ValueError("hypotheses must describe the same joint variables")
        latent_keys = keys
        for _, value in h.values:
            _number(value)
    if not math.isclose(math.fsum(h.probability for h in model.hypotheses), 1, abs_tol=1e-12, rel_tol=0):
        raise ValueError("prior probabilities must sum to one")
    for m in model.measurements:
        _number(m.cost)
        if not 0 <= m.cost <= 1e12 or m.availability not in ("AVAILABLE", "UNAVAILABLE", "UNKNOWN"):
            raise ValueError("invalid cost or availability")
        if m.permission not in ("PERMITTED", "FORBIDDEN", "UNKNOWN"):
            raise ValueError("invalid permission declaration")
        for label in (m.quantity, m.unit):
            if not isinstance(label, str) or not label or len(label) > 128:
                raise ValueError("measurement quantity and unit are required")
    totals: dict[str, list[float]] = {hid: [] for hid in hids}
    seen = set()
    for outcome in model.outcomes:
        if outcome.hypothesis_id not in totals:
            raise ValueError("unknown outcome hypothesis")
        _number(outcome.probability, probability=True)
        _ids(tuple(k for k, _ in outcome.readings))
        if set(k for k, _ in outcome.readings) != set(mids):
            raise ValueError("joint outcomes must contain every measurement")
        for _, value in outcome.readings:
            _number(value)
        key = outcome.hypothesis_id, tuple(sorted(outcome.readings))
        if key in seen:
            raise ValueError("duplicate joint outcome")
        seen.add(key)
        totals[outcome.hypothesis_id].append(outcome.probability)
    if any(not math.isclose(math.fsum(v), 1, abs_tol=1e-12, rel_tol=0) for v in totals.values()):
        raise ValueError("conditional outcome probabilities must sum to one for every hypothesis")
    result = asdict(model)
    result["hypotheses"] = [dict(asdict(h), values=sorted(h.values)) for h in sorted(model.hypotheses, key=lambda h: h.id)]
    result["measurements"] = [asdict(m) for m in sorted(model.measurements, key=lambda m: m.id)]
    result["outcomes"] = sorted(
        [dict(asdict(o), readings=sorted(o.readings)) for o in model.outcomes],
        key=lambda o: (o["hypothesis_id"], o["readings"]),
    )
    return result


def _decision(p: float, model: DecisionModel) -> dict:
    p = min(1.0, max(0.0, p))  # Absorb probability summation round-off only.
    fit_loss = (1 - p) * model.false_fit_loss
    reject_loss = p * model.false_reject_loss
    # A tie conservatively selects rejection in this declared two-action model.
    return {"p_fits": p, "decision": "FIT" if fit_loss < reject_loss else "REJECT",
            "expected_loss": min(fit_loss, reject_loss)}


def evaluate_measurements(model: DecisionModel, measurement_ids: tuple[str, ...]) -> dict:
    """Enumerate a fixed acquisition set, including the empty/no-measurement set.

    Costs are additive in the declared decision-loss unit. Reading labels are
    exact finite outcomes, not bins automatically inferred from continuous data.
    """
    canonical = canonical_model(model)
    _ids(measurement_ids)
    mids = tuple(sorted(measurement_ids))
    measurements = {m.id: m for m in model.measurements}
    if any(mid not in measurements for mid in mids):
        raise ValueError("unknown measurement")
    if any(measurements[mid].availability != "AVAILABLE" or measurements[mid].permission != "PERMITTED" for mid in mids):
        raise ValueError("measurement is not declared available and permitted")
    hypotheses = {h.id: h for h in model.hypotheses}
    groups: dict[tuple, list[tuple[str, float]]] = {}
    for o in canonical["outcomes"]:
        readings = dict(o["readings"])
        key = tuple((mid, readings[mid]) for mid in mids)
        mass = hypotheses[o["hypothesis_id"]].probability * o["probability"]
        groups.setdefault(key, []).append((o["hypothesis_id"], mass))
    branches = []
    for key, masses in sorted(groups.items()):
        probability = math.fsum(mass for _, mass in masses)
        if probability == 0:
            continue  # Impossible outcomes are not posterior beliefs.
        p_fit = math.fsum(mass for hid, mass in masses if hypotheses[hid].fits) / probability
        posterior = [{"id": hid, "probability": math.fsum(m for h, m in masses if h == hid) / probability}
                     for hid in sorted(hypotheses)]
        branches.append({"readings": key, "probability": probability,
                         "posterior": posterior, **_decision(p_fit, model)})
    baseline = _decision(math.fsum(h.probability for h in sorted(model.hypotheses, key=lambda h: h.id) if h.fits), model)
    after = math.fsum(b["probability"] * b["expected_loss"] for b in branches)
    error = math.fsum(b["probability"] * (1 - b["p_fits"] if b["decision"] == "FIT" else b["p_fits"]) for b in branches)
    brier = math.fsum(b["probability"] * b["p_fits"] * (1 - b["p_fits"]) for b in branches)
    cost = math.fsum(measurements[mid].cost for mid in mids)
    reduction = baseline["expected_loss"] - after
    result = {"schema": METHOD, "model_digest": digest(canonical),
              "source_digest": model.source_digest, "measurement_ids": mids,
              "loss_unit": model.loss_unit, "baseline": baseline,
              "expected_posterior_loss": after, "acquisition_cost": cost,
              "expected_total_loss": after + cost, "expected_loss_reduction": reduction,
              "model_expected_decision_error": error, "model_expected_brier_score": brier,
              "net_value": reduction - cost, "outcomes": branches,
              "physical_action_authorized": False, "field_validation": "NOT_ESTABLISHED"}
    return dict(result, result_digest=digest(result))


def plan_measurements(model: DecisionModel) -> dict:
    """Rank one-step measurements against doing nothing; retain exclusion reasons."""
    canonical = canonical_model(model)
    eligible = [m for m in model.measurements if m.availability == "AVAILABLE" and m.permission == "PERMITTED"]
    options = sorted((evaluate_measurements(model, (m.id,)) for m in eligible),
                     key=lambda r: (-r["net_value"], r["measurement_ids"]))
    tolerance = 1e-12 * max(1, model.false_fit_loss, model.false_reject_loss)
    selected = options[0]["measurement_ids"][0] if options and options[0]["net_value"] > tolerance else None
    result = {"schema": "gat.finite-decision-plan.v1", "method": METHOD,
              "model_digest": digest(canonical), "source_digest": model.source_digest,
              "selection_tolerance": tolerance, "baseline": evaluate_measurements(model, ()),
              "options": options, "selected": selected,
              "excluded": [asdict(m) for m in sorted(model.measurements, key=lambda m: m.id) if m not in eligible],
              "disposition": "RECOMMEND_MEASUREMENT" if selected else "NO_WORTHWHILE_AVAILABLE_MEASUREMENT",
              "physical_action_authorized": False, "field_validation": "NOT_ESTABLISHED"}
    return dict(result, result_digest=digest(result))
