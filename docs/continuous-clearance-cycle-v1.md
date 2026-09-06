# Continuous width-clearance cycle

`gat.geometry.clearance_cycle` connects actual GAT raw metre quantities and
their complete joint covariance to a continuous decision-loss calculation.
It is additive to the finite hypothesis benchmark and existing entropy policy.

## Physical scope

The gate is `(opening_width - assembly_width)/2 >= required_clearance_m` for
an explicitly associated opening and assembly. Both frames must be aligned,
with the assembly centred in opening X, under a named exact-pose assumption.
The implementation refuses an offset/rotated case rather than silently omitting
its geometry. Height, wall depth, passage trajectory, contacts and uncertain pose
are outside this gate. ACCEPT_WIDTH_GATE is never a full-fit/compliance verdict.
Nominal widths must be positive; Gaussian tails are not truncated to physical
positive widths, so input uncertainty must be appropriate for this approximation.

Each candidate is an affine measurement of raw metre variables, with an offset,
positive independent residual-noise sigma, cost in the declared decision-loss
unit, calibration digest and explicit availability/permission declarations.
Shared calibration may be represented as a raw latent variable in the sensor's
affine row with correlations in the joint belief. Residual noise is assumed
independent of that state. Unknown bias or correlated repeated residual noise
must not be silently represented as independent noise. No bundle policy is
implemented here; the finite prototype remains the explicit joint-outcome oracle.

The adapter propagates the full covariance, derives the Gaussian conditional
margin and numerically integrates minimum posterior loss over possible readings.
Integration splits at the action boundary and Gaussian transition regions;
successive quadrature rules must agree within the declared tolerance. The
reported numerical error is an estimate plus a Gaussian-tail loss bound, not a
rigorous integration certificate. Three illustrative outcomes are inspection
examples, not the integration rule. No finite hypothesis discretization is used.

## Time as a state-space axis

Plans bind a world, belief, frame representation and decimal UTC Unix-nanosecond
epoch. A reading at another epoch or against a changed world is refused. Epochs
are caller declarations, not timestamps authenticated from sensor bytes. A plan
does not extrapolate simply because its caller supplies a later timestamp.

The example uses existing `EvolveLinearGaussian` to forecast a declared 60-second
transition with shared and independent width process noise. The forecast remains
hypothetical until that process transition is explicitly recorded in the session
ledger. Model-based prediction and observation conditioning are separate events.
Shared width drift cancels from the relative gate; independent drift increases
its variance. This is width evolution, not a rigid translation affecting width.

Frequency/spectral models remain extension points. Recorded sample intervals,
clock uncertainty and an identified temporal process are needed before adding
periodic latent states or spectral analysis. This increment neither assumes a
periodicity nor treats different times as independent copies of an object.

## Complete reproducible synthetic cycle

Run in a fresh output directory under the qualified numerical envelope:

```text
python -m gat.demo.clearance_cycle continuous-clearance-out
```

The runner preserves sensor/process declarations, the initial snapshot, original
reading bytes, a posterior snapshot, the execution ledger and an inspection
report. It refuses an existing output directory. Planning does not change the
world. Observation uses the existing `ObserveLinearized` executor with exact
world/belief and evidence bindings, strict invariant checks and ledger recording.
Repeat evidence bytes are refused within the current session ledger, even after
replanning. This is not global deduplication across independently resumed sessions.

The library function accepts a trusted locally constructed plan and caller-
decoded reading. The caller must preserve the original bytes before invoking
it; the demo does so. A digest does not authenticate a sensor or authorize a
measurement. A future external API needs a strict parser, retained source-policy
checks and a durable receipt boundary; this Python function is not that API.

`examples/continuous-clearance` contains a saved synthetic run. Replay from the
initial snapshot through the saved ledger reproduces the posterior. Inspection
of `cycle.json` requires no computation. The reference runtime remains the
repository's qualified Python/NumPy/BLAS envelope.

The example recommends opening width. Its generated reading of 2.008 m changes
the width-gate probability from approximately 0.500 to 0.201; the decision remains
REJECT_WIDTH_GATE. Reducing uncertainty can strengthen an adverse assessment.
Expected benefit before a reading and realized posterior loss are distinct.

## Independent measurements and Claude handoff

No physical readings or independent outcomes were supplied. The completed cycle
is explicitly SYNTHETIC, and independent evaluation is NO_MEASUREMENTS. To collect
the first real trials, use `examples/continuous-clearance-trials.csv` as an empty
manifest and preserve the referenced artifacts separately:

1. Fix one opening/object association, a centred/aligned configuration and the
   required clearance. Record frames and reference instrument calibration.
2. Freeze the prior, candidate likelihoods, losses and costs before revealing
   that trial's readings or reference result.
3. Record candidate readings with capture epochs and separate independent
   reference measurements, including reference uncertainty. Trial identity,
   instrument/session identity and exclusions must be retained.
4. Split calibration/training trials from evaluation trials by collection session
   where appropriate. Do not fit measurement noise using the held-out references.
5. Compare policy costs and errors across repeated near-threshold trials. If the
   reference interval crosses the gate threshold, retain an unresolved reference
   outcome rather than manufacturing a binary ground-truth label.

This manifest is a collection protocol, not an implemented empirical evaluator.
The existing 32-margin fit-calibration evaluator has a different scope and must
not be fed scalar width records as if they were complete opening-fit results.

Claude can show initial/forecast/observed states on a time selector, the bounded
width gate, predicted measurement benefit, actual reading, probability change,
source references and ledger bindings. Keep SYNTHETIC and WIDTH_GATE_ONLY visible.
Do not label a lower posterior variance as measured accuracy. Retain the separate
full-fit report and confidence vocabulary rather than reusing a width decision
as a building or assembly verdict.
