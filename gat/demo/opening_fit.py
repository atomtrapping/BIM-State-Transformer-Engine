"""Emit a synthetic frame-aware fit prediction and empty calibration report."""
from pathlib import Path
import json
import sys

import numpy as np

from gat.engine.executor import World
from gat.geometry.frames import CoordinateFrame, FrameGraph, RigidTransform
from gat.geometry.opening_fit import OpeningFitBinding, assess_opening_fit
from gat.geometry.fit_calibration import evaluate_held_out
from gat.ids import EntityId, VarId
from gat.ir.core import Entity, Module, QtySlot, Role, Unit


def synthetic_case():
    opening = EntityId("IfcOpeningElement", "synthetic-opening")
    assembly = EntityId("IfcBuildingElementProxy", "synthetic-assembly")
    variables = tuple(VarId(e, q) for e, q in ((opening, "Width"), (opening, "Height"),
                                             (assembly, "Width"), (assembly, "Depth"), (assembly, "Height")))
    sizes = (1.1, 2.2, 1.0, 0.1, 2.0)
    slots = {v: QtySlot(v, Role.RAW, Unit.M, size, 0.001) for v, size in zip(variables, sizes)}
    entities = {e: Entity(e, e.global_id, slots={v.quantity: s for v, s in slots.items() if v.entity == e})
                for e in (opening, assembly)}
    world = World.compile(Module(entities, (), (), {"source": "synthetic-opening-fit-v1"}))
    frames = FrameGraph([CoordinateFrame("model", None, RigidTransform.identity()),
                         CoordinateFrame("storey", "model", RigidTransform(np.eye(3), [0, 0, 3])),
                         CoordinateFrame("opening", "storey", RigidTransform(np.eye(3), [2, 1, 1.1])),
                         CoordinateFrame("assembly", "opening", RigidTransform(np.eye(3), [0.01, 0, 0]))])
    return world, frames, OpeningFitBinding("opening", "assembly", variables)


def run(output):
    world, frames, binding = synthetic_case()
    before = world.digest()
    pose = np.eye(12) * 0.001 ** 2
    report = assess_opening_fit(world, frames, binding, pose_covariance=pose,
                               raw_pose_cross_covariance=np.zeros((len(world.belief.index), 12)),
                               assumption_id="synthetic-independent-1mm-1mrad-v1", required_clearance_m=0.01)
    report_calibration = evaluate_held_out([report], [], fitting_source_ids=[])
    assert report["model_prediction"] == "SATISFIED"
    assert report["acceptance"] == "REQUEST_EVIDENCE"
    assert world.digest() == before
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, record in (("prediction", report), ("calibration", report_calibration)):
        (output / f"{name}.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Synthetic fit: SATISFIED; field acceptance: REQUEST_EVIDENCE; calibration: NO_MEASUREMENTS")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "opening-fit-out")
