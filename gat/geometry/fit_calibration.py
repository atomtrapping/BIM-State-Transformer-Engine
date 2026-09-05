"""Held-out predictive checks. Provenance is declared, not authenticated here."""
from __future__ import annotations

import math
from statistics import NormalDist

from gat.geometry.opening_fit import CONTRACT, assessment_digest


def evaluate_held_out(assessments, measurements, *, fitting_source_ids, levels=(0.5, 0.8, 0.95)):
    """Evaluate scalar corner clearances in metres without updating a world.

    Measurement records require assessment_digest, risk_id, sample_id,
    source_id, calibration_version, value_m and independent_noise_sigma_m.
    The observation must measure that exact corner/edge functional, not a
    minimum across corners. Independent measurement noise is added to the
    predicted variance. Source declarations cannot prove independence.
    """
    levels = tuple(levels)
    if not levels or any(not math.isfinite(x) or not 0 < x < 1 for x in levels) or len(set(levels)) != len(levels):
        raise ValueError("coverage levels must be distinct probabilities in (0, 1)")
    fitting = set(fitting_source_ids)
    records = tuple(assessments)
    for record in records:
        if record.get("contract") != CONTRACT or record.get("assessment_digest") != assessment_digest(record):
            raise ValueError("unsupported or altered assessment")
    lookup = {r["assessment_digest"]: r for r in records}
    if len(lookup) != len(records):
        raise ValueError("duplicate assessment")
    residuals, seen, groups = [], set(), {}
    for measurement in measurements:
        for field in ("sample_id", "source_id", "calibration_version"):
            if not isinstance(measurement[field], str) or not measurement[field].strip():
                raise ValueError(f"{field} must be nonempty")
        if measurement["source_id"] in fitting:
            raise ValueError("held-out source was used for fitting")
        if measurement["sample_id"] in seen:
            raise ValueError("duplicate measurement sample")
        seen.add(measurement["sample_id"])
        assessment = lookup[measurement["assessment_digest"]]
        risk = next((r for r in assessment["risks"] if r["id"] == measurement["risk_id"]), None)
        if risk is None:
            raise ValueError("unknown corner risk")
        value, noise = measurement["value_m"], measurement["independent_noise_sigma_m"]
        if not math.isfinite(value) or not math.isfinite(noise) or noise < 0:
            raise ValueError("measurement must be finite with nonnegative noise")
        residual = value - risk["mean_m"]
        sigma = math.hypot(risk["sigma_m"], noise)
        if sigma == 0:
            raise ValueError("standardised residual requires positive predictive observation sigma")
        z = residual / sigma
        if not math.isfinite(z):
            raise ValueError("standardised residual is not finite")
        key = (risk["quantity_class"], risk["frame_id"], assessment["frame_representation_digest"], measurement["calibration_version"])
        group = groups.setdefault(key, [])
        group.append(z)
        residuals.append({**measurement, "residual_m": residual, "predictive_observation_sigma_m": sigma,
                          "standardised_residual": z})
    summaries = []
    for (quantity, frame, representation, version), values in sorted(groups.items()):
        summaries.append({"quantity_class": quantity, "frame_id": frame, "frame_representation_digest": representation,
                          "calibration_version": version, "count": len(values),
                          "coverage": [{"nominal": level, "observed": sum(abs(z) <= NormalDist().inv_cdf((1 + level) / 2)
                                                       for z in values) / len(values)} for level in levels]})
    return {"contract": "gat-fit-held-out-v1", "status": "NO_MEASUREMENTS" if not residuals else "DESCRIPTIVE_EVALUATION",
            "groups": summaries, "residuals": residuals, "independence": "declared by caller; not verified",
            "limitations": ["correlated samples are not independent trials", "no coverage confidence intervals or acceptance authority",
                            "calibration provenance must be independently reviewed"]}
