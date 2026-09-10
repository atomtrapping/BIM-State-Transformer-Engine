"""Apply geometry authority after the numerical acceptance policy.

This wrapper is the public evaluate path. Gaussianized clearance without
openings subtracted cannot close an as-built case. A verified scan receipt
upgrades that check to SCAN_GMM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from gat.workflows.acceptance import (
    AcceptanceCheck,
    AcceptanceCheckKind,
    AcceptanceDisposition,
    AcceptanceOutcome,
    AcceptancePolicy,
    EvidenceReceipt,
    EvidenceRequest,
)
from gat.workflows.acceptance import (
    evaluate_acceptance_case as evaluate_acceptance_case_ungated,
)
from gat.workflows.geometry_authority import (
    GeometryAuthority,
    geometry_sufficient,
)


def check_geometry_authority(check: AcceptanceCheck) -> GeometryAuthority:
    raw = check.details.get("geometry_authority")
    if raw is not None:
        return GeometryAuthority(str(raw))
    if check.kind is AcceptanceCheckKind.CLEARANCE:
        return GeometryAuthority.GAUSSIAN_PROXY
    return GeometryAuthority.QUANTITY_ONLY


def annotate_check(check: AcceptanceCheck) -> dict[str, object]:
    from gat.workflows.acceptance import acceptance_check_dict

    payload = acceptance_check_dict(check)
    payload["geometry_authority"] = check_geometry_authority(check).value
    return payload


@dataclass(frozen=True)
class GatedAcceptanceOutcome:
    """AcceptanceOutcome plus geometry-authority fields on the contract."""

    base: AcceptanceOutcome
    disposition: AcceptanceDisposition
    reasons: tuple[str, ...]
    evidence_requests: tuple[EvidenceRequest, ...]
    insufficient_geometry_check_ids: tuple[str, ...]

    def __getattr__(self, name: str) -> object:
        return getattr(self.base, name)

    @property
    def may_authorize(self) -> bool:
        return self.disposition is AcceptanceDisposition.ACCEPT

    def to_dict(self) -> dict[str, object]:
        payload = self.base.to_dict()
        payload["disposition"] = self.disposition.value
        payload["may_authorize"] = self.may_authorize
        payload["reasons"] = list(self.reasons)
        payload["insufficient_geometry_check_ids"] = list(
            self.insufficient_geometry_check_ids
        )
        payload["evidence_requests"] = [
            {
                "check_id": request.check_id,
                "action": request.action,
                "target": request.target,
                "reason": request.reason,
                "priority": request.priority,
            }
            for request in self.evidence_requests
        ]
        payload["checks"] = [annotate_check(check) for check in self.base.case.checks]
        return payload


def evaluate_acceptance_case(
    case,
    receipts: Iterable[EvidenceReceipt] = (),
    requests: Iterable[EvidenceRequest] = (),
    policy: AcceptancePolicy = AcceptancePolicy(),
) -> GatedAcceptanceOutcome:
    receipts = tuple(receipts)
    outcome = evaluate_acceptance_case_ungated(case, receipts, requests, policy)
    scan_covered: set[str] = set()
    for receipt in receipts:
        if (
            receipt.verification_passed
            and receipt.evidence_kind == "calibrated-scan-clearance-likelihood"
        ):
            scan_covered.update(receipt.check_ids)

    require_geometry = getattr(policy, "require_sufficient_geometry_for_accept", True)
    insufficient = (
        tuple(
            check.check_id
            for check in case.checks
            if not geometry_sufficient(
                check.kind.value,
                check_geometry_authority(check),
                scan_covered=check.check_id in scan_covered,
            )
        )
        if require_geometry
        else ()
    )

    disposition = outcome.disposition
    reasons = list(outcome.reasons)
    generated = list(outcome.evidence_requests)
    if insufficient and disposition is AcceptanceDisposition.ACCEPT:
        disposition = AcceptanceDisposition.REQUEST_EVIDENCE
        reasons.append(
            "one or more checks lack geometric authority to close the case"
        )
    if insufficient and disposition is not AcceptanceDisposition.REJECT:
        known = {request.check_id for request in generated}
        for check in case.checks:
            if check.check_id in insufficient and check.check_id not in known:
                generated.append(
                    EvidenceRequest(
                        check.check_id,
                        "ACQUIRE_CALIBRATED_EVIDENCE",
                        check.subject,
                        (
                            "geometry authority is insufficient for this check; "
                            f"current support is {check_geometry_authority(check).value}"
                        ),
                    )
                )
        generated.sort(key=lambda item: (-item.priority, item.check_id, item.action))

    return GatedAcceptanceOutcome(
        base=outcome,
        disposition=disposition,
        reasons=tuple(reasons),
        evidence_requests=tuple(generated),
        insufficient_geometry_check_ids=insufficient,
    )
