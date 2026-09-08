# Coordinate-frame contract v1

Status: mathematical primitives and synthetic qualification tests. These APIs
do not yet replace the IR's yaw-only `Placement`, lower general IFC placements,
or generate an acceptance verdict or calibrated measurement update.

## Representation and composition

`gat.geometry.frames` provides `CoordinateFrame`, `FrameGraph`, and
`RigidTransform` under `gat-coordinate-frame-v1`.

- Each frame has an identity, one parent (or no parent for the root), a
  right-handed orthonormal basis, an origin, and an explicit `m` or `mm` unit.
- Rotation columns are child axes in parent coordinates. All stored origins
  (`translation_m`) are in metres in the parent's axes, regardless of either
  frame's coordinate unit. Point inputs/outputs use their declared frame units.
- A transform maps column vectors by `p_parent_m = R @ p_child_m + t_m`.
  Composition `a.compose(b)` means `a @ b`; the child transform acts first.
- The graph requires unique IDs, one root, known parents, and no cycles. The
  root has the identity transform. Unknown frames, reflections, shear, scale
  embedded in rotation, nonfinite inputs and unsupported units are rejected.
- `FrameGraph.covariance` rotates and scales a point covariance using exact
  frame transforms. Metre-to-millimetre conversion multiplies covariance by
  1,000,000. Translation does not change point covariance.

