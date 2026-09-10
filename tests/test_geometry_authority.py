"""Geometry authority is part of the decision contract, not a footnote."""

from __future__ import annotations

import unittest

from gat.engine.decision import DecisionVerdict
from gat.workflows.acceptance import (
    AcceptanceCase,
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    AcceptancePolicy,
    WorkflowKind,
)
from gat.workflows.geometry_gate import evaluate_acceptance_case
from gat.workflows.geometry_authority import (
    GeometryAuthority,
    authority_from_beam_status,
    geometry_sufficient,
)


class GeometryAuthorityTests(unittest.TestCase):
    def test_quantity_fit_is_sufficient_without_solids(self) -> None:
        self.assertTrue(
            geometry_sufficient("DIFFERENCE", GeometryAuthority.QUANTITY_ONLY)
        )

    def test_gaussian_proxy_cannot_close_clearance(self) -> None:
        self.assertFalse(
            geometry_sufficient("CLEARANCE", GeometryAuthority.GAUSSIAN_PROXY)
        )

    def test_scan_receipt_upgrades_clearance(self) -> None:
        self.assertTrue(
            geometry_sufficient(
                "CLEARANCE",
                GeometryAuthority.GAUSSIAN_PROXY,
                scan_covered=True,
            )
        )

    def test_length_only_beam_is_not_section_authority(self) -> None:
        self.assertEqual(
            authority_from_beam_status("LENGTH_ONLY"),
            GeometryAuthority.LENGTH_ONLY,
        )
        self.assertFalse(
            geometry_sufficient("MINIMUM", GeometryAuthority.LENGTH_ONLY)
        )

    def test_evaluate_refuses_gaussian_proxy_clearance(self) -> None:
        check = AcceptanceCheck(
            "route-clearance",
            AcceptanceCheckKind.CLEARANCE,
            "duct",
            DecisionVerdict.SATISFIED,
            0.95,
            0.99,
            0.99,
            "a" * 64,
            details={"geometry_authority": "GAUSSIAN_PROXY"},
        )
        outcome = evaluate_acceptance_case(
            AcceptanceCase(
                "route-1",
                WorkflowKind.AS_BUILT_CLEARANCE,
                "duct",
                (check,),
            ),
            policy=AcceptancePolicy(
                "design-review-v1",
                require_verified_evidence_for_accept=False,
            ),
        )
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ("route-clearance",))
        self.assertEqual(
            outcome.to_dict()["checks"][0]["geometry_authority"], "GAUSSIAN_PROXY"
        )

    def test_complete_swept_solid_maps_to_swept_solid(self) -> None:
        self.assertEqual(
            authority_from_beam_status("COMPLETE"),
            GeometryAuthority.SWEPT_SOLID,
        )
        self.assertTrue(
            geometry_sufficient("CLEARANCE", GeometryAuthority.SWEPT_SOLID)
        )


if __name__ == "__main__":
    unittest.main()
