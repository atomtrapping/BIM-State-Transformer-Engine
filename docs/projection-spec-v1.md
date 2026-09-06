# ProjectionSpec v1 and the Notation Workbench

`gat workbench` composes the human surfaces of this repository into one
offline instrument with eight projection modes. This document is the
contract behind it: what a *projection* is allowed to claim, how a mode
declares itself, how modes share one identity, and what the frontend seats
that are not yet filled (kepler.gl, CesiumJS) will have to read. The code
is `gat/workbench.py`; the design language it inherits is
`docs/design-language-v1.md`.

## The requirement

> Every representation identifies its source, its transformation, its
> supported meaning, and its information loss.

A building element appears as an IFC entity, as scan geometry, as a
computational variable, and as a selected object on a screen. A visually
convincing correspondence between those is not evidence that they describe
the same subject at compatible times and in compatible coordinate frames.
So every Workbench mode carries a `ProjectionSpec` that states, verbatim on
the page, what it projects and what it drops — and the instrument states
which modes it *cannot* fill and why, instead of faking them.

## The triad and the modes

| Mode | Seat | Question | Surface class | Today |
|---|---|---|---|---|
| MAP | kepler.gl — analytical geography | Where is the pattern? | instrument | **unavailable** — no coordinate reference system is lowered into the IR |
| GLOBE | CesiumJS — geodetic reality | Where does it exist? | connected instrument (not yet defined) | **unavailable** — no geodetic datum; tiles would need the network |
| STRUCTURE | Three.js seat — computational structure | How is it constituted? | instrument | `gat view` embedded (self-contained WebGL renderer), with the EXPLODE reading offset and per-piece audit outlines |
| GRAPH | IR relationship graph `G` | What relates to what, on whose authority? | instrument | deterministic reading-order layout, typed edges, IFC source references |
| STATE | IR entities `X` over `N(mu, Sigma)` | What is believed, and how surely? | instrument | per-entity quantities: mean ± sigma, raw or derived, provenance |
| TIME | execution ledger | What happened, in what order, did the chain hold? | report | `gat ledger` timeline, chain verified before drawing |
| EVIDENCE | decision report | What was decided, on what evidence, what is missing? | report | `gat report` of the bound `gat-headless` response |
| COMPLEXITY | IFC compatibility audit | What can this corpus represent, and what not? | report | `gat audit` of the source file |

Modes are numbered 1–8 in this order on the toolbar and on the keyboard.

## ProjectionSpec fields (`gat-projection-spec-v1`)

| Field | Meaning |
|---|---|
| `mode` | one of the eight names above |
| `seat` | which projection library or engine artifact fills the mode |
| `question` | the one question the mode answers |
| `surface_class` | `report` (script-free, inert), `instrument` (self-contained, offline, inline scripts), or `connected instrument` (would fetch external resources — **not yet defined** as a class; naming it here is the honest placeholder) |
| `source` | the engine artifact the projection reads |
| `transformation` | what the mode does to its source to draw it |
| `meaning` | what the picture may be read as |
| `loss` | what the projection drops or approximates |
| `identity` | how subjects are named in this mode (`EntityId`, `VarId`, request id, event hash, world digest) |
| `frame` | the coordinate frame or unit system, or `none` |
| `metric` | the distance model the mode's measurements use — Euclidean in a declared Cartesian frame, geodesic on a declared reference ellipsoid, the shortest path on a mesh, the shortest permitted path through a network — or `none`, with the reason (see *Distances are declared*) |
| `time` | which state in time the mode shows (one world digest, ledger sequence, file version) |
| `availability` | `available`, `empty`, or `unavailable` (below) |
| `reason` | for `empty` and `unavailable`: why, and what would fill the mode |
| `mutates_source` | always `false` |

The specs are embedded in the page twice: as a disclosure strip at the top
of each mode, and in full as JSON in the footer.

## Availability

* **available** — the mode has a source and renders it.
* **empty** — the mode exists for this corpus, but nothing is bound to it in
  this document (no `--ledger`, no `--decision`, `--no-audit`). The panel
  says exactly which flag or artifact fills it. The toolbar keeps the mode
  visible with an `empty` mark; it is never hidden.