The convention follows the parent/child composition rule described in
[Modern Robotics, homogeneous transformation matrices](https://modernrobotics.northwestern.edu/nu-gm-book-resource/3-3-1-homogeneous-transformation-matrices/).
The implementation uses proper rotation matrices, not independent unrestricted
Euler-angle Gaussians. It adds no SciPy dependency.

```python
import numpy as np
from gat.geometry.frames import CoordinateFrame, FrameGraph, RigidTransform

frames = FrameGraph([
    CoordinateFrame("building", None, RigidTransform.identity()),
    CoordinateFrame("storey", "building", RigidTransform(np.eye(3), [0, 0, 3])),
    CoordinateFrame("opening", "storey", RigidTransform(np.eye(3), [2, 1, 0]), "mm"),
])
point_m = frames.point([1000, 0, 0], "opening", "building")  # [3, 1, 3]
```

`representation_digest()` binds the graph's declared frame identities, units,
parents, rotations and origins. Changing the frame representation changes that
digest; it does not imply new physical evidence or a changed building. This
digest is not a world digest and cannot be substituted for an evidence receipt.
The graph does not infer containment, connectivity, material or evidence links.

## Joint uncertainty convention

`RigidTransform.propagate_points(points_m, joint_covariance)` propagates N points
and **one shared uncertain pose** to first order. The nominal pose is a full
3D rigid transform. The perturbation convention is explicitly:

```text
T_actual = T_nominal @ Exp(delta)
delta = (tx, ty, tz, rx, ry, rz) in the local/child tangent frame
translation errors: metres; rotation errors: radians
joint variable order: (p1_xyz, ..., pN_xyz, delta)
```

For a local point p, the first-order pose Jacobian is `R @ [I, -skew(p)]`.
The function stacks these Jacobians for all points and propagates the **full**
joint covariance. Point/point, point/pose, and translation/rotation correlations
are supported. Zero cross-blocks declare independence; the function does not
invent independent pose copies for separate objects.

Consequently common translation cancels from relative position, and shared
orientation can induce correlated relative uncertainty. The output is nominal
transformed points and a full joint covariance, not the exact expectation or
distribution of nonlinear rotations. Covariances must be finite, symmetric,
and positive semidefinite within declared floating-point roundoff.

This is a local small-error approximation. Large-angle distributions,
multimodal association, uncertain nested frame-chain covariance composition,
and nonlinear confidence coverage require separate methods and qualification.
Exact nested placements are supported; do not treat several uncertain
ancestors as independent without an explicit joint model.

## Where the frame sits on the earth

`gat.geometry.frames` is mathematics: rigid transforms and a validated tree,
with no earth in it and no evidence. That boundary is kept. A vertical datum is
not mathematics — it is a declaration about what a height is measured from —
and a geodetic anchor is evidence about where a frame's origin stands on the
planet. Both live in `gat.geometry.datum` under `gat-geodetic-anchor-v1`, beside
the frame graph, and meet it by frame identifier and nothing else.

They are declared before any anchor exists, on purpose. The workbench already
refuses MAP and GLOBE because no `IfcSite` placement, `IfcMapConversion` or CRS
reaches the IR, and an invented position would be visual adjacency presented as
evidence. That refusal was correct and it was also permanent by omission:
nothing an operator could supply, however well surveyed, would have lifted it.
This contract is the object a properly evidenced anchor would be, so the
refusal becomes conditional and the condition is written down.

**Three kinds and no member for "unknown."** `ELLIPSOIDAL` is height above a
reference ellipsoid, which is what GNSS produces. `ORTHOMETRIC` is height above
a named geoid model, which is what a survey or a map means by level.
`LOCAL_ENGINEERING` is a project zero — a finished floor level, a site benchmark
— which is what an IFC almost always carries. An unknown datum is the absence of
an anchor, not a value in the vocabulary; a member for it would let a height
with no declared origin travel through every later join looking like one that
had a declared origin. A reference surface is required on all three, because
"orthometric" without a geoid model names a family of surfaces that differ from
each other by metres.

**A local datum anchors and does not join vertically.** A building whose plan
position is surveyed and whose heights are relative to its own slab is a real,
common and well-understood object, so it is not refused. What it does not have
is any relation between those heights and anybody else's, and
`vertical_join_available` says so rather than letting the height pass as an
earth height. Horizontal and vertical standing are reported separately for that
reason: one verdict for both would either forbid a sound join or allow an
unsound one.

**The transform is an object, not a subtraction.** Ellipsoidal and orthometric
heights differ by the geoid undulation `N`, and `h = H + N`. `N` is a field, not
a constant. A `GeoidSeparation` therefore carries the model that produced it,
the point where it was evaluated, a declared validity radius and its own
evidence; the conversion refuses when the model does not match the orthometric
datum's reference, when the point lies outside the declared radius, or when no
separation is supplied at all. A local engineering datum converts to nothing:
the relation between a floor slab and the earth is established by a levelling
run to a benchmark, and inventing it is the failure this refuses.

**The anchor may not come from the model, and may not come without sigma.**
`scan_likelihood` already refuses to let registration supply the pose used to
claim the model's dimensions are wrong; an anchor inferred from the geometry it
places closes the same circle at a larger radius, so `MODEL_DERIVED` and
`INFERRED_FROM_CONTEXT` are inadmissible. Both sigmas are required and positive,
because the consumer that indexes geodetic positions gives no key at all to a
position with no stated uncertainty — refusing here makes the failure loud at
the producer instead of quiet one system downstream.

### The metric, and the choice that was wrong first

The validity-radius check measures arcs on a sphere of the WGS84 **polar radius
of curvature**, `a²/b` ≈ 6 399 593.63 m, because that is the largest principal
radius of curvature anywhere on the ellipsoid and the arc therefore over-states
the true geodesic separation. A point marginally inside a declared radius may be
refused; one outside it is never accepted. Fail-closed on the metric as well as
on the declaration.

The semi-major axis is the intuitive choice and it is wrong. A sphere of radius
`a` *under*-states east-west separations at high latitude, where the prime
vertical radius of curvature exceeds `a`: at 80° south a 0.2° east-west pair
measures 3 866 m against a 3 879 m geodesic. An under-stated distance accepts a
separation that has travelled outside the range it was declared good for, which
is the exact failure the radius exists to prevent. The bound is verified
numerically against a Vincenty inverse over ~12 500 sampled pairs in
`tests/test_datum.py` rather than argued for in prose, because prose is what got
it wrong the first time. It is tight at the pole, where the prime vertical
radius of curvature equals `a²/b`.

This is not geodesy and is not offered as any. It answers one question: is this
point further from that one than somebody declared their number good for.

### What this does not do

It does not lower `IfcSite`, `IfcMapConversion` or `IfcProjectedCRS`; nothing
reads a georeference out of a model, which is what keeps `MODEL_DERIVED`
unreachable rather than merely forbidden. It does not lift the workbench's MAP
and GLOBE refusals — teaching those surfaces to accept an anchor is separate
work, and doing half of it would leave a surface that draws a position under
conditions nobody stated. It holds no geoid model and computes no undulation.

## Qualification evidence and remaining gates

The synthetic tests check:

1. Nested rotation/translation composition against direct application, including
   noncommuting order and inverse transforms.
2. Point and covariance round trips between metres and millimetres.
3. Opening-minus-assembly fit margin, variance and Gaussian probability under
   global translation and full 3D rotation, with geometry and covariance
   transformed together.
4. Exact cancellation of shared translation from relative position, and the
   relative uncertainty caused by shared rotation.
5. Full joint propagation against an independently evaluated finite-difference
   Jacobian, including point/pose cross-correlations.
6. Rejection of invalid topology, bases, units and covariance matrices.

Metre-scale transform checks use absolute tolerances down to 1e-12; the
opening-fit probability check uses 1e-10. The finite-difference probe uses
1e-6 perturbations with covariance tolerance 1e-12 absolute / 1e-8 relative.
These tolerances qualify the supplied synthetic cases, not arbitrary scene
scales, sensor accuracy, or a cross-platform bitwise execution contract.

Calibration is a separate evidence boundary. No calibration claim or
measurement update is produced by this module. The existing scan adapter's
independent-pose requirement is unchanged; registration to the BIM remains an
association step, not independent confirmation that the BIM is correct.

Next gates: bind these frame records to the bounded IFC opening-fit workflow;
map independently measured dimensions and calibrated pose into the joint model;
carry calibration version/source/control identities and residuals separately;
check predictions on held-out measurements; expose frame, uncertainty and
residual metadata in Claude's report/viewer surfaces. No field measurements
or independently established external-model outcome are available yet.

### Bounded external compatibility target

The existing pinned buildingSMART wall/opening/window sample is a small next
integration target, not field evidence. Its exact content hash is
`73b0e45d931d5dc13bfee5fdc7bd80f796526445458b2de74c4168d209097832`
(12,492 bytes; IFC4; CC-BY-4.0). Source, commit and licensing provenance are in
[`validation/ifc-corpus-v1.json`](../validation/ifc-corpus-v1.json).

Local audit confirms three supported products, three missing required
quantities, one `MISSING_SOURCE_DATA` product and two
`NEEDS_GEOMETRY_DERIVATION` products. The pipeline remains `BLOCKED`.
Implement only the geometry, placement and dependency coverage needed for an
explicit opening-fit scope; do not invent quantities to make the model pass.
Independently measured dimensions and a reference outcome remain missing.
