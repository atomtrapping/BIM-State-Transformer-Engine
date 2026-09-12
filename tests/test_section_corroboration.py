"""A declared section modulus is not a measured one, and must say so.

The shipped beam model declares its plastic section modulus in a
GAT_Structural property set. Before this contract existed the beam record
simply claimed SWEPT_SOLID for it -- on a file that carried no body
representation at all -- and no capacity verdict passed through the geometry
gate, so the claim cost nothing to make. The model now carries a W360X57
swept solid, so the declaration is checked against geometry the file actually
contains.

A capacity check now declares its support explicitly. A bare declaration is
DECLARED_PROPERTY and closes nothing. When the model's own swept solid
brackets the declaration through the shape factor Z/S, it becomes
DECLARED_CORROBORATED and may close a capacity case -- never a clearance one.
"""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path

import gat.demo
from gat.adapters.ifc.beam_geometry import derive_beam_geometry
from gat.adapters.ifc.parser import parse_ifc
from gat.adapters.ifc.reader import global_id
from gat.adapters.ifc.scope import IfcLoweringScope
from gat.engineering import BeamBendingCheck, BeamBendingEvaluator
from gat.engineering.section_corroboration import (
    SHAPE_FACTOR_BOUNDS,
    corroborate_beam_section,
    corroborate_plastic_modulus,
)
from gat.session import GatSession
from gat.workflows import (
    AcceptanceCase,
    AcceptancePolicy,
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    WorkflowKind,
    capacity_check,
    evaluate_acceptance_case,
)
from gat.workflows.geometry_authority import GeometryAuthority, geometry_sufficient
from gat.workflows.geometry_gate import check_geometry_authority


BEAM_MODEL = Path(gat.demo.__file__).parent / "beam_model.ifc"
CORPUS = os.environ.get("GAT_IFC_VALIDATION_ROOT")
CLINIC_FILE = "buildingSMART-Clinic-Structural.ifc"
CLINIC_BEAM = "2Uhw1he2z3UO$DBmBugLyy"

