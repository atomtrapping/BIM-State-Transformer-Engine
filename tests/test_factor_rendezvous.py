"""Live engine-to-Claude-report contract, not only a frozen JSON fixture."""
from pathlib import Path
import copy
import tempfile
import unittest

import numpy as np

from gat.demo.opening_fit import synthetic_case
from gat.demo.opening_factors import run
from gat.gaussian.factors import LinearFactor
from gat.geometry.opening_fit import assess_opening_fit, assessment_digest
from gat.geometry.opening_factors import OpeningFitGraph
from gat.geometry.fit_calibration import evaluate_held_out
from gat.report import decode_response, render_html


class FactorRendezvousTests(unittest.TestCase):
    def setUp(self):
        self.world, self.frames, self.binding = synthetic_case()
        self.options = dict(pose_covariance=np.eye(12)*1e-6, raw_pose_cross_covariance=np.zeros((5,12)),
                            assumption_id="synthetic", inputs="synthetic", required_clearance_m=0.01)
        self.bridge = OpeningFitGraph(self.world, self.frames, self.binding, prior_dependencies=("prior-source",), **self.options)

    def measurement(self):
        return LinearFactor("width", (self.binding.dimensions[0].qualified,), [[1]], [1.098], [[0.0005**2]],
                            "survey-width", ("width-observation",))

    def test_prior_graph_reproduces_existing_fit(self):
        original = assess_opening_fit(self.world, self.frames, self.binding, **self.options)
        result = self.bridge.predict()
        np.testing.assert_allclose(result["margin_covariance_m2"], original["margin_covariance_m2"], atol=1e-18)
        self.assertEqual(result["risks"], original["risks"])
        self.assertEqual(result["world_digest"], original["world_digest"])
        self.assertNotEqual(result["assessment_digest"], original["assessment_digest"])

    def test_conditioned_dimensions_follow_analytic_update_without_world_mutation(self):
        before = self.world.digest()
        report = self.bridge.predict((self.measurement(),))
        self.assertAlmostEqual(report["binding"]["dimensions_m"][0], 1.0984)
        self.assertEqual(report["world_digest"], before)
        self.assertEqual(self.world.digest(), before)
        self.assertEqual(report["assessment_digest"], assessment_digest(report))
        html = render_html(decode_response(report))
        for label in ("SYNTHETIC INPUTS", "FACTOR INFERENCE", "REQUEST_EVIDENCE", "UNVALIDATED", "not rebased"):
            self.assertIn(label, html)

    def test_pose_mean_update_changes_margins_and_is_explicit_in_report(self):
        factor = LinearFactor("position", ("pose:assembly:tx",), [[1]], [0.002], [[1e-6]], "survey", ("position-observation",))
        report = self.bridge.predict((factor,))
        self.assertAlmostEqual(report["pose"]["mean_tangent"][6], 0.001)
        self.assertAlmostEqual(report["risks"][0]["mean_m"]-self.bridge.predict()["risks"][0]["mean_m"], 0.001)
        fields = dict(next(b for b in decode_response(report).blocks if b.title == "pose assumptions").fields)
        self.assertEqual(fields["assembly local position correction"], "1.00 / 0.00 / 0.00 mm")

    def test_actual_populated_evaluation_displays_coverage(self):
        report = self.bridge.predict((self.measurement(),))
        measurement = dict(sample_id="heldout", source_id="independent-check", calibration_version="synthetic-v1",
                           assessment_digest=report["assessment_digest"], risk_id="corner-0:left",
                           value_m=report["risks"][0]["mean_m"], independent_noise_sigma_m=0.001)
        evaluation = evaluate_held_out([report], [measurement], fitting_source_ids=[])
        self.assertEqual(evaluation["status"], "DESCRIPTIVE_EVALUATION")
        rendered = decode_response(evaluation)
        self.assertEqual(rendered.disposition, "UNVALIDATED")
        coverage = next(block for block in rendered.blocks if block.title == "group 1 coverage")
        self.assertEqual(coverage.rows[-1], ("95.0%", "100.0%"))
        self.assertIn("standardised_residual", render_html(rendered))

    def test_fitted_sources_cannot_be_called_heldout_by_omitting_caller_list(self):
        report = self.bridge.predict((self.measurement(),))
        for source in ("survey-width", "width-observation", "prior-source"):
            measurement = dict(sample_id="check", source_id=source, calibration_version="v1", assessment_digest=report["assessment_digest"],
                               risk_id="corner-0:left", value_m=0.06, independent_noise_sigma_m=0.001)
            with self.assertRaisesRegex(ValueError, "used for fitting"):
                evaluate_held_out([report], [measurement], fitting_source_ids=[])

    def test_margin_statuses_distinguish_uncertainty_from_violation(self):
        report = self.bridge.predict()
        report["risks"][0]["p_violates"] = 0.5
        report["risks"][1]["p_violates"] = 0.95
        table = next(block for block in decode_response(report).blocks if block.title == "margins")
        self.assertEqual(table.accents[:2], ("UNRESOLVED", "VIOLATED"))

    def test_provenance_and_gravity_are_declared_without_inference(self):
        report = self.bridge.predict()
        self.assertEqual(report["inputs"], "synthetic")
        self.assertEqual(report["coordinate_convention"]["handedness"], "right")
        self.assertIsNone(report["coordinate_convention"]["up"])
        with self.assertRaises(ValueError):
            assess_opening_fit(self.world, self.frames, self.binding, **dict(self.options, inputs="verified"))

    def test_changed_input_declaration_changes_assessment_not_world(self):
        a = assess_opening_fit(self.world, self.frames, self.binding, **self.options)
        b = assess_opening_fit(self.world, self.frames, self.binding, **dict(self.options, inputs="unknown"))
        self.assertNotEqual(a["assessment_digest"], b["assessment_digest"])
        self.assertEqual(a["world_digest"], b["world_digest"])

    def test_contradictory_empty_evaluation_rejected(self):
        result = evaluate_held_out([self.bridge.predict()], [], fitting_source_ids=[])
        result["residuals"] = [{"standardised_residual": 0}]
        with self.assertRaisesRegex(ValueError, "NO_MEASUREMENTS"):
            decode_response(result)

    def test_demo_emits_all_four_report_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            run(directory)
            for name in ("prior", "posterior", "synthetic-coverage", "no-measurements"):
                self.assertTrue((Path(directory)/f"{name}.json").exists())
                html = (Path(directory)/f"{name}.html").read_text(encoding="utf-8")
                self.assertNotIn("<script", html)


if __name__ == "__main__":
    unittest.main()
