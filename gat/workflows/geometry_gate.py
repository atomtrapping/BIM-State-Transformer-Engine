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
from gat.engine.verify import VerificationReport  # noqa: F401  (annotation)
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
    if check.kind is AcceptanceCheckKind.CAPACITY:
        # A capacity verdict has no safe default support. Dimensional
        # quantities do not establish a section modulus, so an undeclared
        # capacity check is insufficient rather than QUANTITY_ONLY.
        return GeometryAuthority.INSUFFICIENT
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
    #: Constraints that hold at the mean but not across enough of the
    #: posterior to rely on, as ``(subject, p_holds)``. Empty when no
    #: verification report was supplied.
    variant_constraints: tuple[tuple[str, float], ...] = ()

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
        payload["variant_constraints"] = [
            {"subject": subject, "p_holds": p_holds}
            for subject, p_holds in self.variant_constraints
        ]
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
    verification: "VerificationReport | None" = None,
) -> GatedAcceptanceOutcome:
    """Apply the case policy, the geometry gate, and the invariant gate.

    ``verification`` is the report for the world the checks were scored on.
    Supply it and a constraint that is merely *variant* -- true of the mean,
    but not of enough of the posterior -- blocks authorization and becomes an
    evidence request. Omit it and the invariant gate simply does not run,
    which is the pre-existing behaviour.
    """
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

    require_invariants = getattr(
        policy, "require_invariant_constraints_for_accept", True
    )
    variant: tuple[tuple[str, float], ...] = ()
    if verification is not None:
        variant = tuple(
            (result.subject, result.p_holds)
            for result in verification.warnings
            if result.p_holds is not None
        )

    disposition = outcome.disposition
    reasons = list(outcome.reasons)
    generated = list(outcome.evidence_requests)

    if variant and require_invariants and disposition is AcceptanceDisposition.ACCEPT:
        disposition = AcceptanceDisposition.REQUEST_EVIDENCE
        worst = min(p for _, p in variant)
        reasons.append(
            f"{len(variant)} constraint(s) hold at the mean but not across the "
            f"posterior; the weakest holds with P = {worst:.6f}"
        )
    if variant and disposition is not AcceptanceDisposition.REJECT:
        known = {request.check_id for request in generated}
        for subject, p_holds in variant:
            # A variant constraint is not owned by any one check, so the
            # request is raised against the case itself.
            request_id = f"{case.case_id}:variant"
            if request_id in known:
                continue
            generated.append(
                EvidenceRequest(
                    request_id,
                    "MEASURE_VARIANT_CONSTRAINT",
                    subject,
                    (
                        "this constraint holds at the mean but only with "
                        f"P = {p_holds:.6f}; measure its variables to make it "
                        "invariant or to refute it"
                    ),
                    priority=1.0 - p_holds,
                )
            )
            known.add(request_id)

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

    # Both gates may have appended; order the whole set once, highest
    # priority first, so the caller sees a single ranked ask.
    generated.sort(key=lambda item: (-item.priority, item.check_id, item.action))

    return GatedAcceptanceOutcome(
        base=outcome,
        disposition=disposition,
        reasons=tuple(reasons),
        evidence_requests=tuple(generated),
        insufficient_geometry_check_ids=insufficient,
        variant_constraints=variant,
    )


import gat.workflows.acceptance as _acceptance_module

_acceptance_module.evaluate_acceptance_case = evaluate_acceptance_case  # type: ignore[misc]
