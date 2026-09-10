"""Geometry authority is part of the acceptance verdict, not a footnote."""

from __future__ import annotations

import unittest

from gat.engine.decision import DecisionVerdict
from gat.workflows.acceptance import (
    AcceptanceCase,
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    AcceptancePolicy,
    GeometryAuthority,
    WorkflowKind,
    evaluate_acceptance_case,
)


def _check(
    check_id: str,
    *,
    kind: AcceptanceCheckKind = AcceptanceCheckKind.DIFFERENCE,
    verdict: DecisionVerdict = DecisionVerdict.SATISFIED,
    authority: GeometryAuthority = GeometryAuthority.QUANTITY_ONLY,
    digest: str = "a" * 64,
) -> AcceptanceCheck:
    return AcceptanceCheck(
        check_id=check_id,
        kind=kind,
        subject=check_id,
        verdict=verdict,
        confidence=0.95,
        p_satisfies_lower=0.99,
        p_satisfies_upper=0.99,
        world_digest=digest,
        geometry_authority=authority,
    )


class GeometryAuthorityTests(unittest.TestCase):
    def test_quantity_fit_can_accept_under_design_review(self) -> None:
        case = AcceptanceCase(
            "opening-1",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1",
            (_check("width"), _check("height")),
        )
        outcome = evaluate_acceptance_case(
            case,
            policy=AcceptancePolicy(
                "design-review-v1",
                require_verified_evidence_for_accept=False,
            ),
        )
        self.assertEqual(outcome.disposition, AcceptanceDisposition.ACCEPT)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ())

    def test_gaussian_proxy_cannot_close_as_built_clearance(self) -> None:
        case = AcceptanceCase(
            "route-1",
            WorkflowKind.AS_BUILT_CLEARANCE,
            "duct",
            (
                _check(
                    "route-clearance",
                    kind=AcceptanceCheckKind.CLEARANCE,
                    authority=GeometryAuthority.GAUSSIAN_PROXY,
                ),
            ),
        )
        outcome = evaluate_acceptance_case(
            case,
            policy=AcceptancePolicy(
                "design-review-v1",
                require_verified_evidence_for_accept=False,
            ),
        )
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ("route-clearance",))
        self.assertIn("geometry authority", outcome.evidence_requests[0].reason)

    def test_length_only_beam_quantity_is_not_section_authority(self) -> None:
        case = AcceptanceCase(
            "beam-1",
            WorkflowKind.PREFABRICATION_FIT,
            "beam",
            (
                _check(
                    "capacity",
                    kind=AcceptanceCheckKind.MINIMUM,
                    authority=GeometryAuthority.LENGTH_ONLY,
                ),
            ),
        )
        outcome = evaluate_acceptance_case(
            case,
            policy=AcceptancePolicy(
                "design-review-v1",
                require_verified_evidence_for_accept=False,
            ),
        )
        self.assertEqual(outcome.disposition, AcceptanceDisposition.REQUEST_EVIDENCE)
        self.assertEqual(outcome.insufficient_geometry_check_ids, ("capacity",))

    def test_outcome_dict_prints_geometry_authority(self) -> None:
        case = AcceptanceCase(
            "opening-1",
            WorkflowKind.OPENING_VERIFICATION,
            "Door-1",
            (_check("width"),),
        )
        rendered = evaluate_acceptance_case(
            case,
            policy=AcceptancePolicy(
                "design-review-v1",
                require_verified_evidence_for_accept=False,
            ),
        ).to_dict()
        self.assertEqual(rendered["checks"][0]["geometry_authority"], "QUANTITY_ONLY")
        self.assertEqual(rendered["insufficient_geometry_check_ids"], [])


if __name__ == "__main__":
    unittest.main()
