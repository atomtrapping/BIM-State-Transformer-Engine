"""Scoped lowering produces a world without swallowing the rest of the file."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

import gat.demo
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.errors import LoweringError
from gat.session import GatSession


BEAM_MODEL = Path(gat.demo.__file__).parent / "beam_model.ifc"
OFFICE = Path(gat.demo.__file__).parent / "model.ifc"
CORPUS = os.environ.get("GAT_IFC_VALIDATION_ROOT")
CLINIC_BEAM = "2Uhw1he2z3UO$DBmBugLyy"


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


if __name__ == "__main__":
    unittest.main()
