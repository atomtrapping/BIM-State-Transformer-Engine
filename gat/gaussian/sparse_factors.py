"""Inventory IFC-shaped sparse factors. Dense Σ remains the oracle.

This does not replace ``propagate``. It counts cliques implied by IR
relationships so a later sparse path has a fixture to match against.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from gat.engine.executor import World
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

    def to_dict(self) -> dict[str, int | str]:
        return {
            "world_digest": self.world_digest,
            "raw_variables": self.raw_variables,
            "dense_covariance_entries": self.dense_covariance_entries,
            "contains_cliques": self.contains_cliques,
            "voids_cliques": self.voids_cliques,
            "fills_cliques": self.fills_cliques,
            "isolated_entities": self.isolated_entities,
            "oracle": "dense-float64",
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
    return SparseFactorInventory(
        world_digest=world.digest(),
        raw_variables=raw,
        dense_covariance_entries=raw * raw,
        contains_cliques=sum(1 for key in members if key.startswith("contains:")),
        voids_cliques=sum(1 for key in members if key.startswith("voids:")),
        fills_cliques=sum(1 for key in members if key.startswith("fills:")),
        isolated_entities=isolated,
    )
