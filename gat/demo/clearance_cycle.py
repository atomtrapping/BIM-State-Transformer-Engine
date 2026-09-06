"""A generated time-indexed width measurement cycle; never field validation."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from gat.engine.dynamics import EvolveLinearGaussian, forecast_process
from gat.engine.executor import World
from gat.geometry.clearance_cycle import LinearSensor, WidthGate, observe_planned, plan_width_measurements
from gat.geometry.frames import CoordinateFrame, FrameGraph, RigidTransform
from gat.geometry.opening_fit import OpeningFitBinding
from gat.ids import EntityId, VarId
from gat.ir.core import Entity, Module, QtySlot, Role, Unit, Rel, RelKind
from gat.ledger import replay_ledger
from gat.session import GatSession


T0 = "1788652800000000000"
T1 = str(int(T0) + 60_000_000_000)
CALIBRATION = b'{"kind":"SYNTHETIC","model":"independent-2mm-reading-noise-v1"}\n'
PROCESS = b'{"kind":"SYNTHETIC","model":"60s-width-random-walk-v1","shared_variance_m2":0.000025,"independent_variance_m2":0.000001}\n'


def fixture():
    opening = EntityId("IfcOpeningElement", "cycle-opening")
    assembly = EntityId("IfcBuildingElementProxy", "cycle-assembly")
    variables = tuple(VarId(e, q) for e, q in ((opening, "Width"), (opening, "Height"),
                       (assembly, "Width"), (assembly, "Depth"), (assembly, "Height")))
    slots = {v: QtySlot(v, Role.RAW, Unit.M, size, sigma) for v, size, sigma in
             zip(variables, (2.02, 2.2, 2.0, 0.1, 2.0), (0.01, 0.001, 0.01, 0.02, 0.001))}
    entities = {e: Entity(e, e.global_id, slots={v.quantity: s for v, s in slots.items() if v.entity == e}) for e in (opening, assembly)}
    wall = EntityId("IfcWall", "cycle-wall")
    entities[wall] = Entity(wall, "Host wall", slots={})
    world = World.compile(Module(entities, (Rel(RelKind.VOIDS, opening, wall),), (), {"source": "synthetic-continuous-clearance-v1"}))
    frames = FrameGraph([CoordinateFrame("model", None, RigidTransform.identity()),
                        CoordinateFrame("opening", "model", RigidTransform.identity()),
                        CoordinateFrame("assembly", "opening", RigidTransform.identity())])
    binding = OpeningFitBinding("opening", "assembly", variables)
    gate = WidthGate(0.01, 10., 2., "declared decision-loss units", "synthetic exact aligned/centred poses")
    calibration_digest = hashlib.sha256(CALIBRATION).hexdigest()
    sensors = tuple(LinearSensor(name, ((v, 1.),), 0., 0.002, cost, calibration_digest)
                    for name, v, cost in (("opening-width", variables[0], 0.02),
                                         ("assembly-width", variables[2], 0.03),
                                         ("assembly-depth", variables[3], 0.001)))
    return world, frames, binding, gate, sensors


def process(binding):
    # A shared physical width-drift component plus independent process noise.
    # This is not a rigid pose translation masquerading as a width change.
    return EvolveLinearGaussian((binding.dimensions[0], binding.dimensions[2]),
        np.eye(2), np.zeros(2), np.full((2, 2), 0.000025) + np.eye(2) * 0.000001,
        60., "synthetic-60s-width-random-walk-v1", hashlib.sha256(PROCESS).hexdigest())


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)  # Never replace an earlier experiment.
    world, frames, binding, gate, sensors = fixture()
    session = GatSession(world)
    session.export_snapshot(str(output / "initial.snapshot.json"))
    (output / "sensor-calibration.json").write_bytes(CALIBRATION)
    (output / "process-calibration.json").write_bytes(PROCESS)
    initial_plan = plan_width_measurements(world, frames, binding, gate, sensors, epoch_ns=T0)
    transition = process(binding)
    forecast = forecast_process(world, transition).final_world
    forecast_plan = plan_width_measurements(forecast, frames, binding, gate, sensors, epoch_ns=T1)
    # Time advance is a distinct model-based prediction in the ledger, never an observation.
    session.run(transition, provenance={"kind": "SYNTHETIC_PROCESS", "from_epoch_ns": T0, "to_epoch_ns": T1})
    observation = {"kind": "SYNTHETIC", "sensor_id": "opening-width", "epoch_ns": T1,
                   "value_m": 2.008, "calibration_digest": hashlib.sha256(CALIBRATION).hexdigest()}
    raw = (json.dumps(observation, sort_keys=True) + "\n").encode()
    (output / "observation.json").write_bytes(raw)  # Preserve before conditioning.
    update = observe_planned(session, forecast_plan, sensor_id=observation["sensor_id"],
        value_m=observation["value_m"], epoch_ns=T1, source_bytes=raw, evidence_kind="SYNTHETIC")
    after = plan_width_measurements(session.world, frames, binding, gate, sensors, epoch_ns=T1)
    session.export_snapshot(str(output / "posterior.snapshot.json"))
    session.export_ledger(str(output / "cycle.ledger.json"))
    replayed = replay_ledger(world, session.ledger)
    report = {"schema": "gat-continuous-clearance-cycle-v1", "initial_plan": initial_plan,
              "forecast_plan": forecast_plan, "update": update, "posterior_plan": after,
              "independent_evaluation": "NO_MEASUREMENTS", "evidence_kind": "SYNTHETIC",
              "replay": {"world_digest": replayed.world.digest(), "ledger_head": replayed.head,
                         "events_replayed": replayed.events_replayed,
                         "matches_posterior": replayed.world.digest() == session.world.digest()}}
    (output / "cycle.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"selected": forecast_plan["selected"], "before": forecast_plan["baseline"],
                      "after": after["baseline"], "output": str(output)}, indent=2))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "continuous-clearance-out")
