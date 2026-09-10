"""Decision-scoped IFC lowering.

Whole-file v0 lowering still requires exactly one storey and every
supported product in the file. That blocks public multi-storey models
that already have usable beam geometry. A scope names the GlobalIds that
may become world entities. Anything else stays audit-only.

Off-scope dependencies never silently join the world. A later acceptance
request that names an absent entity fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IfcLoweringScope:
    """Restrict lowering to an explicit subject set."""

    include_global_ids: frozenset[str]
    allow_derived_beam_length: bool = True

    def __post_init__(self) -> None:
        if not self.include_global_ids:
            raise ValueError("lowering scope must name at least one GlobalId")
        object.__setattr__(
            self,
            "include_global_ids",
            frozenset(value.strip() for value in self.include_global_ids if value.strip()),
        )
        if not self.include_global_ids:
            raise ValueError("lowering scope GlobalIds must be non-empty text")
        if not isinstance(self.allow_derived_beam_length, bool):
            raise ValueError("allow_derived_beam_length must be boolean")

    def admits(self, global_id: str) -> bool:
        return global_id in self.include_global_ids
