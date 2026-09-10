# IfcOpenShell as a second adapter (v0 plan)

Status: planned extra. Not the authoritative v0 loader.

## Why a second adapter

GAT's hand-written IFC path exists so the engine can fail closed on units,
missing quantities, and unsupported beam bodies without inheriting a large
C++ world. That personality stays.

IfcOpenShell is the practical way to differential-test the parser and to
obtain solids / openings the v0 adapter does not read. It is an adapter,
not a replacement religion.

## Contract

- Optional extra: `pip install ".[ifcopenshell]"` (package `ifcopenshell`).
- The authoritative loader remains `gat.adapters.ifc`.
- An IfcOpenShell adapter, when written, must:

  1. emit the same `EntityId` / `VarId` identities for quantities both
     loaders can see;
  2. refuse to invent section properties GAT would have marked
     `LENGTH_ONLY`;
  3. expose mesh / solid support as an explicit geometry authority
     (`SWEPT_SOLID` or `INSUFFICIENT`), including voids when present;
  4. never silently skip unsupported entities.

## v0 action

This document and the optional dependency extra are the whole delivery.
No IfcOpenShell import is required to install or test the kernel.
