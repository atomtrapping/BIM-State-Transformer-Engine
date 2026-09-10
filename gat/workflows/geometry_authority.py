"""Geometry authority codes for GAT checks.

These codes are part of the public decision contract. Clearance scored from
Gaussianized boxes with openings unsubtracted is GAUSSIAN_PROXY and cannot
close an as-built case by itself. Scan receipts upgrade a check to SCAN_GMM.
"""

from __future__ import annotations

from enum import StrEnum


class GeometryAuthority(StrEnum):
    SWEPT_SOLID = "SWEPT_SOLID"
    LENGTH_ONLY = "LENGTH_ONLY"
    SCAN_GMM = "SCAN_GMM"
    QUANTITY_ONLY = "QUANTITY_ONLY"
    GAUSSIAN_PROXY = "GAUSSIAN_PROXY"
    INSUFFICIENT = "INSUFFICIENT"


_CLEARANCE_OK = frozenset({GeometryAuthority.SWEPT_SOLID, GeometryAuthority.SCAN_GMM})
_QUANTITY_OK = frozenset(
    {
        GeometryAuthority.QUANTITY_ONLY,
        GeometryAuthority.SWEPT_SOLID,
        GeometryAuthority.SCAN_GMM,
    }
)


def authority_from_beam_status(status: str) -> GeometryAuthority:
    if status == "COMPLETE":
        return GeometryAuthority.SWEPT_SOLID
    if status == "LENGTH_ONLY":
        return GeometryAuthority.LENGTH_ONLY
    return GeometryAuthority.INSUFFICIENT


def geometry_sufficient(
    kind: str,
    authority: GeometryAuthority,
    *,
    scan_covered: bool = False,
) -> bool:
    if scan_covered:
        authority = GeometryAuthority.SCAN_GMM
    if kind == "CLEARANCE":
        return authority in _CLEARANCE_OK
    return authority in _QUANTITY_OK
