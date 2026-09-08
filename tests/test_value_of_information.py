from dataclasses import replace
import copy
import json
import unittest

from gat.demo.clearance_voi import experiment, fixture
from gat.engine.value_of_information import (
    canonical_model, digest, evaluate_measurements, plan_measurements,
)


class ValueOfInformationTests(unittest.TestCase):
    def test_decision_value_differs_from_cost_and_uncertainty_ranking(self):
        result = experiment()
        self.assertEqual(result["plan"]["selected"], "opening")
        comparisons = result["comparisons"]
        for name in ("cheapest_first", "largest_uncertainty_first"):
            self.assertEqual(comparisons[name]["measurement_ids"], ("panel",))
            self.assertEqual(comparisons[name]["expected_loss_reduction"], 0)
            self.assertAlmostEqual(comparisons[name]["expected_total_loss"], 1.01)
        self.assertEqual(comparisons["no_measurement"]["expected_total_loss"], 1)
        self.assertAlmostEqual(comparisons["one_step_voi"]["expected_total_loss"], 0.6)
        self.assertAlmostEqual(comparisons["one_step_voi"]["model_expected_decision_error"], 0.25)
        self.assertAlmostEqual(comparisons["measure_everything"]["expected_total_loss"], 0.26)
        self.assertFalse(result["plan"]["physical_action_authorized"])
        self.assertEqual(result["independent_evaluation"], "NOT_AVAILABLE")

    def test_shared_calibration_has_complementary_value(self):
        model = fixture()
        calibration = evaluate_measurements(model, ("calibration",))
        opening = evaluate_measurements(model, ("opening",))
        together = evaluate_measurements(model, ("opening", "calibration"))
        self.assertEqual(calibration["expected_loss_reduction"], 0)
        self.assertAlmostEqual(opening["expected_posterior_loss"], 0.5)
        self.assertEqual(together["expected_posterior_loss"], 0)
        self.assertAlmostEqual(together["expected_total_loss"], 0.25)
        ambiguous = next(o for o in opening["outcomes"] if o["readings"] == (("opening", 2.02),))
        self.assertEqual(ambiguous["p_fits"], 0.5)
        self.assertEqual(ambiguous["decision"], "REJECT")

    def test_reordering_preserves_digests_and_does_not_mutate(self):
        model = fixture()
        before = copy.deepcopy(model)
        reordered = replace(model, hypotheses=tuple(replace(h, values=tuple(reversed(h.values))) for h in reversed(model.hypotheses)),
                            measurements=tuple(reversed(model.measurements)),
                            outcomes=tuple(replace(o, readings=tuple(reversed(o.readings))) for o in reversed(model.outcomes)))
        self.assertEqual(plan_measurements(model), plan_measurements(reordered))
        self.assertEqual(model, before)

    def test_outcome_posteriors_obey_total_probability(self):
        model = fixture()
        for mids in ((), ("opening",), ("opening", "calibration")):
            result = evaluate_measurements(model, mids)
            self.assertAlmostEqual(sum(o["probability"] for o in result["outcomes"]), 1)
            self.assertAlmostEqual(sum(o["probability"] * o["p_fits"] for o in result["outcomes"]), 0.5)
            for outcome in result["outcomes"]:
                self.assertAlmostEqual(sum(h["probability"] for h in outcome["posterior"]), 1)
            self.assertGreaterEqual(result["expected_loss_reduction"], -1e-12)

    def test_unknown_permission_and_availability_excluded(self):
        model = fixture()
        model = replace(model, measurements=tuple(replace(m, permission="UNKNOWN") for m in model.measurements))
        plan = plan_measurements(model)
        self.assertIsNone(plan["selected"])
        self.assertEqual(len(plan["excluded"]), 3)
        with self.assertRaises(ValueError):
            evaluate_measurements(model, ("opening",))
        model = replace(model, measurements=tuple(replace(m, permission="PERMITTED", availability="UNKNOWN") for m in model.measurements))
        self.assertIsNone(plan_measurements(model)["selected"])

    def test_high_cost_prefers_no_acquisition(self):
        model = fixture()
        model = replace(model, measurements=tuple(replace(m, cost=10) for m in model.measurements))
        self.assertIsNone(plan_measurements(model)["selected"])

    def test_correlated_sensor_noise_is_not_counted_twice(self):
        from gat.engine.value_of_information import Hypothesis, JointOutcome
        model = fixture()
        model = replace(model, false_fit_loss=1, false_reject_loss=1,
            hypotheses=(Hypothesis("fit", 0.5, True, (("width", 2.02),)),
                        Hypothesis("fail", 0.5, False, (("width", 2.0),))),
            outcomes=tuple(JointOutcome(hid, p, (("opening", reading), ("calibration", reading), ("panel", 0)))
                           for hid, reading, p in (("fit", 1, 0.8), ("fit", 0, 0.2), ("fail", 0, 0.8), ("fail", 1, 0.2))))
        one = evaluate_measurements(model, ("opening",))
        both = evaluate_measurements(model, ("opening", "calibration"))
        self.assertAlmostEqual(one["expected_posterior_loss"], 0.2)
        self.assertEqual(one["expected_posterior_loss"], both["expected_posterior_loss"])

    def test_known_state_and_impossible_outcomes(self):
        model = fixture()
        model = replace(model, hypotheses=tuple(replace(h, probability=1.0 if i == 0 else 0.0)
                                               for i, h in enumerate(model.hypotheses)))
        result = evaluate_measurements(model, ("opening",))
        self.assertEqual(len(result["outcomes"]), 1)
        self.assertEqual(result["expected_loss_reduction"], 0)
        self.assertIsNone(plan_measurements(model)["selected"])

    def test_asymmetric_loss_changes_decision(self):
        model = fixture()
        self.assertEqual(evaluate_measurements(model, ())["baseline"]["decision"], "REJECT")
        alternate = replace(model, false_fit_loss=1, false_reject_loss=10)
        self.assertEqual(evaluate_measurements(alternate, ())["baseline"]["decision"], "FIT")

    def test_invalid_models_and_duplicate_measurements_refused(self):
        model = fixture()
        for invalid in (
            replace(model, false_fit_loss=float("nan")),
            replace(model, hypotheses=model.hypotheses[:-1]),
            replace(model, outcomes=model.outcomes[:-1]),
            replace(model, outcomes=model.outcomes + (model.outcomes[0],)),
            replace(model, source_digest="unbound"),
            replace(model, model_status="VALIDATED"),
            replace(model, measurements=(replace(model.measurements[0], cost=-1),) + model.measurements[1:]),
        ):
            with self.assertRaises(ValueError):
                canonical_model(invalid)
        for mids in (("opening", "opening"), ("missing",)):
            with self.assertRaises(ValueError):
                evaluate_measurements(model, mids)

    def test_artifact_and_result_bindings(self):
        artifact = json.loads(json.dumps(experiment()))
        expected = artifact.pop("artifact_digest")
        self.assertEqual(digest(artifact), expected)
        self.assertEqual(digest(artifact["source"]), artifact["model"]["source_digest"])
        self.assertEqual(digest(artifact["model"]), artifact["plan"]["model_digest"])
        for result in artifact["comparisons"].values():
            expected = result.pop("result_digest")
            self.assertEqual(digest(result), expected)


if __name__ == "__main__":
    unittest.main()
