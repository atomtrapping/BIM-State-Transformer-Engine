"""Scoped lowering produces a world without swallowing the rest of the file."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest

import gat.demo
from gat.adapters.ifc.beam_geometry import derive_beam_geometry
from gat.adapters.ifc.lower import lower_ifc
from gat.adapters.ifc.parser import parse_ifc_file
from gat.adapters.ifc.reader import global_id
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.engine.executor import World
from gat.errors import LoweringError
from gat.session import GatSession


BEAM_MODEL = Path(gat.demo.__file__).parent / "beam_model.ifc"
OFFICE = Path(gat.demo.__file__).parent / "model.ifc"
CORPUS = os.environ.get("GAT_IFC_VALIDATION_ROOT")
CLINIC_BEAM = "2Uhw1he2z3UO$DBmBugLyy"
CLINIC_FILE = "buildingSMART-Clinic-Structural.ifc"
SCOPED_WORLD_RECORD = (
    Path(__file__).resolve().parent.parent
    / "validation"
    / "clinic-w460x60-scoped-world-v1.json"
)


class ScopedWorldTests(unittest.TestCase):
    def test_explicit_beam_scope_on_the_shipped_model(self) -> None:
        session = GatSession.load_ifc(
            str(BEAM_MODEL),
            scope=IfcLoweringScope(frozenset({"GATBEAMELEMENT00000100"})),
        )
        self.assertEqual(len(session.world.module.entities), 1)
        self.assertTrue(session.verify().passed)
        self.assertEqual(
            session.world.module.meta["lowering_scope"],
            ["GATBEAMELEMENT00000100"],
        )

    def test_unknown_scope_id_fails_closed(self) -> None:
        with self.assertRaisesRegex(LoweringError, "absent"):
            GatSession.load_ifc(
                str(OFFICE),
                scope=IfcLoweringScope(frozenset({"not-a-real-global-id"})),
            )

    def test_office_unscoped_load_still_works(self) -> None:
        session = GatSession.load_ifc(str(OFFICE))
        self.assertGreater(len(session.world.module.entities), 1)
        self.assertIsNone(session.world.module.meta.get("lowering_scope"))

    @unittest.skipUnless(CORPUS, "public IFC corpus not fetched")
    def test_clinic_w460x60_gets_a_world_digest(self) -> None:
        path = Path(CORPUS) / "buildingSMART-Clinic-Structural.ifc"
        session = GatSession.load_ifc(
            str(path),
            scope=IfcLoweringScope(frozenset({CLINIC_BEAM})),
        )
        entity = next(iter(session.world.module.entities))
        self.assertEqual(entity.global_id, CLINIC_BEAM)
        self.assertIn("Length", session.world.module.entities[entity].slots)
        self.assertNotIn(
            "YieldStrengthMPa", session.world.module.entities[entity].slots
        )
        self.assertTrue(session.verify().passed)
        self.assertEqual(len(session.world.digest()), 64)

    def test_scope_without_the_defining_storey_fails_closed(self) -> None:
        """A wall's Height is the storey's ClearHeight; it cannot be orphaned."""
        wall = next(
            eid.global_id
            for eid in GatSession.load_ifc(str(OFFICE)).world.module.entities
            if eid.ifc_class == "IfcWall"
        )
        with self.assertRaisesRegex(LoweringError, "ClearHeight"):
            GatSession.load_ifc(str(OFFICE), scope=IfcLoweringScope(frozenset({wall})))

    def test_scope_is_part_of_world_identity(self) -> None:
        """Two scopes over one file must not collide on a digest."""
        beam = GatSession.load_ifc(
            str(BEAM_MODEL),
            scope=IfcLoweringScope(frozenset({"GATBEAMELEMENT00000100"})),
        )
        whole = GatSession.load_ifc(str(BEAM_MODEL))
        self.assertNotEqual(beam.world.digest(), whole.world.digest())

    @unittest.skipUnless(CORPUS, "public IFC corpus not fetched")
    def test_clinic_scoped_world_matches_the_measured_record(self) -> None:
        """Every claim in the shipped record is re-measured here."""
        record = json.loads(SCOPED_WORLD_RECORD.read_text())
        path = Path(CORPUS) / CLINIC_FILE
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), record["source_ifc_sha256"])

        # The world digest includes the source string, so the record pins the
        # label it was measured with rather than a machine-specific path.
        file = parse_ifc_file(str(path))
        module = lower_ifc(
            file,
            source=record["source_label"],
            scope=IfcLoweringScope(frozenset({record["beam_global_id"]})),
        )
        world = World.compile(module)
        self.assertEqual(module.digest(), record["module_digest"])
        self.assertEqual(world.digest(), record["world_digest"])
        self.assertEqual(world.binding.n_raw, record["raw_variables"])

        entity = next(iter(module.entities))
        self.assertEqual(sorted(module.entities[entity].slots), record["slots"])
        self.assertEqual(
            "YieldStrengthMPa" in module.entities[entity].slots,
            record["has_yield_strength"],
        )

        # The body is a complete solid — the refusal to state capacity is a
        # missing *material* certificate, not missing geometry.
        beam = next(
            b for b in file.by_type("IFCBEAM")
            if global_id(b) == record["beam_global_id"]
        )
        geometry = derive_beam_geometry(
            file, beam, source_ifc_sha256=record["source_ifc_sha256"]
        )
        self.assertEqual(str(geometry.status), record["geometry_status"])
        self.assertEqual(geometry.beam_name, record["beam_name"])
        self.assertEqual(
            geometry.axis_length.value, record["derived_axis_length_m"]
        )
        self.assertEqual(
            geometry.section_modulus_major.value,
            record["derived_section_modulus_major_m3"],
        )
        self.assertFalse(record["may_authorize_capacity"])


if __name__ == "__main__":
    unittest.main()
