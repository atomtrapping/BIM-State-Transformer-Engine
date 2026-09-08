# Factor-graph and report rendezvous v1

This candidate integrates Claude's `72af88c` consumer with #29's opening-fit
engine. The symbolic IR, world identity and evidence ledger retain their
canonical roles. Graph inference is read-only and emits no evidence receipt.

## Inference contract

`gat.gaussian.factors` provides named, unit-labelled variables, one full
joint Gaussian prior, and linear factors `y = H x + noise`. Each factor
declares its source, consumed dependencies, variable order, H, y and full
positive-definite noise covariance. Factor kinds (observation,
structural_prior, calibration) label roles, not assurance levels.

The solver scales the prior into correlation coordinates before spectral
factorization, whitens observations, and solves by QR in prior latent
coordinates. It adds no covariance jitter and never inverts normal equations.
Singular prior directions are exact, not unknown. A free gauge or improper
prior is unsupported. Correlated observations belong in a single block or
must have their shared error modeled explicitly as a variable. Separate
factor noises are declared independent of each other and of the prior.

Each factor lists consumed evidence dependencies, including upstream
derivations. Reusing one across factors or against the prior is refused.
The caller must declare the complete prior dependency closure. Hidden overlap
and false provenance cannot be detected by this check. A source ID alone
does not prove independence. In-sample residuals are not calibration results.

Graph identity binds variable order/units, prior, factors and declarations;
factors are sorted by ID. Physical equivalence does not imply byte identity.
This is a small dense reference implementation, not a sparse GTSAM backend,
nonlinear optimizer, robust outlier fitter or discrete hypothesis search.

## Opening-fit bridge

`OpeningFitGraph` uses world raw-variable identities followed by opening and
assembly right-local pose tangents. It preserves raw/pose correlations and
uses the existing dimension and corner-margin Jacobians. With no factors,
it reproduces #29's prediction. Factors condition that joint distribution;
the margins are evaluated at the **fixed reference linearization**.

Output remains `gat-opening-fit-v1`, with an additive `inference` record
containing graph data, posterior, fitting residuals and reference identity.
Binding dimensions become posterior linearized means. `pose.mean_tangent`
contains corrections relative to the recorded frames, which are not rebased.
Covariances are not silently transported. The report states these limits.
Large tangent updates require nonlinear qualification; no canonical pose
update or geometric insertion-path assessment is implemented here.

## Consumer integration

- `inputs` is unknown by default, or explicitly synthetic/measured/mixed.
  This is a declaration, not authenticated provenance. The demo is synthetic.
- `coordinate_convention` states right-handed axes, metre translations,
  radian angles, aperture X/Z and passage Y. Up, CRS and epoch are null:
  arbitrary coordinate frames do not establish gravity or survey control.
- Margin rows are VIOLATED only when P(violation) >= confidence. Values
  between the decision thresholds are UNRESOLVED.
- Populated `DESCRIPTIVE_EVALUATION` results now render nominal/observed
  coverage tables under an UNVALIDATED headline. NO_MEASUREMENTS remains
  an empty state and refuses contradictory nonempty data.
- Recorded fitting sources/dependencies cannot become held-out sources
  merely by omitting the evaluator's caller-supplied fitting-source list.
- CI also triggers for PRs targeting `codex/**` and runs the combined demo.

The current headless minimum-check route assesses a decision; it does not
invoke the minimum evidence planner. `NO_AVAILABLE_EVIDENCE` remains an
engine planner outcome, not a new status emitted by this bridge.

## Reproduction

```console
python -m unittest tests.test_factor_graph tests.test_factor_rendezvous tests.test_fit_report -v
python -m gat.demo.opening_factors opening-factor-out
python -m gat.demo.workflow
```

The demo writes JSON and Claude's script-free HTML for prior, posterior,
synthetic coverage and no-measurements reports. Both its observations and
its held-out checks are invented; none establishes field calibration.

Tests compare QR inference with an independent partitioned-Gaussian oracle;
preserve heterogeneous units, shared calibration covariance and exact
directions; reject declared double counting; reproduce prior fit; compare
posterior means with analytic conditioning; and pass live engine outputs
through Claude's renderer. Claude's older JSON fixture remains a compatibility
test rather than being regenerated to hide contract changes.

The NumPy 2.4.6 legacy snapshot finding on #28 remains open. Passing locally
on NumPy 2.3.5 does not establish replay across that execution envelope.