#: A W460x60-shaped I section: d=455, bf=153, tf=13.3, tw=8 (mm), in metres.
#: Its derived elastic modulus lands near the handbook Sx for that shape.
I_SECTION_BEAM = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('i section'),'2;1');
FILE_NAME('i.ifc','2026-09-01T00:00:00',(),(),'','','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('P',$,'P',$,$,$,$,$,#10);
#10=IFCUNITASSIGNMENT((#11,#12));
#11=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#12=IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.);
#100=IFCBEAM('ISECTION-BEAM-GID',$,'I Beam',$,$,$,#101,$);
#101=IFCPRODUCTDEFINITIONSHAPE($,$,(#102,#103));
#102=IFCSHAPEREPRESENTATION($,'Axis','Curve2D',(#104));
#103=IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#107));
#104=IFCPOLYLINE((#105,#106));
#105=IFCCARTESIANPOINT((0.,0.));
#106=IFCCARTESIANPOINT((7.28,0.));
#107=IFCEXTRUDEDAREASOLID(#108,$,#109,7.28);
#108=IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,$,#110);
#109=IFCDIRECTION((0.,0.,1.));
#110=IFCPOLYLINE((#200,#201,#202,#203,#204,#205,#206,#207,#208,#209,#210,#211,#200));
#200=IFCCARTESIANPOINT((-0.0765,-0.2275));
#201=IFCCARTESIANPOINT((0.0765,-0.2275));
#202=IFCCARTESIANPOINT((0.0765,-0.2142));
#203=IFCCARTESIANPOINT((0.004,-0.2142));
#204=IFCCARTESIANPOINT((0.004,0.2142));
#205=IFCCARTESIANPOINT((0.0765,0.2142));
#206=IFCCARTESIANPOINT((0.0765,0.2275));
#207=IFCCARTESIANPOINT((-0.0765,0.2275));
#208=IFCCARTESIANPOINT((-0.0765,0.2142));
#209=IFCCARTESIANPOINT((-0.004,0.2142));
#210=IFCCARTESIANPOINT((-0.004,-0.2142));
#211=IFCCARTESIANPOINT((-0.0765,-0.2142));
ENDSEC;
END-ISO-10303-21;
"""


def _derived_elastic_modulus(source: str) -> float:
    file = parse_ifc(source)
    result = derive_beam_geometry(
        file,
        file.by_type("IFCBEAM")[0],
        source_ifc_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )
    assert result.section_modulus_major is not None
    return result.section_modulus_major.value


class ShapeFactorBracketTests(unittest.TestCase):
    """Z/S is a physical ratio, so the bracket has physical endpoints."""

    def setUp(self) -> None:
        self.elastic = _derived_elastic_modulus(I_SECTION_BEAM)

    def test_a_plausible_wide_flange_declaration_is_corroborated(self) -> None:
        result = corroborate_plastic_modulus(
            1.14 * self.elastic, self.elastic, geometry_status="COMPLETE"
        )
        self.assertTrue(result.corroborated)
        self.assertIs(result.authority, GeometryAuthority.DECLARED_CORROBORATED)
        self.assertAlmostEqual(result.shape_factor, 1.14, places=9)

    def test_a_declaration_below_the_geometric_floor_is_refused(self) -> None:
        """Z >= S for any solid section, so Z < S cannot describe this solid."""
        result = corroborate_plastic_modulus(
            0.95 * self.elastic, self.elastic, geometry_status="COMPLETE"
        )
        self.assertFalse(result.corroborated)
        self.assertIs(result.authority, GeometryAuthority.DECLARED_PROPERTY)
        self.assertIn("geometric floor", result.reason)

    def test_a_rectangle_shape_factor_is_refused_for_a_wide_flange(self) -> None:
        """1.5 is a filled rectangle, not a rolled shape."""
        result = corroborate_plastic_modulus(
            1.5 * self.elastic, self.elastic, geometry_status="COMPLETE"
        )
        self.assertFalse(result.corroborated)
        self.assertIn("solid-rectangle limit", result.reason)

    def test_a_unit_error_is_caught(self) -> None:
        """The error that actually happens: Z given in mm^3, not m^3."""
        result = corroborate_plastic_modulus(
            1.14 * self.elastic * 1e9, self.elastic, geometry_status="COMPLETE"
        )
        self.assertFalse(result.corroborated)
        self.assertIs(result.authority, GeometryAuthority.DECLARED_PROPERTY)

    def test_without_a_solid_there_is_nothing_to_check_against(self) -> None:
        for status in ("BLOCKED", "LENGTH_ONLY"):
            with self.subTest(status=status):
                result = corroborate_plastic_modulus(
                    1.14 * self.elastic, None, geometry_status=status
                )
                self.assertFalse(result.corroborated)
                self.assertIs(result.authority, GeometryAuthority.DECLARED_PROPERTY)
                self.assertIn(status, result.reason)

    def test_a_nonsense_declaration_is_insufficient(self) -> None:
        for declared in (0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(declared=declared):
                result = corroborate_plastic_modulus(
                    declared, self.elastic, geometry_status="COMPLETE"
                )
                self.assertIs(result.authority, GeometryAuthority.INSUFFICIENT)

    def test_the_bracket_endpoints_are_inclusive(self) -> None:
        low, high = SHAPE_FACTOR_BOUNDS
        for factor in (low, high):
            with self.subTest(factor=factor):
                result = corroborate_plastic_modulus(
                    factor * self.elastic, self.elastic, geometry_status="COMPLETE"
                )
                self.assertTrue(result.corroborated)


class AuthoritySemanticsTests(unittest.TestCase):
    def test_a_bare_declaration_closes_nothing(self) -> None:
        authority = GeometryAuthority.DECLARED_PROPERTY
        self.assertFalse(geometry_sufficient("CAPACITY", authority))
        self.assertFalse(geometry_sufficient("CLEARANCE", authority))

    def test_a_corroborated_declaration_closes_capacity_but_not_clearance(self) -> None:
        authority = GeometryAuthority.DECLARED_CORROBORATED
        self.assertTrue(geometry_sufficient("CAPACITY", authority))
        self.assertFalse(
            geometry_sufficient("CLEARANCE", authority),
            "a section property says nothing about as-built clearance",
        )

    def test_an_undeclared_capacity_check_fails_closed(self) -> None:
        """Dimensional quantities do not establish a section modulus."""
        check = AcceptanceCheck(
            check_id="bare",
            kind=AcceptanceCheckKind.CAPACITY,
            subject="undeclared capacity",
            verdict="SATISFIED",
            confidence=0.95,
            p_satisfies_lower=0.99,
            p_satisfies_upper=0.99,
            world_digest="0" * 64,
        )
        self.assertIs(
            check_geometry_authority(check), GeometryAuthority.INSUFFICIENT
        )


class ShippedBeamGateTests(unittest.TestCase):
    """The flagship capacity check, through the gate it never used to reach."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.session = GatSession.load_ifc(str(BEAM_MODEL))
        cls.beam = cls.session.entity_by_name("Beam-B1")
        cls.result = BeamBendingEvaluator().evaluate(
            cls.session.world,
            BeamBendingCheck(cls.beam, 301_000.0, 0.95, "Beam-B1 factored bending"),
        )
        cls.corroboration = corroborate_beam_section(
            cls.session.world,
            cls.session.source_file,
            cls.beam,
            source_ifc_sha256=hashlib.sha256(BEAM_MODEL.read_bytes()).hexdigest(),
        )

    def _case(self) -> AcceptanceCase:
        return AcceptanceCase(
            "beam-b1-capacity",
            WorkflowKind.OPENING_VERIFICATION,
            "Beam-B1 factored bending",
            (
                capacity_check(
                    "beam-b1-bending",
                    self.result,
                    self.corroboration.authority,
                    support=self.corroboration.to_dict(),
                ),
            ),
        )

    def test_the_shipped_beam_solid_corroborates_its_declaration(self) -> None:
        self.assertTrue(self.corroboration.corroborated, self.corroboration.reason)
        self.assertIs(
            self.corroboration.authority, GeometryAuthority.DECLARED_CORROBORATED
        )
        low, high = SHAPE_FACTOR_BOUNDS
        self.assertLess(low, self.corroboration.shape_factor)
        self.assertLess(self.corroboration.shape_factor, high)

    def test_the_declared_modulus_exceeds_the_derived_elastic_one(self) -> None:
        """Z >= S, always. If this inverts, the two were confused somewhere."""
        self.assertGreater(
            self.corroboration.declared_plastic_modulus_m3,
            self.corroboration.derived_elastic_modulus_m3,
        )

    def test_as_built_still_requests_evidence_but_not_for_want_of_support(self) -> None:
        self.assertEqual(self.result.verdict.value, "SATISFIED")
        outcome = evaluate_acceptance_case(self._case())
        self.assertIs(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertFalse(outcome.may_authorize)
        self.assertEqual(list(outcome.insufficient_geometry_check_ids), [])

    def test_design_review_can_accept_once_the_declaration_is_corroborated(self) -> None:
        outcome = evaluate_acceptance_case(
            self._case(),
            policy=AcceptancePolicy(
                "design-review-v1", require_verified_evidence_for_accept=False
            ),
        )
        self.assertIs(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertTrue(outcome.may_authorize)

    def test_design_review_is_still_refused_on_a_bare_declaration(self) -> None:
        """Waiving field evidence does not waive support."""
        bare = capacity_check(
            "beam-b1-bending",
            self.result,
            GeometryAuthority.DECLARED_PROPERTY,
        )
        case = AcceptanceCase(
            "beam-b1-capacity",
            WorkflowKind.OPENING_VERIFICATION,
            "Beam-B1 factored bending",
            (bare,),
        )
        outcome = evaluate_acceptance_case(
            case,
            policy=AcceptancePolicy(
                "design-review-v1", require_verified_evidence_for_accept=False
            ),
        )
        self.assertIs(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(
            list(outcome.insufficient_geometry_check_ids), ["beam-b1-bending"]
        )


class ClinicCorroborationTests(unittest.TestCase):
    """A real model with a real solid: the contrast the shipped beam lacks."""

    @unittest.skipUnless(CORPUS, "public IFC corpus not fetched")
    def test_a_real_solid_corroborates_a_plausible_declaration(self) -> None:
        path = Path(CORPUS) / CLINIC_FILE
        session = GatSession.load_ifc(
            str(path), scope=IfcLoweringScope(frozenset({CLINIC_BEAM}))
        )
        file = session.source_file
        beam = next(
            candidate
            for candidate in file.by_type("IFCBEAM")
            if global_id(candidate) == CLINIC_BEAM
        )
        geometry = derive_beam_geometry(
            file,
            beam,
            source_ifc_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        self.assertEqual(str(geometry.status), "COMPLETE")
        elastic = geometry.section_modulus_major.value

        # The handbook plastic modulus for a W460X60 is about 1.29e-3 m3.
        corroborated = corroborate_plastic_modulus(
            1.29e-3, elastic, geometry_status="COMPLETE"
        )
        self.assertTrue(corroborated.corroborated, corroborated.reason)
        self.assertIs(
            corroborated.authority, GeometryAuthority.DECLARED_CORROBORATED
        )

        # The same beam has no declared modulus of its own, so the world-level
        # bridge reports that rather than inventing one.
        bridged = corroborate_beam_section(
            session.world,
            file,
            next(iter(session.world.module.entities)),
            source_ifc_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        self.assertIs(bridged.authority, GeometryAuthority.INSUFFICIENT)
        self.assertIn("declares no plastic section modulus", bridged.reason)


if __name__ == "__main__":
    unittest.main()
