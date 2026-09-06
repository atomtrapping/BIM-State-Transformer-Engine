"""The measurement-recommendation card over Codex's value-of-information
records: a positive recommendation, no worthwhile measurement, unresolved
availability or permission, and impossible outcomes that are refused."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

from gat import report
from gat.cli import main as cli_main

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "clearance-voi.json")


def experiment() -> dict:
    with open(EXAMPLE, encoding="utf-8") as handle:
        return json.load(handle)


def blocks_by_title(decoded: report.DecisionReport) -> dict:
    return {block.title: block for block in decoded.blocks}


class PositiveRecommendationTests(unittest.TestCase):
    def test_headline_is_the_disposition_and_the_subject_is_the_measurement(self) -> None:
        decoded = report.decode_response(experiment())
        self.assertEqual(decoded.operation, "measurement_recommendation")
        self.assertEqual(decoded.disposition, "RECOMMEND_MEASUREMENT")
        self.assertEqual(decoded.subject, "measure opening")
        self.assertIn("model SYNTHETIC", decoded.subline)
        self.assertIn("field validation NOT_ESTABLISHED", decoded.subline)
        self.assertTrue(any(note.startswith("SYNTHETIC MODEL") for note in decoded.notes))
        self.assertTrue(any("Physical action authorized: no" in note for note in decoded.notes))
        self.assertTrue(any("not the fit report's SATISFIED / VIOLATED / UNRESOLVED" in note for note in decoded.notes))
        self.assertEqual(decoded.footers, (report.NON_AUTHORIZING_FOOTER, report.READ_ONLY_FOOTER))

    def test_cards_explain_the_choice_without_making_it(self) -> None:
        decoded = report.decode_response(experiment())
        by_title = blocks_by_title(decoded)
        self.assertEqual(
            list(by_title),
            ["recommendation", "candidates", "outcome branches: opening", "policies compared", "model", "validation", "identity"],
        )
        recommendation = dict(by_title["recommendation"].fields)
        self.assertEqual(by_title["recommendation"].accent, "RECOMMEND_MEASUREMENT")
        self.assertEqual(recommendation["measure"], "opening")
        self.assertEqual(recommendation["quantity"], "indicated opening width (m)")
        self.assertEqual(recommendation["baseline decision"], "REJECT, expected loss 1, P(fit) 0.50000")
        self.assertEqual(recommendation["expected loss reduction"], "0.5")
        self.assertEqual(recommendation["acquisition cost"], "0.1")
        self.assertEqual(recommendation["net value"], "0.4")
        self.assertEqual(recommendation["outcome branches"], "3")
        self.assertEqual(recommendation["objective"], "gat.finite-decision-voi.v1")
        self.assertEqual(recommendation["excluded"], "none")
        candidates = by_title["candidates"]
        self.assertEqual([row[0] for row in candidates.rows], ["opening", "panel", "calibration"], "ranked by net value")
        self.assertEqual([row[-1] for row in candidates.rows], ["yes", "no", "no"])
        self.assertEqual(candidates.rows[1][5], "-0.01")
        self.assertTrue(all(accent == "" for accent in candidates.accents))
        # Every possible reading, its probability, the posterior and the decision that would follow.
        branches = by_title["outcome branches: opening"]
        self.assertEqual(branches.columns, ("reading", "probability", "P(fit) after", "decision", "expected loss"))
        self.assertEqual([row[0] for row in branches.rows], ["opening = 2", "opening = 2.02", "opening = 2.04"])
        self.assertEqual([row[3] for row in branches.rows], ["REJECT", "REJECT", "FIT"])
        self.assertAlmostEqual(sum(float(row[1]) for row in branches.rows), 1.0)
        self.assertTrue(all(accent == "" for accent in branches.accents), "loss decisions are never painted as verdicts")
        policies = by_title["policies compared"]
        self.assertEqual([row[0] for row in policies.rows], ["no_measurement", "cheapest_first", "largest_uncertainty_first", "one_step_voi", "measure_everything", "opening_and_calibration"])
        self.assertEqual(policies.rows[4][4], "0.26")
        self.assertIn("not held-out accuracy", policies.overflow)
        model = dict(by_title["model"].fields)
        self.assertEqual(model["status"], "SYNTHETIC")
        self.assertEqual(model["decision rule"], "opening_width >= equipment_width")
        self.assertEqual(model["hypotheses"], "8")
        validation = dict(by_title["validation"].fields)
        self.assertEqual(validation["field validation"], "NOT_ESTABLISHED")
        self.assertEqual(validation["independent evaluation"], "NOT_AVAILABLE")
        self.assertEqual(by_title["validation"].accent, "NOT_ESTABLISHED")
        identity = dict(by_title["identity"].fields)
        self.assertEqual(identity["artifact"], experiment()["artifact_digest"])
        self.assertEqual(identity["model"], experiment()["plan"]["model_digest"])

    def test_bare_plan_renders_without_the_model(self) -> None:
        decoded = report.decode_response(experiment()["plan"])
        by_title = blocks_by_title(decoded)
        self.assertEqual(list(by_title), ["recommendation", "candidates", "outcome branches: opening", "validation", "identity"])
        self.assertEqual(dict(by_title["recommendation"].fields)["quantity"], "undeclared")
        self.assertEqual(dict(by_title["validation"].fields)["independent evaluation"], "not declared in a bare plan")
        self.assertIn("model undeclared", decoded.subline)

    def test_renderings_and_cli(self) -> None:
        decoded = report.decode_response(experiment())
        text = report.render_text(decoded)
        self.assertIn("RECOMMEND_MEASUREMENT", text)
        self.assertIn("opening = 2.04", text)
        html = report.render_html(decoded)
        self.assertIn("SYNTHETIC MODEL", html)
        self.assertNotIn("<script", html)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "voi.html")
            self.assertEqual(cli_main(["report", EXAMPLE, "--html", "-o", out]), 0)
            self.assertEqual(cli_main(["report", EXAMPLE]), 0)

    def test_live_demo_output_decodes(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "gat.demo.clearance_voi"], capture_output=True, text=True, check=True,
            env={**os.environ, "OPENBLAS_NUM_THREADS": "1"},
        )
        decoded = report.decode_response(json.loads(completed.stdout))
        self.assertEqual(decoded.disposition, "RECOMMEND_MEASUREMENT")
        self.assertEqual(decoded.subject, "measure opening")


class NoWorthwhileMeasurementTests(unittest.TestCase):
    def make(self) -> dict:
        # Every candidate priced above its benefit: the arithmetic still closes, nothing is worth taking.
        document = copy.deepcopy(experiment())
        for option in document["plan"]["options"]:
            option["acquisition_cost"] = option["expected_loss_reduction"] + 1.0
            option["net_value"] = option["expected_loss_reduction"] - option["acquisition_cost"]
            option["expected_total_loss"] = option["expected_posterior_loss"] + option["acquisition_cost"]
        document["plan"]["selected"] = None
        document["plan"]["disposition"] = "NO_WORTHWHILE_AVAILABLE_MEASUREMENT"
        return document

    def test_nothing_is_recommended_and_the_headline_is_undecided(self) -> None:
        decoded = report.decode_response(self.make())
        self.assertEqual(decoded.disposition, "NO_WORTHWHILE_AVAILABLE_MEASUREMENT")
        self.assertEqual(decoded.subject, "no worthwhile available measurement")
        by_title = blocks_by_title(decoded)
        self.assertNotIn("outcome branches: opening", by_title)
        recommendation = dict(by_title["recommendation"].fields)
        self.assertTrue(recommendation["measure"].startswith("none"))
        self.assertNotIn("net value", recommendation)
        self.assertEqual([row[-1] for row in by_title["candidates"].rows], ["no", "no", "no"])
        self.assertEqual(by_title["candidates"].rows[0][5], "-1")
        html = report.render_html(decoded)
        self.assertIn('<section class="undecided"><h2>recommendation', html)

    def test_a_worthwhile_first_option_cannot_be_left_unselected(self) -> None:
        document = copy.deepcopy(experiment())
        document["plan"]["selected"] = None
        document["plan"]["disposition"] = "NO_WORTHWHILE_AVAILABLE_MEASUREMENT"
        with self.assertRaisesRegex(ValueError, "ranked first but none was selected"):
            report.decode_response(document)


class UnresolvedAssumptionTests(unittest.TestCase):
    def exclude(self, measurement_id: str, **declaration: str) -> dict:
        document = copy.deepcopy(experiment())
        plan = document["plan"]
        plan["options"] = [option for option in plan["options"] if option["measurement_ids"] != [measurement_id]]
        measurement = next(m for m in document["model"]["measurements"] if m["id"] == measurement_id)
        entry = dict(measurement, **declaration)
        measurement.update(declaration)
        plan["excluded"].append(entry)
        return document

    def test_unknown_availability_or_permission_is_listed_with_its_reason_and_never_ranked(self) -> None:
        decoded = report.decode_response(self.exclude("panel", availability="UNKNOWN"))
        by_title = blocks_by_title(decoded)
        self.assertEqual([row[0] for row in by_title["candidates"].rows], ["opening", "calibration"])
        excluded = by_title["excluded measurements"]
        self.assertEqual(excluded.columns, ("measurement", "quantity", "availability", "permission", "reason"))
        self.assertEqual(excluded.rows, (("panel", "unrelated panel offset", "UNKNOWN", "PERMITTED", "availability UNKNOWN"),))
        self.assertEqual(dict(by_title["recommendation"].fields)["excluded"], "1 measurement(s), listed below")
        both = report.decode_response(self.exclude("calibration", availability="UNAVAILABLE", permission="UNKNOWN"))
        self.assertEqual(blocks_by_title(both)["excluded measurements"].rows[0][4], "availability UNAVAILABLE; permission UNKNOWN")

    def test_an_available_permitted_measurement_cannot_be_excluded(self) -> None:
        document = copy.deepcopy(experiment())
        document["plan"]["excluded"].append(dict(document["model"]["measurements"][2]))
        with self.assertRaisesRegex(ValueError, "cannot be excluded"):
            report.decode_response(document)
        odd = self.exclude("panel", availability="MAYBE")
        with self.assertRaisesRegex(ValueError, "unknown availability or permission"):
            report.decode_response(odd)


class ImpossibleOutcomeTests(unittest.TestCase):
    def selected_option(self, document: dict) -> dict:
        return document["plan"]["options"][0]

    def test_branch_probabilities_must_sum_to_one_and_be_possible(self) -> None:
        document = copy.deepcopy(experiment())
        self.selected_option(document)["outcomes"][0]["probability"] += 0.2
        with self.assertRaisesRegex(ValueError, "sum to one"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        option = self.selected_option(document)
        option["outcomes"][0]["probability"] = 0.0
        option["outcomes"][1]["probability"] += 0.25
        with self.assertRaisesRegex(ValueError, "impossible"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        self.selected_option(document)["outcomes"][0]["p_fits"] = 1.5
        with self.assertRaisesRegex(ValueError, "impossible"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        self.selected_option(document)["outcomes"][0]["decision"] = "MAYBE"
        with self.assertRaisesRegex(ValueError, "two-action model"):
            report.decode_response(document)

    def test_arithmetic_that_does_not_close_is_refused(self) -> None:
        document = copy.deepcopy(experiment())
        self.selected_option(document)["net_value"] = 0.9
        with self.assertRaisesRegex(ValueError, "do not close"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        self.selected_option(document)["outcomes"][0]["expected_loss"] = 5.0
        with self.assertRaisesRegex(ValueError, "does not follow from its branches"):
            report.decode_response(document)

    def test_claims_the_contract_forbids_are_refused(self) -> None:
        document = copy.deepcopy(experiment())
        document["plan"]["physical_action_authorized"] = True
        with self.assertRaisesRegex(ValueError, "authorization"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        document["plan"]["disposition"] = "MEASURE_NOW"
        with self.assertRaisesRegex(ValueError, "disposition"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        document["plan"]["selected"] = "panel"
        with self.assertRaisesRegex(ValueError, "contradicts the ranking"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        document["plan"]["options"].reverse()
        with self.assertRaisesRegex(ValueError, "ranked"):
            report.decode_response(document)
        document = copy.deepcopy(experiment())
        document["model"]["model_status"] = "FIELD_VALIDATED"
        with self.assertRaisesRegex(ValueError, "model status"):
            report.decode_response(document)


if __name__ == "__main__":
    unittest.main()
