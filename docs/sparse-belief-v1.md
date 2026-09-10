# Sparse / factor-graph belief plan v1

Status: information-form v0 implemented. Dense covariance remains the
verified digest oracle on small worlds.

## Problem

v0 stores raw and full covariance as dense `float64` arrays. Incremental
pushforward already avoids recomputing unchanged rows, but the resident
state is still O(n²) and a dense Cholesky is O(n³). That is acceptable
for the demo IFC. It is not acceptable as the product belief for a
storey of MEP plus scan latents.

Covariance is the wrong sparse object. A Gaussian with sparse conditional
independence still has a dense Σ. The sparse object is the precision
`Λ = Σ⁻¹` (information form).

## Decision

1. Keep dense Σ as the bitwise oracle used by snapshot / OpenUSD
   continuation tests on small worlds (`n_raw ≤ 256` before an explicit
   `to_dense()`).
2. Do not replace that oracle with an approximate sparse path that can
   change a world digest.
3. Working representation for scale is `SparseInformationBelief`:
   `η = Λμ`, `Λ` stored by nonzero entries, Cholesky only on connected
   components of `Λ`.
4. Observation updates run the existing Joseph conditioner on the
   affected component only. Cross-storey correlation is explicit
   (an off-diagonal precision entry) or absent, never a dense accident.
5. IR relationships (contains / voids / fills) remain the inventory of
   *architectural* cliques. They do not invent precision fill-in. Fill-in
   appears only after an observation whose Jacobian touches those raws.

## Non-goals

- Learned precision structure
- Dropping verification because a sparse solve was cheaper
- Shipping two incompatible digest identities
- Putting millions of scan points into the raw state. Scan points are
  evidence. Raw state is BIM quantities plus declared latents.

## Exit test

`tests/test_information.py`:

- 400 independent synthetic storeys: `nnz == n`, refuse dense materialize
- office demo prior matches dense means/variances and leaves the world
  digest unchanged
- coupled and derived observations match the Joseph path on the touched
  raw support
