"""Optional IfcOpenShell adapter — second loader, not the authority.

The hand-written ``gat.adapters.ifc`` path remains fail-closed and
authoritative. This module exists so a later implementation can
differential-test quantities and pull solids/voids GAT does not yet read.

v0 inventories products and compares beam GlobalIds. It never claims
section or clearance authority.
"""

from __future__ import annotations

from dataclasses import dataclass


class IfcOpenShellAdapterError(RuntimeError):
    """Raised when the optional adapter cannot be used honestly."""


def ifcopenshell_available() -> bool:
    try:
        import ifcopenshell  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True)
class IfcOpenShellInventory:
    path: str
    schema: str
    product_count: int
    beam_global_ids: tuple[str, ...]
    geometry_authority: str = "INSUFFICIENT"


def inventory_with_ifcopenshell(path: str) -> IfcOpenShellInventory:
    """Open a file for identity inventory only. Never invent section properties."""
    if not ifcopenshell_available():
        raise IfcOpenShellAdapterError(
            "ifcopenshell is not installed; pip install '.[ifcopenshell]'"
        )
    import ifcopenshell

    model = ifcopenshell.open(path)
    beams = tuple(
        beam.GlobalId
        for beam in model.by_type("IfcBeam")
        if getattr(beam, "GlobalId", None)
    )
    products = model.by_type("IfcProduct")
    return IfcOpenShellInventory(
        path=path,
        schema=str(model.schema),
        product_count=len(products),
        beam_global_ids=beams,
        geometry_authority="INSUFFICIENT",
    )


@dataclass(frozen=True)
class IdentityDiff:
    """GlobalId comparison. Never a quantity or solid authority."""

    path: str
    ifcopenshell_schema: str
    gat_beam_ids: tuple[str, ...]
    ios_beam_ids: tuple[str, ...]
    only_in_gat: tuple[str, ...]
    only_in_ifcopenshell: tuple[str, ...]
    in_both: tuple[str, ...]
    geometry_authority: str = "INSUFFICIENT"

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "ifcopenshell_schema": self.ifcopenshell_schema,
            "gat_beam_count": len(self.gat_beam_ids),
            "ifcopenshell_beam_count": len(self.ios_beam_ids),
            "only_in_gat": list(self.only_in_gat),
            "only_in_ifcopenshell": list(self.only_in_ifcopenshell),
            "in_both": list(self.in_both),
            "geometry_authority": self.geometry_authority,
        }


def gat_beam_global_ids(path: str) -> tuple[str, ...]:
    from gat.adapters.ifc.parser import parse_ifc_file
    from gat.adapters.ifc.reader import global_id

    file = parse_ifc_file(path)
    ids = []
    for beam in file.by_type("IFCBEAM"):
        gid = global_id(beam)
        if gid:
            ids.append(gid)
    return tuple(ids)


def identity_diff(path: str) -> IdentityDiff:
    """Compare beam GlobalIds. Does not copy quantities from IfcOpenShell."""
    inventory = inventory_with_ifcopenshell(path)
    gat_ids = gat_beam_global_ids(path)
    gat_set = set(gat_ids)
    ios_set = set(inventory.beam_global_ids)
    return IdentityDiff(
        path=path,
        ifcopenshell_schema=inventory.schema,
        gat_beam_ids=gat_ids,
        ios_beam_ids=inventory.beam_global_ids,
        only_in_gat=tuple(sorted(gat_set - ios_set)),
        only_in_ifcopenshell=tuple(sorted(ios_set - gat_set)),
        in_both=tuple(sorted(gat_set & ios_set)),
    )