* **unavailable** — the corpus cannot fill the mode. MAP and GLOBE are
  unavailable in this release because no IfcSite placement, IfcMapConversion
  or coordinate reference system reaches the IR; an invented position would
  be visual adjacency presented as evidence. Whether and how those
  semantics are lowered is an engine decision; this document only names
  what the seats will read once they exist (`frame` with a CRS, `time` with
  a survey epoch, and for GLOBE a defined connected-instrument class with
  declared tile sources).

## Distances are declared, not assumed

Coordinates describe positions; the geometry, the metric and the permitted
connections decide what a distance means. Two rooms can be close on the
plan and a long walk apart; two depots can be a short ellipsoidal
separation and a much longer permitted route. So every mode declares its
distance model in `metric`, and a distance shown on any surface is read
under that declaration:

| Context | Distance model | Where it appears |
|---|---|---|
| a declared local Cartesian frame | Euclidean distance in that frame, in its units | STRUCTURE (clearances, dimensions, reading offsets), EVIDENCE (clearances as the engine evaluated them), the fit report's margins |
| locations across the Earth | geodesic distance and bearings on a declared reference ellipsoid | MAP and GLOBE, once a CRS is lowered (none today) |
| terrain or a curved surface | the shortest path constrained to the mesh | no mode yet |
| roads, corridors and doors | the shortest *permitted* path through a weighted network, under a declared distance rule | the reserved ACCESS representation |
| a reading order, a timeline, a table of quantities | none — the canvas carries no metric | GRAPH, TIME, STATE, COMPLEXITY |

A straight-line distance is never presented as a path, and a path length is
never presented without the network and rule it was computed on. The
relationship graph drawn by GRAPH has no metric at all: it is not an
access graph, and its layout distances carry no information.

## Identity across modes

One selection is shared by every mode. It is an `EntityId`
(`IfcClass:GlobalId`) — never a name, never a position, never an index into
a mode's own arrays. The identity strip shows the name *and* the id.

* GRAPH nodes, STATE list entries and STRUCTURE elements all carry the
  `EntityId`; selecting in any one selects in all.
* The page and the embedded viewer share one world digest, and every
  message between them carries it; a message from a different world is
  ignored, not reconciled.
* Report panels (TIME, EVIDENCE, COMPLEXITY) mark exact-name mentions of
  the selected entity so the reader sees where the identity appears in the
  evidence. Because `gat-headless` responses name subjects by entity *name*,
  a name shared by several entities is an ambiguous identity: nothing is
  marked and the strip says so. Carrying `EntityId`s in responses would
  remove the ambiguity — an engine contract, noted here rather than worked
  around.
* The URL hash carries `#MODE/EntityId`, so a view can be shared and
  restored by identity.

## Message contract (`gat-workbench-message-v1`)

The STRUCTURE viewer runs in a sandboxed `srcdoc` frame (`allow-scripts`
only; opaque origin). Messages are the only channel between it and the
page; there is no DOM access in either direction.

| Direction | `kind` | Fields | Meaning |
|---|---|---|---|
| viewer → page | `ready` | `world_digest` | the frame has booted; the page replays its current selection |
| viewer → page | `selection` | `world_digest`, `entity` or `null`, `name` | the user selected (or cleared) an element in the viewer |
| page → viewer | `select` | `world_digest`, `entity` or `null` | select (or clear) this identity in the viewer, quietly |

Every message carries `format: "gat-workbench-message-v1"`. Receivers check
the format, the source window, and the world digest before acting, and
drop anything else silently. No message mutates state on either side:
selection is a view property, not a model property.

## Exploded views are reading offsets

