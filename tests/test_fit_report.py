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


def posterior() -> dict:
    """A live `python -m gat.demo.opening_factors` posterior: synthetic inputs,
    a declared coordinate convention and one conditioning factor."""
    with open(os.path.join(FIXTURES, "posterior.json"), encoding="utf-8") as handle:
        return json.load(handle)


def coverage() -> dict:
    """The same demo's held-out evaluation: three invented checks of one margin."""
    with open(os.path.join(FIXTURES, "coverage.json"), encoding="utf-8") as handle:
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
            ["prediction", "controlling clearance", "calibration", "evidence still missing",
             "binding", "pose assumptions", "frames", "margins", "inputs and identity"],
        )
        by_title = {block.title: block for block in decoded.blocks}
        self.assertEqual(by_title["prediction"].accent, "SATISFIED")
        self.assertEqual(by_title["calibration"].accent, "UNVALIDATED")
        self.assertEqual(len(by_title["margins"].rows), 20)
        self.assertEqual(by_title["margins"].overflow, "and 12 more margins")
        self.assertTrue(all(accent == "" for accent in by_title["margins"].accents))
        controlling = dict(by_title["controlling clearance"].fields)
        self.assertEqual(controlling["margin"], "corner-4:right")
        self.assertEqual(controlling["mean +- sigma"], "40.0 +- 2.1 mm")
        self.assertEqual(controlling["P(violates)"], "0.00000")
        self.assertEqual(controlling["tightest margin"], "the same")
        self.assertEqual(by_title["controlling clearance"].accent, "")
        self.assertEqual(by_title["margins"].rows[0][:2], ("corner-0:left", "opening"))
        self.assertIn("mm", by_title["margins"].rows[0][2])
        pose = dict(by_title["pose assumptions"].fields)
        self.assertEqual(pose["opening position sigma"], "1.00 / 1.00 / 1.00 mm")
        self.assertEqual(pose["assembly rotation sigma"], "1.00 / 1.00 / 1.00 mrad")
        self.assertEqual(pose["canonical placement uncertainty"], "no")
        self.assertIn("independent", pose["dimensions and pose"])
        self.assertEqual(len(by_title["frames"].rows), 4)
        self.assertTrue(all(len(row) == 5 for row in by_title["frames"].rows))
        identity = dict(by_title["inputs and identity"].fields)
        self.assertEqual(identity["inputs"], "undeclared")
        self.assertEqual(identity["method version"], "not declared in the record")
        self.assertEqual(identity["world"], prediction()["world_digest"])
        self.assertEqual(identity["assessment"], prediction()["assessment_digest"])

    def test_controlling_clearance_is_the_margin_the_prediction_turns_on(self) -> None:
        # corner-0:top has a 2100 mm margin: never the tightest, but once it is
        # the least cleared it controls, and the card says so in amber.
        record = copy.deepcopy(prediction())
        record["risks"][3]["p_violates"] = 0.5
        card = next(b for b in report.decode_response(record).blocks if b.title == "controlling clearance")
        fields = dict(card.fields)
        self.assertEqual(fields["margin"], record["risks"][3]["id"])
        self.assertEqual(fields["quantity class"], "corner_clearance")
        self.assertEqual(fields["frame"], "opening")
        self.assertEqual(fields["rule"], "highest P(violates), then smallest margin")
        self.assertEqual(fields["tightest margin"], "corner-4:right 40.0 +- 2.1 mm (P(violates) 0.00000)")
        self.assertEqual(card.accent, "UNRESOLVED")
        record["risks"][3]["p_violates"] = 0.99
        decoded = report.decode_response(record)
        card = next(b for b in decoded.blocks if b.title == "controlling clearance")
        self.assertEqual(card.accent, "VIOLATED")
        self.assertIn('<section class="stop"><h2>controlling clearance', report.render_html(decoded))

    def test_evidence_card_names_what_no_measurement_has_validated(self) -> None:
        decoded = report.decode_response(prediction())
        card = next(b for b in decoded.blocks if b.title == "evidence still missing")
        fields = dict(card.fields)
        self.assertEqual(card.accent, "UNVALIDATED")
        self.assertEqual(fields["field acceptance"], "REQUEST_EVIDENCE")
        self.assertEqual(fields["margins rest on"], "5 dimensions and 2 poses")
        self.assertEqual(fields["dimensions"].split("; "), prediction()["binding"]["dimensions"])
        self.assertEqual(fields["poses"], "opening, assembly; assumption synthetic-independent-1mm-1mrad-v1")
        self.assertIn("no evidence receipt", fields["receipts in this record"])
        self.assertNotIn("in-sample factors", fields)
        # The title follows the engine's own word: only REQUEST_EVIDENCE is "still missing".
        rejected = [b.title for b in report.decode_response(dict(prediction(), acceptance="REJECT")).blocks]
        self.assertIn("evidence", rejected)
        self.assertNotIn("evidence still missing", rejected)

    def test_frame_chains_are_walked_and_broken_chains_refused(self) -> None:
        decoded = report.decode_response(prediction())
        binding = dict(next(b for b in decoded.blocks if b.title == "binding").fields)
        self.assertEqual(binding["opening frame chain"], "opening -> storey -> model")
        self.assertEqual(binding["assembly frame chain"], "assembly -> opening -> storey -> model")
        frames = next(b for b in decoded.blocks if b.title == "frames")
        self.assertEqual(frames.columns, ("frame", "parent", "unit", "origin in parent", "rotation"))
        self.assertEqual({row[4] for row in frames.rows}, {"identity"})
        rotated = copy.deepcopy(prediction())
        next(f for f in rotated["frames"] if f["id"] == "storey")["rotation"] = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        frames = next(b for b in report.decode_response(rotated).blocks if b.title == "frames")
        self.assertEqual({row[0]: row[4] for row in frames.rows}["storey"], "rotated")
        missing = copy.deepcopy(prediction())
        missing["frames"] = [f for f in missing["frames"] if f["id"] != "storey"]
        with self.assertRaisesRegex(ValueError, "bound but not declared"):
            report.decode_response(missing)
        cyclic = copy.deepcopy(prediction())
        next(f for f in cyclic["frames"] if f["id"] == "model")["parent_id"] = "assembly"
        with self.assertRaisesRegex(ValueError, "cycles"):
            report.decode_response(cyclic)
        doubled = copy.deepcopy(prediction())
        doubled["frames"].append(dict(doubled["frames"][0]))
        with self.assertRaisesRegex(ValueError, "declared twice"):
            report.decode_response(doubled)

    def test_convention_inference_and_method_render_as_cards(self) -> None:
        record = posterior()
        decoded = report.decode_response(record)
        self.assertEqual(
            [b.title for b in decoded.blocks],
            ["prediction", "controlling clearance", "calibration", "evidence still missing", "binding",
             "pose assumptions", "coordinate convention", "factor inference", "frames", "margins",
             "inputs and identity"],
        )
        by_title = {b.title: b for b in decoded.blocks}
        convention = dict(by_title["coordinate convention"].fields)
        self.assertEqual(convention["handedness"], "right")
        self.assertEqual(convention["up"], "undeclared")
        self.assertEqual(convention["aperture_axes"], "X, Z")
        inference = dict(by_title["factor inference"].fields)
        self.assertEqual(inference["contract"], "gat-opening-factor-bridge-v1")
        self.assertEqual(inference["canonical state committed"], "no")
        self.assertEqual(inference["geometry evaluation"], "fixed_first_order_linearization")
        self.assertEqual(inference["factors"], "1: opening-width-check (observation, source synthetic-width-instrument)")
        self.assertEqual(inference["factor graph"], record["inference"]["graph_digest"])
        self.assertEqual(
            dict(by_title["evidence still missing"].fields)["in-sample factors"],
            "1; in-sample residuals are not calibration",
        )
        identity = dict(by_title["inputs and identity"].fields)
        self.assertEqual(identity["inputs"], "synthetic")
        self.assertEqual(identity["method version"], "not declared in the record")
        self.assertFalse(any(note.startswith(("coordinate convention", "factor graph")) for note in decoded.notes))
        self.assertTrue(any(note.startswith("FACTOR INFERENCE") for note in decoded.notes))
        # A record that declares its method shows it verbatim in place of the "not declared" row.
        declared = dict(record, method={"engine": "gat 0.1.0", "commit": "9b6dffb"})
        identity = dict(next(b for b in report.decode_response(declared).blocks if b.title == "inputs and identity").fields)
        self.assertEqual(identity["method engine"], "gat 0.1.0")
        self.assertEqual(identity["method commit"], "9b6dffb")
        self.assertNotIn("method version", identity)
        tampered = copy.deepcopy(record)
        tampered["inference"]["canonical_state_committed"] = True
        with self.assertRaisesRegex(ValueError, "committed"):
            report.decode_response(tampered)

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

    def test_residuals_compare_predicted_with_measured(self) -> None:
        record = coverage()
        decoded = report.decode_response(record)
        self.assertEqual(decoded.disposition, "UNVALIDATED")
        table = next(b for b in decoded.blocks if b.title == "residuals: predicted vs measured")
        self.assertEqual(
            table.columns,
            ("risk_id", "sample_id", "source_id", "predicted", "measured", "predictive sigma", "standardised_residual"),
        )
        first = record["residuals"][0]
        self.assertEqual(table.rows[0][:3], (first["risk_id"], first["sample_id"], first["source_id"]))
        self.assertEqual(table.rows[0][3], f"{(first['value_m'] - first['residual_m']) * 1000:.1f} mm")
        self.assertEqual(table.rows[0][4], f"{first['value_m'] * 1000:.1f} mm")
        self.assertEqual(table.rows[2][6], "3")
        # The assessment is named once, on the evaluation card, not per row.
        self.assertTrue(all(first["assessment_digest"] not in cell for row in table.rows for cell in row))
        evaluation = dict(next(b for b in decoded.blocks if b.title == "evaluation").fields)
        self.assertEqual(evaluation["assessment"], first["assessment_digest"])
        html = report.render_html(decoded)
        self.assertIn("standardised_residual", html)
        self.assertIn("DESCRIPTIVE_EVALUATION", html)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "coverage.html")
            self.assertEqual(cli_main(["report", os.path.join(FIXTURES, "coverage.json"), "--html", "-o", out]), 0)
        # A sigma of zero cannot have standardised anything; refuse rather than divide.
        broken = copy.deepcopy(record)
        broken["residuals"][0]["predictive_observation_sigma_m"] = 0.0
        with self.assertRaisesRegex(ValueError, "sigma must be positive"):
            report.decode_response(broken)

    def _rows(self, decoded):
        table = next(b for b in decoded.blocks if b.title == "residuals: predicted vs measured")
        card = next(b for b in decoded.blocks if b.title == "residuals past the reader's threshold")
        return table, card, dict(card.fields)

    def test_a_residual_past_the_readers_threshold_is_marked_and_the_threshold_is_named(self) -> None:
        # The live demo's third check sits at exactly three sigma; the other
        # two do not. The threshold is the reader's because no held-out record
        # declares one, and the card says so rather than implying the
        # evaluator set it.
        decoded = report.decode_response(coverage())
        table, card, fields = self._rows(decoded)
        self.assertEqual(list(table.accents), ["", "", "UNRESOLVED"])
        self.assertEqual(fields["past it"], "1 of 3")
        self.assertIn("the reader's, not declared by the record", fields["threshold"])
        self.assertIn(">= 3", fields["threshold"])
        self.assertIn("which of the two is wrong is not decided here", fields["what that says"])
        self.assertEqual(card.accent, "UNRESOLVED")

    def test_a_large_residual_is_never_a_decision_and_never_red(self) -> None:
        # A residual says the prediction and the measurement disagree. It does
        # not say which is wrong, so no magnitude earns the decision colour.
        record = copy.deepcopy(coverage())
        record["residuals"][0]["standardised_residual"] = -50.0
        decoded = report.decode_response(record)
        table, card, fields = self._rows(decoded)
        self.assertEqual(list(table.accents), ["UNRESOLVED", "", "UNRESOLVED"])
        self.assertEqual(fields["past it"], "2 of 3")
        self.assertNotIn("VIOLATED", table.accents)
        self.assertNotEqual(card.accent, "VIOLATED")
        self.assertNotIn("VIOLATED", report.render_text(decoded))

    def test_nothing_past_the_threshold_is_not_a_calibration_result(self) -> None:
        record = copy.deepcopy(coverage())
        for residual in record["residuals"]:
            residual["standardised_residual"] = 2.9
        decoded = report.decode_response(record)
        table, card, fields = self._rows(decoded)
        self.assertEqual(list(table.accents), ["", "", ""])
        self.assertEqual(fields["past it"], "0 of 3")
        self.assertIn("in-sample residuals never were one", fields["what that says"])
        self.assertEqual(card.accent, "")

    def test_the_report_says_the_posterior_is_not_where_disagreement_shows(self) -> None:
        # Combining two disagreeing Gaussian measurements adds their
        # precisions: the posterior narrows however far apart they are. A
        # reader looking there for conflict finds the opposite of conflict,
        # so the report says where to look instead.
        decoded = report.decode_response(coverage())
        note = next(n for n in decoded.notes if n == report.RESIDUAL_CHANNEL_NOTE)
        self.assertIn("adds their precisions", note)
        self.assertIn("more confident than either about a value neither declared", note)
        self.assertIn("a narrow posterior is not evidence that the inputs agreed", note)
        self.assertIn(note, report.render_text(decoded))
        # A record whose residuals the reader does not recognise renders as
        # emitted and claims nothing about a channel it did not read.
        unknown = copy.deepcopy(coverage())
        unknown["residuals"] = [{"whatever": 1.0}]
        self.assertNotIn(report.RESIDUAL_CHANNEL_NOTE, report.decode_response(unknown).notes)

    def test_unknown_status_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibration status"):
            report.decode_response(dict(calibration(), status="CALIBRATED"))


if __name__ == "__main__":
    unittest.main()
