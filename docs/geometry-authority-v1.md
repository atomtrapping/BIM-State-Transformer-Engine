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
| `DECLARED_PROPERTY` | Section property asserted in a property set, uncorroborated | no | no |
| `DECLARED_CORROBORATED` | The same declaration, bracketed by the model's own solid | no | yes |
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

## Declared section properties

A capacity check has a third kind of support, distinct from both measured
geometry and dimensional quantities. `GAT_Structural` declares
`PlasticSectionModulusMajorM3` (Z) directly. That value is asserted by the
model author: it is neither measured nor derived from the model's geometry,
so on its own it is `DECLARED_PROPERTY` and closes nothing.

The shipped `gat/demo/beam_model.ifc` is exactly this case — it carries no
body representation at all — which is why its `SATISFIED` prior verdict
yields `REQUEST_EVIDENCE` rather than `ACCEPT`.

When the beam *does* carry a swept solid, the adapter independently derives
the **elastic** modulus S = I/c from the profile polygon. Z and S are
different section properties and are never compared for equality; they are
related by the shape factor k = Z/S. `gat.engineering.section_corroboration`
brackets k at `[1.00, 1.30]`:

- k ≥ 1 is a geometric floor — Z ≥ S holds for any solid section, so a
  declaration below it cannot describe that solid at all.
- A filled rectangle gives exactly k = 1.5. Rolled doubly-symmetric
  wide-flange shapes, which is what `GAT_StructuralScope` restricts this
  profile to, sit near 1.10–1.15.

Inside the bracket the check becomes `DECLARED_CORROBORATED` and may close a
capacity case. This is the same shape of upgrade a verified scan receipt
performs for clearance.

Corroboration is not verification. A bracketed declaration has only been
shown to be consistent with a solid the same file asserts; it never becomes
a measurement, and it never closes an as-built clearance case. What the
bracket actually catches is the class of error that occurs in practice: a
wrong unit, a misplaced decimal, a value read from the wrong row of a
section table.

## Capacity checks reach the gate

`AcceptanceCheckKind.CAPACITY` and `capacity_check()` bring a member
capacity verdict under the case policy. `authority` is a required argument,
not a default: a capacity verdict is only as good as the section property
behind it. A capacity check that declares no authority reads as
`INSUFFICIENT`, because dimensional quantities do not establish a section
modulus.