STRUCTURE can pull the asset apart. The displacement of each piece is
derived from the relationship graph (radially from the plan centroid; an
opening with the wall it voids, a door with the opening it fills, one step
further each; spaces lifted), scaled by a slider, and drawn with leader
lines back to the assembled place. It is declared in the mode's
`transformation` and `loss`, stated on the inspection card ("drawn N m from
its place for reading; not a position"), and never written anywhere: the
scene, the world and the carrier are untouched. The same rule would hold
for an OpenUSD expression of the exploded layout — a variant or
time-sampled transforms over the derived view, never over `/GAT/State`.

Audit statuses ride along per piece, bound by GlobalId from a
`gat-ifc-audit-v1` document and refused if the vocabulary is unknown. A
piece the corpus could not fully represent is outlined in its status
colour; its fill keeps the identity hue, because an audit status describes
the corpus, not a verdict on the asset.

## Frames: stated today, read tomorrow

Every projection draws in a frame it states. `frame_record(world)` reads
what the adapter recorded — the IFC length unit and its scale to metres,
the placement convention of the lowering (corner-origin box, yaw about
+Z) — and adds the viewer's own convention (right-handed, Z up, metres,
the same the OpenUSD carrier declares), the absence of a CRS, and the
engine's current limit: **placements are exact metadata, so the belief
carries dimensions only**. The record is embedded in the scene, shown in
the viewer's meta line and the workbench identity strip, and is the source
of the `frame` field of the STRUCTURE and STATE specs. A frame change on
the display side is never evidence: the tests assert that computing frame
records and reading offsets in other frames leaves the world digest
untouched.

Projections must behave consistently under a change of frame, and the
frontend tests that on its own layer: EXPLODE offsets are invariant under
translation, rotate with the scene, and scale with the unit; the box
centre the viewer uses agrees with the engine's. GRAPH is frame-free by
construction. These are the frontend's share of the coordinate-
transformation equivalence tests; the engine's share (nested placements,
pose uncertainty, physical-result equivalence within a declared tolerance)
is the milestone the engine team owns.

### What the viewer will read when the engine carries frames and pose

This is a consumer's statement of the fields the surfaces will draw, not a
design of the engine's representation. It exists so the two can be shaped
together.

| Record | Fields the surfaces read | How it will be drawn |
|---|---|---|
| frame | `id`, `parent`, `transform` (rigid, declared convention), `units`, `up`, `handedness`, `crs`, `epoch` | identity strip and meta line; MAP/GLOBE availability flips only when `crs` is present |
| pose belief per element | position mean and 3×3 covariance in the parent frame; a rotation uncertainty in a representation that respects rotation geometry (e.g. a yaw variance for gravity-aligned cases), with correlations to dimensions where the engine carries them | a position ellipsoid at the box centre and a yaw fan, distinct from the dimensional ellipsoids; the inspection card separates "loose in place" from "loose in size" |
| residual | observation id, `VarId` or pose component, predicted mean ± sigma, measured value ± sigma, standardised residual, calibration id, frame id, independence flag | a CALIBRATION report: coverage per quantity class and frame, standardised-residual table, and markers on the pieces in STRUCTURE; a residual from a scan aligned to the model is drawn as association, never as independent evidence |

Nothing above is rendered until the engine emits it; the surfaces will
refuse a pose or residual record whose frame id they cannot resolve.

The first emitted records are the `gat-opening-fit-v1` prediction and the
`gat-fit-held-out-v1` evaluation. Their report renderings are described
under *Surfaces* in the design language: the headline is the field
acceptance, the pose sidecar is drawn as an assessment assumption named by
its id, and the global exact-placement statement stays on the frame record
because the sidecar is not canonical belief. Drawing the assessment pose in
STRUCTURE waits for an IFC-backed case with a scene to draw it in.

### The fit surface around the benchmark

The next milestone is one trustworthy opening-fit workflow on a permissioned
external IFC model, and the interface is built around that benchmark: a
practitioner selects the opening and the proposed assembly, inspects their
frames and dimensions, sees the controlling clearance, compares predicted
with measured geometry, sees which evidence is still missing, and can follow
every assessment to its exact inputs and method version.

What renders today from the two emitted records (`gat report`, described
under *Surfaces* in the design language): the controlling clearance and its
rule, the frame chains and bound dimensions, the evidence card, the
predicted-vs-measured residuals, and the inputs-and-identity card. What
waits for the benchmark, stated from the consumer's side:

