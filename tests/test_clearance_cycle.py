from dataclasses import replace
import math
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np

from gat.demo.clearance_cycle import fixture, process, T0, T1
from gat.engine.dynamics import forecast_process
from gat.geometry.clearance_cycle import observe_planned, plan_width_measurements
from gat.geometry.frames import CoordinateFrame, FrameGraph, RigidTransform
from gat.ledger import replay_ledger, read_ledger
from gat.state_snapshot import read_snapshot
from gat.session import GatSession


class ClearanceCycleTests(unittest.TestCase):
    def setUp(self):
        self.world, self.frames, self.binding, self.gate, self.sensors = fixture()

    def plan(self, world=None, frames=None, gate=None, sensors=None, epoch=T0):
        return plan_width_measurements(world or self.world, frames or self.frames, self.binding,
            gate or self.gate, self.sensors if sensors is None else sensors, epoch_ns=epoch)

    def test_continuous_risk_matches_gaussian_classification_identity(self):
        gate = replace(self.gate, false_accept_loss=1., false_reject_loss=1.)
        plan = self.plan(gate=gate)
        option = next(o for o in plan["options"] if o["id"] == "opening-width")
        # Zero-mean joint Gaussian sign prediction: P(sign mismatch)=acos(rho)/pi.
        rho = math.sqrt(1 - option["posterior_margin_variance_m2"] / plan["baseline"]["margin_sigma_m"] ** 2)
        self.assertAlmostEqual(option["expected_posterior_loss"], math.acos(rho) / math.pi, delta=1e-9)
        self.assertEqual(plan["selected"], "opening-width")

    def test_irrelevant_high_variance_sensor_has_no_value(self):
        plan = self.plan()
        option = next(o for o in plan["options"] if o["id"] == "assembly-depth")
        self.assertAlmostEqual(option["net_value"], -option["cost"], delta=1e-12)

    def test_observation_posterior_matches_prediction_and_replays(self):
        session = GatSession(self.world)
        plan = self.plan()
        update = observe_planned(session, plan, sensor_id="opening-width", value_m=2.008,
                                 epoch_ns=T0, source_bytes=b"synthetic reading 2.008", evidence_kind="SYNTHETIC")
        self.assertAlmostEqual(update["margin_variance_m2"], update["predicted_posterior_variance_m2"], delta=1e-14)
        self.assertNotEqual(update["prior_world_digest"], update["posterior_world_digest"])
        replay = replay_ledger(self.world, session.ledger)
        self.assertEqual(replay.world.digest(), session.world.digest())
        fresh = self.plan(world=session.world)
        with self.assertRaises(ValueError):
            observe_planned(session, fresh, sensor_id="opening-width", value_m=2.008,
                            epoch_ns=T0, source_bytes=b"synthetic reading 2.008", evidence_kind="SYNTHETIC")
        with self.assertRaises(ValueError):
            observe_planned(session, plan, sensor_id="opening-width", value_m=2.008,
                            epoch_ns=T0, source_bytes=b"duplicate", evidence_kind="SYNTHETIC")

    def test_time_prediction_transports_shared_covariance(self):
        forecast = forecast_process(self.world, process(self.binding)).final_world
        before, after = self.plan(), self.plan(world=forecast, epoch=T1)
        # Shared width drift cancels from the relative gate. Only independent
        # process variance contributes: (Q11+Q22-2Q12)/4 = 0.5e-6.
        self.assertAlmostEqual(after["baseline"]["margin_sigma_m"] ** 2 - before["baseline"]["margin_sigma_m"] ** 2, 0.5e-6, delta=1e-14)
        session = GatSession(self.world)
        with self.assertRaises(ValueError):
            observe_planned(session, before, sensor_id="opening-width", value_m=2.008,
                            epoch_ns=T1, source_bytes=b"late", evidence_kind="SYNTHETIC")
        self.assertEqual(session.world.digest(), self.world.digest())

    def test_common_coordinate_transform_preserves_decision(self):
        rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
        frames = FrameGraph([CoordinateFrame("world", None, RigidTransform.identity()),
                            CoordinateFrame("model", "world", RigidTransform(rotation, [100., 20., -3.])),
                            CoordinateFrame("opening", "model", RigidTransform.identity()),
                            CoordinateFrame("assembly", "opening", RigidTransform.identity())])
        before, after = self.plan(), self.plan(frames=frames)
        self.assertEqual(before["baseline"], after["baseline"])
        self.assertEqual(before["options"], after["options"])
        self.assertNotEqual(before["frames_digest"], after["frames_digest"])

    def test_unavailable_high_cost_and_wrong_geometry(self):
        self.assertIsNone(self.plan(sensors=tuple(replace(s, permitted=False) for s in self.sensors))["selected"])
        self.assertIsNone(self.plan(sensors=tuple(replace(s, cost=100.) for s in self.sensors))["selected"])
        frames = FrameGraph([CoordinateFrame("opening", None, RigidTransform.identity()),
                            CoordinateFrame("assembly", "opening", RigidTransform(np.eye(3), [0.01, 0., 0.]))])
        with self.assertRaises(ValueError):
            self.plan(frames=frames)

    def test_sensor_order_is_stable_and_tampering_refused(self):
        self.assertEqual(self.plan(), self.plan(sensors=tuple(reversed(self.sensors))))
        plan = self.plan()
        plan["epoch_ns"] = T1
        with self.assertRaises(ValueError):
            observe_planned(GatSession(self.world), plan, sensor_id="opening-width", value_m=2.008,
                            epoch_ns=T1, source_bytes=b"value", evidence_kind="SYNTHETIC")

    def test_saved_cycle_preserves_sources_and_replays_after_reload(self):
        root = Path(__file__).resolve().parents[1] / "examples" / "continuous-clearance"
        initial = read_snapshot(root / "initial.snapshot.json").world
        posterior = read_snapshot(root / "posterior.snapshot.json").world
        ledger = read_ledger(root / "cycle.ledger.json")
        report = json.loads((root / "cycle.json").read_text())
        self.assertEqual(replay_ledger(initial, ledger).world.digest(), posterior.digest())
        self.assertEqual(hashlib.sha256((root / "observation.json").read_bytes()).hexdigest(), report["update"]["evidence_digest"])
        calibration = hashlib.sha256((root / "sensor-calibration.json").read_bytes()).hexdigest()
        self.assertTrue(all(o["calibration_digest"] == calibration for o in report["forecast_plan"]["options"]))
        self.assertEqual(report["independent_evaluation"], "NO_MEASUREMENTS")


if __name__ == "__main__":
    unittest.main()
