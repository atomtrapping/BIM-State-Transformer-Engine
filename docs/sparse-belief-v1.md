# Sparse / factor-graph belief plan v1

Status: plan. Dense covariance remains the verified oracle.

## Problem

v0 stores raw and full covariance as dense `float64` arrays. Incremental
pushforward already avoids recomputing unchanged rows, but the resident
state is still O(n²). That is acceptable for the demo IFC and the clinic
beam inventory's *quantities*. It is not acceptable as the product belief
for a storey of MEP plus scan latents.

## Decision

1. Keep dense Σ as the bitwise oracle used by snapshot / OpenUSD
   continuation tests on small worlds.
2. Do not replace that oracle with an approximate sparse path that can
   change a world digest.
3. Next implementation, when needed, is a factor graph whose cliques
   follow IFC relationships already in the IR:

   - `IfcRelContainedInSpatialStructure` (storey / space)
   - `IfcRelConnects` / port connectivity
   - `IfcRelVoidsElement` / openings
   - assembly membership

4. Observation updates factorize through the clique that owns the
   measured variables. Cross-storey correlation is explicit or absent,
   never a dense accident.

## Non-goals

- Learned precision structure
- Dropping verification because a sparse solve was cheaper
- Shipping two incompatible digest identities

## Exit test

A world with several hundred raw variables must report resident memory
and Cholesky cost on the dense path (`python -m gat.demo.incremental_scale`)
and a later sparse path must match dense means to the stated tolerance
on a fixture small enough that both run. Digests may differ across
representations only through an explicit carrier version bump.
