"""Inventory IFC-shaped sparse factors. Dense Σ remains the digest oracle.

This does not replace ``propagate``. It counts cliques implied by IR
relationships and lifts the raw belief into information form so scale
probes can compare resident sparse entries against the dense ``n^2``
footprint without changing a world digest.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from gat.engine.executor import World
from gat.gaussian.information import SparseInformationBelief, from_world
from gat.ir.core import RelKind


@dataclass(frozen=True)
class SparseFactorInventory:
    world_digest: str
    raw_variables: int
    dense_covariance_entries: int
    contains_cliques: int
    voids_cliques: int
    fills_cliques: int
    isolated_entities: int
    precision_nnz: int
    precision_components: int
    largest_component: int
    sparse_resident_bytes: int
    dense_resident_bytes: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "world_digest": self.world_digest,
            "raw_variables": self.raw_variables,
            "dense_covariance_entries": self.dense_covariance_entries,
            "contains_cliques": self.contains_cliques,
            "voids_cliques": self.voids_cliques,
            "fills_cliques": self.fills_cliques,
            "isolated_entities": self.isolated_entities,
            "precision_nnz": self.precision_nnz,
            "precision_components": self.precision_components,
            "largest_component": self.largest_component,
            "sparse_resident_bytes": self.sparse_resident_bytes,
            "dense_resident_bytes": self.dense_resident_bytes,
            "oracle": "dense-float64",
            "working_representation": "sparse-information-v0",
        }


def inventory_sparse_factors(world: World) -> SparseFactorInventory:
    members: dict[str, set[str]] = defaultdict(set)
    related: set[str] = set()
    for rel in world.module.rels:
        if rel.kind is RelKind.CONTAINS:
            members[f"contains:{rel.source.global_id}"].add(rel.target.global_id)
            related.update((rel.source.global_id, rel.target.global_id))
        elif rel.kind is RelKind.VOIDS:
            members[f"voids:{rel.target.global_id}"].add(rel.source.global_id)
            related.update((rel.source.global_id, rel.target.global_id))
        elif rel.kind is RelKind.FILLS:
            members[f"fills:{rel.source.global_id}"].add(rel.target.global_id)
            related.update((rel.source.global_id, rel.target.global_id))
    raw = world.binding.n_raw
    entity_ids = {entity.global_id for entity in world.module.entities}
    isolated = len(entity_ids - related)
    info = from_world(world)
    components = info.components()
    full = world.binding.n_full
    dense_bytes = 8 * (raw + raw * raw + full + full * full + 2 * full * raw)
    return SparseFactorInventory(
        world_digest=world.digest(),
        raw_variables=raw,
        dense_covariance_entries=raw * raw,
        contains_cliques=sum(1 for key in members if key.startswith("contains:")),
        voids_cliques=sum(1 for key in members if key.startswith("voids:")),
        fills_cliques=sum(1 for key in members if key.startswith("fills:")),
        isolated_entities=isolated,
        precision_nnz=info.nnz,
        precision_components=len(components),
        largest_component=max((len(component) for component in components), default=0),
        sparse_resident_bytes=info.resident_bytes(),
        dense_resident_bytes=dense_bytes,
    )


def information_belief(world: World) -> SparseInformationBelief:
    """Lift the current raw belief. Does not replace World.belief."""
    return from_world(world)