| Need | Why the surface cannot fill it yet | What the benchmark package must carry |
|---|---|---|
| Select the opening and assembly in STRUCTURE and bind the assessment by identity | the emitted subjects are synthetic ids with no IFC world to select them in | subjects as `EntityId`s present in the world the assessment names by `world_digest`, so a FIT mode binds fail-closed exactly as EVIDENCE binds a decision |
| Show the criteria the fit was judged against | the record carries `required_clearance_m` only | the required width, height and clearance as a criteria record with its source |
| Link the assessment to its method version | the record declares no producer version; the card says "not declared in the record" rather than printing the reader's own version | a `method` object (engine version, commit, contract ids) in the record — the card renders whatever it declares, verbatim |
| Compare predicted with measured | the evaluation names its assessment by digest and its sources by id, nothing more | independently measured dimensions with instrument, date, a source not used for fitting, and calibration context |
| Exercise every branch of the vocabulary | one synthetic case exists, and it is `SATISFIED` / `REQUEST_EVIDENCE` | reference outcomes for a clear fit, a clear violation and an unresolved case |
| Show a useful blocked result | no blocked record exists yet | missing geometry or evidence must yield a structured blocked outcome, never an exception; the report will render it as an undecided headline naming the missing item |

A ninth Workbench mode, FIT, is reserved for this: it will list the
opening/assembly pairs the IR relationship graph offers, bind a
`gat-opening-fit-v1` record to the selected pair by `EntityId` and world
digest, and show the cards above beside STRUCTURE with the pair selected.
It is not added until an IFC-backed assessment exists to fill it; an
`unavailable` mode with a stated reason would say no more than this section
does.

### What the surfaces will read from an observation

Every measured position that reaches a surface — a held-out check in the
fit report, a residual marker in STRUCTURE, a placement on a globe — is an
observation with a calibration chain behind it (reference frame → antenna
or instrument position → platform pose → sensor mounting → measurement
model → estimated position and uncertainty), and the surfaces will draw
only what that chain declares. The observation record the surfaces will
read carries: the sensor identity and calibration version; the capture
timestamp and its clock basis; the coordinate frame and units; the pose
estimate and its covariance; the receiver solution status where one exists
(`RTK fixed`, `float`, …), **recorded verbatim as a status and never
converted into an accuracy claim**; the correction source and its age; a
reference to the raw artifact; the processing method and version; and the
association uncertainty between the observation and the object it is
attributed to. A record missing its frame, its timestamp basis or its
uncertainty is drawn as *unplaced* with the missing field named, exactly as
the Earth Twin lists a record whose subject declares no position.

Two numbers are kept apart on every surface: the fitting error of an
alignment or estimate (an in-sample residual, which a wrong reference can
make small) and its accuracy against withheld, independent controls. The
fit report already separates in-sample factor residuals from the held-out
evaluation; a registration or trajectory estimate will be shown the same
way — residuals on one card, independent accuracy on another, and the
systematic pattern of the residuals visible rather than summarised away.

### What the surfaces will read from a learned model

A prediction from a learned model (a physics-informed network, a graph
network, a neural operator) is a representation like any other, and is
drawn as a *prediction*, distinct from observed or believed state. To be
drawn at all, a prediction record must declare its inputs (by identity and
digest), its model version, its assumptions and the physical model it was
trained against where there is one, its validation domain (the sites,
geometries or operating conditions it was evaluated on, and whether the
case at hand lies inside it), its uncertainty method, and the conventional
baseline it was compared with. Prediction alone never proposes anything to
the corpus: canonical admission is an engine decision on evidence, and the
surfaces will never blur the two. Nothing here is rendered until a model
exists and emits such a record; the field list is a consumer's statement,
shaped with the engine team, not a design of the model.

### What the surfaces will read from a measurement recommendation

When the engine can choose what to observe next, the surface's job is to
explain the choice, not to make it: what remains uncertain, which
measurement is recommended, why it matters to the decision, and what would
change afterwards. The record the surfaces read carries, per candidate
action (measure the opening more accurately, verify the assembly's
dimensions, improve the scan-to-building alignment, take another scan from a
different viewpoint, or any other explicitly permitted action): the quantity
it observes; the decision it bears on and the criterion that controls it
today; the expected reduction in decision loss after the measurement, under
the engine's stated model; the acquisition cost in the same declared unit;
the net value (reduction minus cost) by which the candidates are ranked;
**the possible outcome branches — every reading the model allows, each with
its probability, the posterior P(fit) and the decision that would follow**;
the objective's name and version (an explicit value-of-information
criterion, kept distinct from any expected-free-energy formula); and the
model the prediction rests on, by digest. A most-likely outcome alone can
conceal an important low-probability branch, so branches are shown in full
and a single "predicted outcome" is never substituted for them; where a
record summarises branches as a range, it must say what the range is (a
minimum and maximum over enumerated branches, a credible interval at a
stated level, a numerical error estimate with a tail bound) and the surface
repeats that word. Where a shared variable — an alignment, a calibration —
couples several candidates, the record names it, so the surface can show
that one measurement informs several quantities.

