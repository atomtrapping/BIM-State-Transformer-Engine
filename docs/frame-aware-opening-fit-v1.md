# Frame-aware opening-fit prediction v1

This increment connects the canonical dimensional belief to explicit frames
and a joint opening/assembly pose model. It emits a report-ready prediction
and provides a held-out measurement evaluation harness. It does **not** add
canonical pose variables, general IFC geometry support or field acceptance.

## Supported physical question

An opening is a centred rectangular aperture in its frame's X/Z plane.
Its local Y passage direction is unbounded. An assembly is a centred box
with three extents. Every assembly corner must project inside all four
opening edges by at least the requested per-edge clearance.

Frame origins must be geometric centres. Existing IR placements are corner
origins: passing them unchanged would be incorrect. The caller explicitly
binds two frame IDs and five VarIds (opening width/height, assembly X/Y/Z
extents). IDs carry the owning entities into the report. No proximity or
name match infers physical correspondence, containment or evidence.

This checks projected containment at a specified pose, not an insertion
trajectory, finite wall tunnel, neighbouring obstacle or deformable assembly.
No new IFC lowering is included. The existing demo IFC lacks door depth and
is refused by this contract; the demo below constructs explicitly synthetic
dimensions instead of supplying an invented IFC quantity.

## Joint model and invariance

`assess_opening_fit` reads dimensional means and their raw-state Jacobians
from the bound world, preserving derived quantities and dimensional
correlations. It requires a 12x12 pose covariance and an n_raw x 12
raw-dimension/pose cross-covariance. A zero block explicitly declares
independence or exactness. The full joint covariance is validated as PSD.

Pose order is opening then assembly; each is a right-local tangent
`(tx,ty,tz,rx,ry,rz)` in metres/radians. Nominal transforms may have arbitrary
3D rotations and exact nested parents. Ancestor uncertainty must already be
represented in the supplied joint leaf covariance, including correlations;
this adapter does not compose uncertain ancestor chains.

For assembly-local corner q and relative transform (R,t), p = R q + t.
The opening pose Jacobian of p is `[-I, skew(p)]`; the assembly Jacobian is
`[R, -R skew(q)]`. The adapter propagates all 32 smooth half-plane margins
together. It does not differentiate a minimum at a corner tie. Per-corner
Gaussian violation probabilities give dependence-safe union bounds, not a
product of assumed-independent events. Repeated corner constraints can
make these bounds conservative.

These are local first-order predictions, not exact nonlinear moments or
empirically established coverage. Large uncertainty and rotation effects
at zero first derivative need additional nonlinear qualification.

Tests check analytic margins, finite-difference derivatives, consistent
global rigid transforms, nested/direct frames, m/mm frame metadata,
shared global pose cancellation, relative pose sensitivity, and
dimension/pose cross-covariance. Frame units describe point coordinates;
stored translations and canonical dimensions remain metres.

## Report contract for Claude

Run:

```console
python -m gat.demo.opening_fit opening-fit-out
```

`prediction.json` uses `gat-opening-fit-v1` and includes:

- Exact world digest and separate frame-representation/assessment digests.
- Stable entity identities, bound dimension identities, complete frames,
  pose covariance, cross-covariance ordering and assumption ID.
- Each corner/edge margin's mean, sigma and violation probability, with
  its opening frame ID; the complete 32x32 margin covariance.
- Nominal deterministic fit, modeled probability bounds and prediction.
- `calibration_status: UNVALIDATED`, `acceptance: REQUEST_EVIDENCE` and
  explicit scope limitations. There is no evidence receipt or state mutation.

The synthetic demo gives a 40 mm minimum nominal gap against a requested
10 mm per-edge clearance. Its assumed pose sigmas are 1 mm and 1 mrad.
These are invented test inputs and must be labelled synthetic in any surface.
`calibration.json` has `NO_MEASUREMENTS`, empty groups and empty residuals.

The Workbench's global exact-placement label remains correct: uncertainty
here is an assessment-specific sidecar. A surface may display its ellipsoid
only as an explicitly selected assessment assumption. Changing these
assumptions changes the assessment identity, never the world identity.

## Held-out evaluation boundary

`evaluate_held_out` accepts unchanged assessment records and scalar measurements
of the exact corner/edge functional named by a risk ID. Records identify the
assessment digest, risk ID, sample ID, independent source, calibration version,
value in metres and independent measurement-noise sigma in metres. It adds
that noise variance to prediction variance for observation residuals.

The caller supplies fitting-source IDs. Reused fitting sources, duplicate
samples, invalid noise, zero predictive-observation variance and changed
assessment records are rejected. Coverage is grouped by quantity class,
frame ID, frame representation and calibration version. No pooling across
incompatible frame representations occurs. Correlated samples are not
independent trials; the output supplies descriptive coverage, not sampling
confidence intervals. Source declarations are not authenticated independence.

No field data is bundled and synthetic tests do not establish calibration.
Acquisition-cost comparisons with deterministic tolerances and measuring
everything still require an independent measurement campaign. Canonical pose
belief updates, a bounded IFC geometry adapter, and verified calibration
receipts remain subsequent milestones.
