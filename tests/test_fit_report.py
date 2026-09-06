"""Opening-fit predictions and held-out calibration render honestly."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest

from gat import report
from gat.cli import main as cli_main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "opening_fit")


def prediction() -> dict:
    with open(os.path.join(FIXTURES, "prediction.json"), encoding="utf-8") as handle:
        return json.load(handle)


def calibration() -> dict:
    with open(os.path.join(FIXTURES, "calibration.json"), encoding="utf-8") as handle:
        return json.load(handle)


class FitReportTests(unittest.TestCase):
    def test_headline_is_the_field_acceptance_not_the_model(self) -> None:
        decoded = report.decode_response(prediction())
        self.assertEqual(decoded.operation, "opening_fit")
        self.assertEqual(decoded.disposition, "REQUEST_EVIDENCE")
        self.assertEqual(
            decoded.subject,
            "IfcBuildingElementProxy:synthetic-assembly into IfcOpeningElement:synthetic-opening",
        )
        self.assertIn("model prediction SATISFIED", decoded.subline)
        self.assertIn("calibration UNVALIDATED", decoded.subline)
        self.assertIn(report.NON_AUTHORIZING_FOOTER, decoded.footers)

    def test_blocks_carry_prediction_calibration_pose_frames_margins_identity(self) -> None:
        decoded = report.decode_response(prediction())
        titles = [block.title for block in decoded.blocks]
        self.assertEqual(
            titles,
            ["prediction", "calibration", "binding", "pose assumptions", "frames", "margins", "identity"],
        )
        by_title = {block.title: block for block in decoded.blocks}
        self.assertEqual(by_title["prediction"].accent, "SATISFIED")
        self.assertEqual(by_title["calibration"].accent, "UNVALIDATED")
        self.assertEqual(len(by_title["margins"].rows), 20)
        self.assertEqual(by_title["margins"].overflow, "and 12 more margins")
        self.assertTrue(all(accent == "" for accent in by_title["margins"].accents))
        self.assertEqual(
            dict(by_title["prediction"].fields)["tightest margin"],
            "corner-4:right 40.0 +- 2.1 mm (P(violates) 0.00000)",
        )
        self.assertEqual(by_title["margins"].rows[0][:2], ("corner-0:left", "opening"))
        self.assertIn("mm", by_title["margins"].rows[0][2])
        pose = dict(by_title["pose assumptions"].fields)
        self.assertEqual(pose["opening position sigma"], "1.00 / 1.00 / 1.00 mm")
        self.assertEqual(pose["assembly rotation sigma"], "1.00 / 1.00 / 1.00 mrad")
        self.assertEqual(pose["canonical placement uncertainty"], "no")
        self.assertIn("independent", pose["dimensions and pose"])
        self.assertEqual(len(by_title["frames"].rows), 4)
        identity = dict(by_title["identity"].fields)
        self.assertEqual(identity["world"], prediction()["world_digest"])
        self.assertEqual(identity["assessment"], prediction()["assessment_digest"])

    def test_undeclared_provenance_is_said_out_loud(self) -> None:
        decoded = report.decode_response(prediction())
        self.assertTrue(any("does not declare" in note for note in decoded.notes))
        labelled = dict(prediction(), inputs="synthetic")
        decoded = report.decode_response(labelled)
        self.assertTrue(any(note.startswith("SYNTHETIC INPUTS") for note in decoded.notes))

    def test_renderings_carry_the_vocabulary_and_truncate_honestly(self) -> None:
        decoded = report.decode_response(prediction())
        text = report.render_text(decoded)
        self.assertIn("REQUEST_EVIDENCE:", text)
        self.assertIn("UNVALIDATED", text)
        self.assertIn("(and 12 more margins)", text)
        self.assertIn("tightest margin", text)
        html = report.render_html(decoded)
        self.assertIn('class="undecided"', html)
        self.assertIn('class="proceed"', html)
        self.assertNotIn("<script", html)

    def test_acceptance_cannot_outrun_calibration(self) -> None:
        tampered = dict(prediction(), acceptance="ACCEPT")
        with self.assertRaisesRegex(ValueError, "unvalidated calibration"):
            report.decode_response(tampered)

    def test_unknown_vocabulary_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibration status"):
            report.decode_response(dict(prediction(), calibration_status="FINE"))
        with self.assertRaisesRegex(ValueError, "fit prediction"):
            report.decode_response(dict(prediction(), model_prediction="OK"))

    def test_inconsistent_records_are_refused(self) -> None:
        short = copy.deepcopy(prediction())
        short["margin_covariance_m2"] = short["margin_covariance_m2"][:-1]
        with self.assertRaisesRegex(ValueError, "covariance does not match"):
            report.decode_response(short)
        bounds = dict(prediction(), p_any_violation_lower=0.5, p_any_violation_upper=0.1)
        with self.assertRaisesRegex(ValueError, "bounds are inconsistent"):
            report.decode_response(bounds)
        foreign = copy.deepcopy(prediction())
        foreign["binding"]["dimensions"][0] = "IfcWall:somewhere-else.Width"
        with self.assertRaisesRegex(ValueError, "outside the declared subjects"):
            report.decode_response(foreign)

    def test_cli_renders_the_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "fit.html")
            self.assertEqual(
                cli_main(["report", os.path.join(FIXTURES, "prediction.json"), "--html", "-o", out]),
                0,
            )
            with open(out, encoding="utf-8") as handle:
                html = handle.read()
            self.assertIn("REQUEST_EVIDENCE", html)
            self.assertIn("corner-0:left", html)


class FitCalibrationReportTests(unittest.TestCase):
    def test_empty_evaluation_is_an_empty_state_not_a_pass(self) -> None:
        decoded = report.decode_response(calibration())
        self.assertEqual(decoded.operation, "fit_calibration")
        self.assertEqual(decoded.disposition, "NO_MEASUREMENTS")
        self.assertEqual(decoded.blocks[-1].title, "evaluation")
        self.assertEqual(dict(decoded.blocks[-1].fields)["residuals"], "0")
        text = report.render_text(decoded)
        self.assertIn("NO_MEASUREMENTS", text)
        self.assertIn("correlated samples are not independent trials", text)
        self.assertIn(report.READ_ONLY_FOOTER, text)

    def test_residuals_render_as_emitted(self) -> None:
        document = dict(calibration(), status="UNVALIDATED")
        document["residuals"] = [
            {"risk_id": "corner-0:left", "standardized": 0.4, "covered": True},
            {"risk_id": "corner-1:left", "standardized": -2.1, "covered": False},
        ]
        decoded = report.decode_response(document)
        table = decoded.blocks[0]
        self.assertEqual(table.title, "residuals")
        self.assertEqual(table.columns, ("covered", "risk_id", "standardized"))
        self.assertEqual(table.rows[1], ("no", "corner-1:left", "-2.1"))

    def test_unknown_status_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibration status"):
            report.decode_response(dict(calibration(), status="CALIBRATED"))


if __name__ == "__main__":
    unittest.main()