The card renders the ranking as the engine emitted it, names the objective
verbatim, and keeps apart two things that are easy to conflate: the
measurement that most reduces uncertainty and the measurement that most
improves the decision — a dimension can be very uncertain and barely matter
to whether the assembly fits. A recommendation requests nothing by itself:
it names the next useful measurement in the words of the *evidence still
missing* card, and the acquisition remains a permitted action someone takes.
Its FIT / REJECT are the model's two-action loss decisions, never the fit
report's SATISFIED / VIOLATED / UNRESOLVED.

#### Field agreement with the producers

Three producers exist or are drafted: the finite decision plan and saved
experiment (`gat.finite-decision-plan.v1`, `gat.synthetic-clearance-voi-experiment.v1`,
GAT #31, rendered by `gat report`), the continuous width-clearance cycle
(`examples/continuous-clearance/cycle.json`, GAT #32, stacked on #31), and
an uncommitted TypeScript draft in NotationsOS (`src/compute/clearance-voi.ts`,
reported to carry loss reduction, cost, net value, hypothetical outcomes with
posterior decisions, shared dependencies and the four comparator policies).
The agreement below is written against the two committed records; the draft
is to be confirmed against the same rows when it is committed, not re-derived.

| Consumer field | Finite plan / experiment (#31) | Continuous cycle (#32) | Standing |
|---|---|---|---|
| quantity observed, unit | `model.measurements[].quantity`, `unit` (the bare plan carries ids only, so the card reads `undeclared`) | affine measurement rows over raw metre variables | exists |
| decision it bears on, controlling criterion | `source.fit` (a binary fit rule); no per-margin controlling criterion in a two-action model | the width gate `(opening − assembly)/2 ≥ clearance`, `WIDTH_GATE_ONLY` | exists as stated; the fit report's controlling clearance is a different record and is not conflated |
| expected reduction in decision loss | `expected_loss_reduction` | candidate expected loss reduction | exists |
| acquisition cost, unit | `acquisition_cost`, `loss_unit` | cost in the declared decision-loss unit | exists |
| net value and ranking | `net_value`, `plan.options` order, `selected`, `selection_tolerance` | candidate ranking | exists; the card refuses a selection the ranking contradicts |
| outcome branches with probabilities and decisions | `outcomes[]` (`readings`, `probability`, `posterior`, `p_fits`, `decision`, `expected_loss`), enumerated exhaustively | three *illustrative* readings that are not the integration; a numerical error estimate and Gaussian tail bound instead | exists for #31; **adapter** for #32: the card must label illustrative readings as such and show the error estimate as the range word, never as branches |
| range semantics | none needed: branches are exhaustive | numerical error estimate plus tail bound | exists, stated |
| objective name and version | `method` = `gat.finite-decision-voi.v1` | method id and version | exists |
| model identity by digest | `model_digest`, `source_digest`, `result_digest`, `artifact_digest` | plan binds world, belief, frame representation and epoch; snapshot and ledger digests | exists |
| shared variables coupling candidates | encoded in `hypotheses[].values` (the shared instrument offset) and in a measurement's `quantity` text; no explicit coupling field | shared calibration as a raw latent variable in the affine row with joint covariance | **adapter**: the card can show the coupling only by name today; an explicit "shares" field would let it draw which candidates one measurement informs |
| permitted action | `availability`, `permission` declarations, `excluded[]`, `physical_action_authorized = false` | availability and permission declarations | exists; the card refuses `true` and refuses an available, permitted exclusion |
| limitations and validation | `model_status`, `provenance`, `field_validation`, `independent_evaluation`, `evaluation_scope` | `SYNTHETIC`, `NO_MEASUREMENTS`, scope words | exists, rendered verbatim |
| comparators | `comparisons` (no measurement, cheapest first, largest uncertainty first, one-step VOI, measure everything, opening and calibration) | none in the cycle record | exists for #31 |
| what would change afterwards | per branch: `decision`, `p_fits`, `expected_loss` | the realised update (`update`, `posterior_plan`) after one reading | exists |
| field-validated accuracy | — | — | **unavailable** by design until independent trials exist; the card shows `NOT_ESTABLISHED` / `NOT_AVAILABLE` and never a model expectation as accuracy |
| a recommendation for a real IFC pair | — | — | **unavailable**: both records are synthetic; the FIT mode waits for the benchmark |

The card is tested on four cases and refuses a fifth: a positive
recommendation (the saved experiment), no worthwhile measurement (every
candidate priced above its benefit; `NO_WORTHWHILE_AVAILABLE_MEASUREMENT`
is undecided grey, nothing is selected, the candidates still show their
negative net values), unresolved assumptions (a candidate whose availability
or permission is `UNKNOWN` is excluded with its reason and never ranked),
and impossible outcomes (branch probabilities that do not sum to one, a
zero-probability branch, a posterior outside [0, 1], arithmetic that does
not close, a claimed authorization, a selection the ranking contradicts —
each refused, never drawn).

## Reserved: ACCESS, a configuration representation

Cartesian geometry answers where a thing is and what its dimensions are.
Space Syntax asks a different question of the same building — which spaces
can be reached from which others, how route continuity shapes
accessibility, what can be seen from a location — and answers it over an
explicit *representation of space* (rooms and their access graph, axial
lines, segments, convex spaces, visibility fields), each a different aspect
of spatial experience and none interchangeable with another. For this
engine it would turn a dimensional fit into a configuration-aware
assessment — "this opening fits physically; what does opening, closing or
relocating it do to the connected spaces?" — with the two kinds of result
kept distinct. It is a promising extension, not an implemented capability:
the representation is reserved here so that the first implementation reads
a stated contract rather than inventing one.

| Field | What the ACCESS representation will require |
|---|---|
| `seat` | a versioned Space Syntax method; depthmapX and the QGIS Space Syntax Toolkit are the reference implementations to compare against before any algorithm is written here |
| `source` | an access graph *supported by source information*: a traversable doorway is an IFC relationship or a documented observation, never two rooms touching geometrically, and a visible connection is not permitted access |
| `transformation` | the representation (access graph, axial, segment, convex, visibility), the distance rule (topological, angular, metric), the radius, the normalization and the network boundary — every one changes the result, so an "accessibility score" without them is not a representation |
| `meaning` | calculated spatial properties (connectivity, depth, a precisely defined integration or choice) — never a prediction of footfall, rent or behaviour, which needs additional data and validation and is reported as a separate, distinguished result |
| `loss` | what the chosen representation drops (a graph carries no dimensions; an axial map carries no rooms) |
| `metric` | the shortest permitted path through the weighted network under the declared distance rule and radius — the one place a path length appears, and never as a straight line |
| `identity` | space and connection ids that resolve to `EntityId`s in the world the analysis names, so selection stays synchronized with STRUCTURE and GRAPH |
| `time` | the state of the building the graph was drawn from, and the analysis date |
| `availability` | `unavailable` in this release: no access graph is lowered into the IR, and the IR relationship graph drawn by GRAPH is *not* an access graph |

Connectivity uncertainty is the question the surfaces will have to draw
honestly: a passage that may be open, closed or restricted changes the
network itself, so its effect is evaluated as explicit scenarios reported
side by side, not propagated as a small perturbation of a fixed model — and
the scenario whose outcomes differ most names the next useful observation,
in the same words the fit surface uses for missing evidence. The first case
is one permissioned floor plan, not a city: an explicit access graph with
source references; connectivity, depth and one defined integration measure;
a baseline compared with one doorway or partition change; the plan and the
graph with synchronized selection; and any movement interpretation compared
against observations or a practitioner's review.

## Non-goals

The workbench adds no judgement of its own: no derived scores, no
aggregated traffic lights, no inferred correspondences between modes. It
does not fetch anything. It does not implement the kepler.gl or CesiumJS
seats or the ACCESS representation; it reserves them and states what they
would need.
