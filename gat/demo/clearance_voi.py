"""Synthetic clearance decision design: python -m gat.demo.clearance_voi.

Writes a self-contained model and analysis to stdout. Every likelihood and
loss is a fixture assumption, not calibration from independent observations.
"""
from __future__ import annotations

import itertools
import json
import math

from gat.engine.value_of_information import (
    DecisionModel, Hypothesis, JointOutcome, Measurement, canonical_model,
    digest, evaluate_measurements, plan_measurements,
)


SOURCE = {
    "schema": "gat.synthetic-clearance-voi-source.v1",
    "frame": "local-opening", "length_unit": "m",
    "opening_widths": [2.0, 2.02], "equipment_width": 2.01,
    "shared_instrument_offsets": [0.0, 0.02],
    "unrelated_panel_offsets": [-0.1, 0.1],
    "prior": "uniform over the eight explicitly enumerated joint states",
    "fit": "opening_width >= equipment_width",
    "readings": "opening survey reports width + shared instrument offset; calibration reports that offset; panel survey reports unrelated panel offset",
    "likelihood": "deterministic finite readings conditional on joint state; synthetic only",
}


def fixture() -> DecisionModel:
    hypotheses, outcomes = [], []
    for index, (width, bias, panel) in enumerate(itertools.product(
        SOURCE["opening_widths"], SOURCE["shared_instrument_offsets"], SOURCE["unrelated_panel_offsets"],
    )):
        hid = f"H-{index}"
        hypotheses.append(Hypothesis(hid, 0.125, width >= SOURCE["equipment_width"], (
            ("opening_width_m", width), ("equipment_width_m", SOURCE["equipment_width"]),
            ("instrument_offset_m", bias), ("panel_offset_m", panel),
        )))
        outcomes.append(JointOutcome(hid, 1.0, (
            ("opening", round(width + bias, 2)), ("calibration", bias), ("panel", panel),
        )))
    return DecisionModel(
        digest(SOURCE), "Explicit generated eight-state model; no independent survey evidence.",
        "SYNTHETIC", "declared decision-loss units", 10.0, 2.0,
        tuple(hypotheses), (
            Measurement("opening", 0.1, "AVAILABLE", "PERMITTED", "indicated opening width", "m"),
            Measurement("calibration", 0.15, "AVAILABLE", "PERMITTED", "shared instrument offset", "m"),
            Measurement("panel", 0.01, "AVAILABLE", "PERMITTED", "unrelated panel offset", "m"),
        ), tuple(outcomes),
    )


def experiment() -> dict:
    model = fixture()
    plan = plan_measurements(model)
    # This naive comparator uses predicted reading variance, in common metres.
    # It is deliberately not a general cross-unit sensor ranking rule.
    prior = {h.id: h.probability for h in model.hypotheses}
    variances = {}
    for m in model.measurements:
        readings = [(prior[o.hypothesis_id] * o.probability, dict(o.readings)[m.id]) for o in model.outcomes]
        mean = math.fsum(p * v for p, v in readings)
        variances[m.id] = math.fsum(p * (v - mean) ** 2 for p, v in readings)
    cheapest = min(model.measurements, key=lambda m: (m.cost, m.id)).id
    largest = min(variances, key=lambda mid: (-variances[mid], mid))
    selected = () if plan["selected"] is None else (plan["selected"],)
    result = {
        "schema": "gat.synthetic-clearance-voi-experiment.v1",
        "source": SOURCE, "model": canonical_model(model), "plan": plan,
        "predicted_reading_variance_m2": variances,
        "comparisons": {name: evaluate_measurements(model, mids) for name, mids in (
            ("no_measurement", ()), ("one_step_voi", selected), ("cheapest_first", (cheapest,)),
            ("largest_uncertainty_first", (largest,)),
            ("measure_everything", tuple(m.id for m in model.measurements)),
            ("opening_and_calibration", ("opening", "calibration")),
        )},
        "evaluation_scope": "Exact expectations under the synthetic design model; not held-out accuracy or uncertainty calibration.",
        "independent_evaluation": "NOT_AVAILABLE",
    }
    return dict(result, artifact_digest=digest(result))


if __name__ == "__main__":
    print(json.dumps(experiment(), indent=2, sort_keys=True, allow_nan=False))
