# Geometry authority v1

Status: implemented on the acceptance boundary.

A probabilistic clearance or capacity number is not enough to close a case.
The check must also declare what geometric or quantity support it used.

## Codes

| Code | Meaning | Can close as-built clearance? | Can close quantity fit / beam capacity? |
|---|---|---|---|
| `SWEPT_SOLID` | IFC swept-solid body with derived section properties | yes | yes |
| `SCAN_GMM` | Calibrated scan likelihood bound to this world | yes | yes |
| `QUANTITY_ONLY` | IFC dimensional quantities / placements, no solid | no | yes |
| `LENGTH_ONLY` | Beam axis length only; no section authority | no | no |
| `GAUSSIAN_PROXY` | Oriented-box Gaussianization; openings not subtracted | no | no |
| `INSUFFICIENT` | Support missing or blocked | no | no |

## Policy

`AcceptancePolicy.require_sufficient_geometry_for_accept` defaults to true.

- Clearance accepts only `SWEPT_SOLID` or `SCAN_GMM`.
- Minimum / difference checks accept `QUANTITY_ONLY`, `SWEPT_SOLID`, or
  `SCAN_GMM`.
- A verified `calibrated-scan-clearance-likelihood` receipt covering a check
  upgrades that check to `SCAN_GMM` for the policy decision. The stored check
  still reports the authority it was constructed with.
- Insufficient geometry yields `REQUEST_EVIDENCE`, never `ACCEPT`.
- `REJECT` still wins if any check is `VIOLATED`.

v0 clearance from `assess_clearance` is constructed as `GAUSSIAN_PROXY`.
That is intentional. A green Gaussian overlap is not an as-built clearance
acceptance.

## Beam mapping

`BeamGeometryStatus` from the IFC adapter maps as:

- `COMPLETE` → `SWEPT_SOLID`
- `LENGTH_ONLY` → `LENGTH_ONLY`
- `BLOCKED` → `INSUFFICIENT`

A `LENGTH_ONLY` beam must not be treated as having section-modulus authority.
