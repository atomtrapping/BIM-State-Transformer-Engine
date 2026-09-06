"""Analytic and coordinate-equivalence evidence, not field calibration."""
from dataclasses import replace
import copy
import math
import unittest

import numpy as np

from gat.demo.opening_fit import synthetic_case
from gat.geometry.frames import CoordinateFrame, FrameGraph, RigidTransform, _skew
from gat.geometry.opening_fit import assess_opening_fit, margin_linearization, OpeningFitBinding
from gat.geometry.fit_calibration import evaluate_held_out
from gat.ids import VarId
from gat.session import GatSession
from tests.test_coordinate_frames import rotation


class OpeningFitTests(unittest.TestCase):
    def setUp(self):
        self.world, self.frames, self.binding = synthetic_case()

    def assess(self, frames=None, pose=None, cross=None, binding=None):
        return assess_opening_fit(self.world, frames or self.frames, binding or self.binding,
                                  pose_covariance=np.zeros((12, 12)) if pose is None else pose,
                                  raw_pose_cross_covariance=np.zeros((5, 12)) if cross is None else cross,
                                  assumption_id="synthetic-test-v1", required_clearance_m=0.01)

    def test_analytic_margin_and_dimension_variance(self):
        before = self.world.digest()
        report = self.assess()
        self.assertAlmostEqual(min(r["mean_m"] for r in report["risks"]), 0.04)
        self.assertAlmostEqual(report["risks"][0]["sigma_m"] ** 2, 0.5e-6)
        self.assertEqual(report["model_prediction"], "SATISFIED")
        self.assertEqual(report["acceptance"], "REQUEST_EVIDENCE")
        self.assertEqual(report["calibration_status"], "UNVALIDATED")
        self.assertEqual(before, self.world.digest())
        self.assertEqual(report["subjects"][0]["global_id"], "synthetic-opening")

    def test_global_rotation_translation_units_and_nested_equivalence(self):
        nominal = self.assess(pose=np.eye(12) * 1e-6)
        outer = RigidTransform(rotation([1, 2, 3], 0.8), [34, -18, 20])
        frames = FrameGraph([CoordinateFrame("root", None, RigidTransform.identity()),
                             CoordinateFrame("outer", "root", outer, "mm"),
                             CoordinateFrame("opening", "outer", self.frames.to_root("opening"), "mm"),
                             CoordinateFrame("assembly", "outer", self.frames.to_root("assembly"), "mm")])
        changed = self.assess(frames=frames, pose=np.eye(12) * 1e-6)
        np.testing.assert_allclose([r["mean_m"] for r in nominal["risks"]], [r["mean_m"] for r in changed["risks"]], atol=1e-13)
        np.testing.assert_allclose(nominal["margin_covariance_m2"], changed["margin_covariance_m2"], atol=1e-16)
        self.assertEqual(nominal["model_prediction"], changed["model_prediction"])
        self.assertNotEqual(nominal["assessment_digest"], changed["assessment_digest"])
        self.assertEqual(nominal["world_digest"], changed["world_digest"])

    def test_shared_global_rigid_pose_cancels(self):
        blocks = []
        for name in ("opening", "assembly"):
            transform = self.frames.to_root(name)
            rt = transform.rotation.T
            blocks.append(np.block([[rt, -rt @ _skew(transform.translation_m)], [np.zeros((3, 3)), rt]]))
        common = np.vstack(blocks)
        pose = common @ (np.eye(6) * 1e-4) @ common.T
        nominal, shared = self.assess(), self.assess(pose=pose)
        np.testing.assert_allclose(shared["margin_covariance_m2"], nominal["margin_covariance_m2"], atol=2e-18)
        independent = self.assess(pose=np.diag(np.diag(pose)))
        self.assertGreater(independent["risks"][0]["sigma_m"], shared["risks"][0]["sigma_m"] * 10)

    def test_jacobian_against_independent_perturbed_geometry(self):
        dimensions = np.array([1.2, 2.3, 1.0, 0.2, 2.0])
        opening = RigidTransform(rotation([1, 2, 1], 0.4), [2, 1, 3])
        assembly = RigidTransform(rotation([2, 1, 3], 0.7), [2.1, 1.1, 3.2])
        _, analytic = margin_linearization(dimensions, opening.inverse().compose(assembly))
        def evaluate(delta):
            d = dimensions + delta[:5]
            transforms = []
            for nominal, offset in ((opening, 5), (assembly, 11)):
                angle = np.linalg.norm(delta[offset+3:offset+6])
                r = np.eye(3) if angle == 0 else rotation(delta[offset+3:offset+6], angle)
                transforms.append(nominal.compose(RigidTransform(r, delta[offset:offset+3])))
            relative = transforms[0].inverse().compose(transforms[1])
            # Independent corner and half-plane enumeration; no production Jacobian.
            corners = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]) * d[2:] / 2
            points = corners @ relative.rotation.T + relative.translation_m
            return np.column_stack((d[0]/2 + points[:,0], d[0]/2 - points[:,0],
                                    d[1]/2 + points[:,2], d[1]/2 - points[:,2])).ravel()
        finite = []
        for i in range(17):
            delta = np.zeros(17)
            delta[i] = 1e-6
            finite.append((evaluate(delta) - evaluate(-delta)) / 2e-6)
        np.testing.assert_allclose(analytic, np.array(finite).T, atol=1e-9, rtol=1e-7)

    def test_dimension_pose_correlation_is_preserved(self):
        pose = np.eye(12) * 1e-6
        cross = np.zeros((5, 12))
        row = self.world.belief.index.row(self.binding.dimensions[0])
        cross[row, 6] = 0.5e-6
        independent, correlated = self.assess(pose=pose), self.assess(pose=pose, cross=cross)
        self.assertAlmostEqual(correlated["risks"][0]["sigma_m"] ** 2 - independent["risks"][0]["sigma_m"] ** 2, 0.5e-6)

    def test_relative_shift_and_rotation_change_fit(self):
        for transform in (RigidTransform(np.eye(3), [0.3, 0, 0]), RigidTransform(rotation([0, 1, 0], math.pi/2), [0, 0, 0])):
            frames = FrameGraph([replace(f, to_parent=transform) if f.frame_id == "assembly" else f for f in self.frames.frames.values()])
            report = self.assess(frames=frames)
            self.assertEqual(report["model_prediction"], "VIOLATED")
            self.assertFalse(report["deterministic_nominal_fit"])

    def test_invalid_joint_covariance_and_frames_fail_closed(self):
        for pose in (np.eye(12) * -1, np.ones((2, 2)), np.full((12,12), np.nan)):
            with self.assertRaises(ValueError):
                self.assess(pose=pose)
        with self.assertRaises(ValueError):
            self.assess(cross=np.ones((5, 12)))
        with self.assertRaises(ValueError):
            self.assess(binding=replace(self.binding, assembly_frame="missing"))

    def test_missing_ifc_depth_is_not_invented(self):
        from pathlib import Path
        session = GatSession.load_ifc(Path(__file__).parents[1] / "gat/demo/model.ifc")
        opening, door = session.var("Opening-1", "Width").entity, session.var("Door-1", "Width").entity
        variables = tuple(VarId(e,q) for e,q in ((opening,"Width"),(opening,"Height"),(door,"Width"),(door,"Depth"),(door,"Height")))
        with self.assertRaises(KeyError):
            assess_opening_fit(session.world, self.frames, OpeningFitBinding("opening", "assembly", variables),
                               pose_covariance=np.zeros((12,12)), raw_pose_cross_covariance=np.zeros((len(session.world.belief.index),12)),
                               assumption_id="test")

    def test_binding_and_negative_dimension_validation(self):
        with self.assertRaises(ValueError):
            replace(self.binding, dimensions=self.binding.dimensions[:4])
        with self.assertRaises(ValueError):
            margin_linearization([1, 2, -1, 0.1, 2], RigidTransform.identity())

    def test_empty_calibration_and_known_coverage(self):
        report = self.assess()
        empty = evaluate_held_out([report], [], fitting_source_ids=[])
        self.assertEqual(empty["status"], "NO_MEASUREMENTS")
        risk = report["risks"][0]
        measurements = [{"sample_id": str(i), "source_id": "synthetic-heldout", "calibration_version": "synthetic-v1",
                         "assessment_digest": report["assessment_digest"], "risk_id": risk["id"],
                         "value_m": risk["mean_m"] + z * risk["sigma_m"], "independent_noise_sigma_m": 0.0}
                        for i,z in enumerate((0, 1, 3))]
        before = copy.deepcopy(report)
        result = evaluate_held_out([report], measurements, fitting_source_ids=[], levels=(0.95,))
        self.assertEqual(result["groups"][0]["coverage"][0]["observed"], 2/3)
        self.assertEqual(report, before)
        with self.assertRaises(ValueError):
            evaluate_held_out([report], measurements, fitting_source_ids=["synthetic-heldout"])
        with self.assertRaises(ValueError):
            evaluate_held_out([report], [measurements[0], measurements[0]], fitting_source_ids=[])

    def test_calibration_rejects_changed_predictions(self):
        report = self.assess()
        report["risks"][0]["mean_m"] += 0.01
        with self.assertRaises(ValueError):
            evaluate_held_out([report], [], fitting_source_ids=[])

    def test_calibration_includes_independent_observation_noise(self):
        report = self.assess()
        risk = report["risks"][0]
        measurement = {"sample_id": "s1", "source_id": "synthetic", "calibration_version": "v1",
                       "assessment_digest": report["assessment_digest"], "risk_id": risk["id"],
                       "value_m": risk["mean_m"] + 0.01, "independent_noise_sigma_m": 0.01}
        evaluated = evaluate_held_out([report], [measurement], fitting_source_ids=[])
        self.assertAlmostEqual(evaluated["residuals"][0]["standardised_residual"],
                               0.01 / math.hypot(risk["sigma_m"], 0.01))

    def test_indefinite_joint_cross_blocks_rejected_even_if_pose_is_valid(self):
        with self.assertRaises(ValueError):
            self.assess(pose=np.eye(12)*1e-6, cross=np.full((5,12), 1e-3))


if __name__ == "__main__":
    unittest.main()
