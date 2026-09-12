"""Cross-check a declared plastic section modulus against the model's solid.

A GAT_Structural property set declares ``PlasticSectionModulusMajorM3`` (Z).
The IFC geometry adapter, when the beam carries a swept solid, independently
derives the *elastic* modulus S = I/c from the profile polygon. These are two
different section properties and must never be compared for equality -- but
they are rigidly related, and that relation is enough to catch the errors
that actually occur in practice: a wrong unit, a misplaced decimal, a value
copied from the wrong row of a section table.

The relation is the shape factor::

    k = Z / S

For any solid cross-section ``Z >= S``, so ``k >= 1`` is a hard geometric
floor, not a convention: the plastic modulus takes the full first moment of
area about the equal-area axis, the elastic modulus divides the second moment
by the extreme-fibre distance. A solid rectangle -- the most efficient
possible shape factor for a filled section -- gives exactly ``k = 1.5``.
Rolled doubly-symmetric wide-flange shapes, which is what
``GAT_StructuralScope`` restricts this profile to, sit near ``k = 1.10-1.15``
because most of their area is in the flanges, far from the neutral axis.

:data:`SHAPE_FACTOR_BOUNDS` brackets that at ``[1.00, 1.30]``. The bracket is
deliberately looser than the catalogue range. It is a falsification test, not
a section lookup: the adapter discretizes the profile polygon without fillets,
and a real file's idealized outline can differ from a handbook value by a few
per cent in either direction. Widening the bracket costs almost nothing --
the errors worth catching are off by factors of a thousand, not by five per
cent -- while narrowing it would reject legitimate models.

Corroboration is not verification. A bracketed declaration is still a
declaration; it has only been shown to be consistent with a solid that the
same file asserts. It never becomes a measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gat.workflows.geometry_authority import GeometryAuthority


#: Bounds on Z/S for a doubly-symmetric wide-flange section. The lower bound
#: is the geometric floor Z >= S; the upper bound sits between the catalogue
#: range (~1.18 at the extreme) and the solid-rectangle limit of 1.5.
SHAPE_FACTOR_BOUNDS: tuple[float, float] = (1.00, 1.30)

#: The solid-rectangle shape factor, recorded so the upper bound above is
#: readable as "well short of a filled section" rather than as a magic number.
RECTANGLE_SHAPE_FACTOR = 1.5

CORROBORATION_METHOD = "gat-shape-factor-bracket-v1"


@dataclass(frozen=True)
class SectionCorroboration:
    """Whether the model's own solid brackets its declared plastic modulus."""

    authority: GeometryAuthority
    corroborated: bool
    reason: str
    declared_plastic_modulus_m3: float | None = None
    derived_elastic_modulus_m3: float | None = None
    shape_factor: float | None = None

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "authority": str(self.authority),
            "corroborated": self.corroborated,
            "method": CORROBORATION_METHOD,
            "reason": self.reason,
            "shape_factor_bounds": list(SHAPE_FACTOR_BOUNDS),
        }
        if self.declared_plastic_modulus_m3 is not None:
            record["declared_plastic_modulus_m3"] = self.declared_plastic_modulus_m3
        if self.derived_elastic_modulus_m3 is not None:
            record["derived_elastic_modulus_m3"] = self.derived_elastic_modulus_m3
        if self.shape_factor is not None:
            record["shape_factor"] = self.shape_factor
        return record


