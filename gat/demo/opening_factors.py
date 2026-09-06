"""Synthetic joint inference, prediction and Claude report consumer rendezvous."""
from pathlib import Path
import json
import sys

import numpy as np

from gat.demo.opening_fit import synthetic_case
from gat.gaussian.factors import LinearFactor
from gat.geometry.opening_factors import OpeningFitGraph
from gat.geometry.fit_calibration import evaluate_held_out
from gat.report import decode_response, render_html


def run(output):
    world, frames, binding = synthetic_case()
    original = world.digest()
    bridge = OpeningFitGraph(world, frames, binding, prior_dependencies=("synthetic-dimensions-v1", "synthetic-pose-v1"),
                             pose_covariance=np.eye(12)*1e-6, raw_pose_cross_covariance=np.zeros((len(world.belief.index), 12)),
                             assumption_id="synthetic-1mm-1mrad", inputs="synthetic", required_clearance_m=0.01)
    prior = bridge.predict()
    observation = LinearFactor("opening-width-check", (binding.dimensions[0].qualified,), [[1]], [1.098], [[0.0005**2]],
                               "synthetic-width-instrument", ("synthetic-width-observation-1",))
    posterior = bridge.predict((observation,))
    assert posterior["binding"]["dimensions_m"][0] < prior["binding"]["dimensions_m"][0]
    assert posterior["acceptance"] == "REQUEST_EVIDENCE"
    assert posterior["calibration_status"] == "UNVALIDATED"
    assert original == world.digest()
    risk = posterior["risks"][0]
    checks = [{"sample_id": f"synthetic-heldout-{i}", "source_id": "synthetic-independent-checks", "calibration_version": "synthetic-v1",
               "assessment_digest": posterior["assessment_digest"], "risk_id": risk["id"],
               "value_m": risk["mean_m"] + z * float(np.hypot(risk["sigma_m"], 0.001)), "independent_noise_sigma_m": 0.001}
              for i, z in enumerate((0, 1, 3))]
    evaluation = evaluate_held_out([posterior], checks, fitting_source_ids=[])
    evaluation["limitations"].insert(0, "SYNTHETIC HARNESS EXAMPLE: invented observations and checks; not field calibration.")
    empty = evaluate_held_out([posterior], [], fitting_source_ids=[])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, record in (("prior", prior), ("posterior", posterior), ("synthetic-coverage", evaluation), ("no-measurements", empty)):
        (output / f"{name}.json").write_text(json.dumps(record, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        (output / f"{name}.html").write_text(render_html(decode_response(record)), encoding="utf-8")
    print("Factor inference and Claude reports: prior/posterior, synthetic coverage and empty state emitted; world unchanged; REQUEST_EVIDENCE")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "opening-factor-out")