def corroborate_plastic_modulus(
    declared_plastic_modulus_m3: float,
    derived_elastic_modulus_m3: float | None,
    *,
    geometry_status: str,
) -> SectionCorroboration:
    """Bracket a declared Z against a derived S.

    ``derived_elastic_modulus_m3`` is the adapter's major-axis section
    modulus, which is elastic (``I/c``) despite the adapter's internal
    spelling. Pass ``None`` when the beam has no usable solid.

    Fails closed: anything other than a finite, positive pair that lands
    inside :data:`SHAPE_FACTOR_BOUNDS` leaves the check at
    ``DECLARED_PROPERTY``.
    """
    if not math.isfinite(declared_plastic_modulus_m3) or (
        declared_plastic_modulus_m3 <= 0.0
    ):
        return SectionCorroboration(
            GeometryAuthority.INSUFFICIENT,
            False,
            "declared plastic section modulus is not finite and positive",
        )

    if geometry_status != "COMPLETE" or derived_elastic_modulus_m3 is None:
        return SectionCorroboration(
            GeometryAuthority.DECLARED_PROPERTY,
            False,
            (
                "the model carries no swept solid to check the declaration "
                f"against (beam geometry is {geometry_status})"
            ),
            declared_plastic_modulus_m3=declared_plastic_modulus_m3,
        )

    if (
        not math.isfinite(derived_elastic_modulus_m3)
        or derived_elastic_modulus_m3 <= 0.0
    ):
        return SectionCorroboration(
            GeometryAuthority.DECLARED_PROPERTY,
            False,
            "derived elastic section modulus is not finite and positive",
            declared_plastic_modulus_m3=declared_plastic_modulus_m3,
        )

    shape_factor = declared_plastic_modulus_m3 / derived_elastic_modulus_m3
    low, high = SHAPE_FACTOR_BOUNDS
    if not low <= shape_factor <= high:
        below = shape_factor < low
        return SectionCorroboration(
            GeometryAuthority.DECLARED_PROPERTY,
            False,
            (
                f"declared Z / derived S = {shape_factor:.4g}, outside the "
                f"[{low}, {high}] shape-factor bracket for a doubly-symmetric "
                "wide-flange section; the declaration is "
                + (
                    "below the geometric floor Z >= S, so it cannot describe "
                    "this solid at all"
                    if below
                    else "too large for a rolled shape and approaches the "
                    f"solid-rectangle limit of {RECTANGLE_SHAPE_FACTOR}"
                )
            ),
            declared_plastic_modulus_m3=declared_plastic_modulus_m3,
            derived_elastic_modulus_m3=derived_elastic_modulus_m3,
            shape_factor=shape_factor,
        )

    return SectionCorroboration(
        GeometryAuthority.DECLARED_CORROBORATED,
        True,
        (
            f"declared Z / derived S = {shape_factor:.4g}, inside the "
            f"[{low}, {high}] shape-factor bracket; the model's own solid is "
            "consistent with the declared plastic modulus"
        ),
        declared_plastic_modulus_m3=declared_plastic_modulus_m3,
        derived_elastic_modulus_m3=derived_elastic_modulus_m3,
        shape_factor=shape_factor,
    )


def corroborate_beam_section(
    world,
    file,
    beam,
    *,
    source_ifc_sha256: str,
) -> SectionCorroboration:
    """Corroborate one beam's declared Z against the solid in its own file.

    ``world`` supplies the declared plastic modulus as it currently stands in
    the belief -- so a certificate that revised the section is reflected --
    and ``file`` supplies the geometry it is checked against.
    """
    from gat.adapters.ifc.beam_geometry import derive_beam_geometry
    from gat.adapters.ifc.reader import global_id
    from gat.errors import BindingError
    from gat.ids import VarId

    declared_var = VarId(beam, "PlasticSectionModulusMajorM3")
    try:
        declared = world.full.mean(declared_var)
    except BindingError:
        return SectionCorroboration(
            GeometryAuthority.INSUFFICIENT,
            False,
            f"{beam.global_id} declares no plastic section modulus",
        )

    instance = next(
        (
            candidate
            for candidate in file.by_type("IFCBEAM")
            if global_id(candidate) == beam.global_id
        ),
        None,
    )
    if instance is None:
        return SectionCorroboration(
            GeometryAuthority.DECLARED_PROPERTY,
            False,
            f"{beam.global_id} is not an IfcBeam in the supplied file",
            declared_plastic_modulus_m3=declared,
        )

    geometry = derive_beam_geometry(
        file, instance, source_ifc_sha256=source_ifc_sha256
    )
    derived = (
        geometry.section_modulus_major.value
        if geometry.section_modulus_major is not None
        else None
    )
    return corroborate_plastic_modulus(
        declared, derived, geometry_status=str(geometry.status)
    )


__all__ = [
    "CORROBORATION_METHOD",
    "RECTANGLE_SHAPE_FACTOR",
    "SHAPE_FACTOR_BOUNDS",
    "SectionCorroboration",
    "corroborate_beam_section",
    "corroborate_plastic_modulus",
]
