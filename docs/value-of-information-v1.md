# Decision value of information, v1

`gat.engine.value_of_information` adds exact one-step Bayesian decision design
over a bounded finite model. Existing `active_inference.py` and `decision.py`
continue to rank target information in nats. This new method evaluates
**expected reduction in minimum decision loss minus acquisition cost**.
It is not an expected-free-energy formula or a claim that GAT satisfies the
Free Energy Principle. It does not infer statistical Markov blankets from
architectural containment, software services, or physical walls.

## Contract and computation

`DecisionModel` declares an exact source SHA-256, model provenance/status,
joint hypotheses with prior probabilities and a boolean `fits` per hypothesis,
two positive losses (false fit and false reject), measurements, and the complete
conditional joint distribution of measurement readings for every hypothesis.
Correct decisions have zero loss in this version. The caller is responsible for
deriving `fits` from its physical criterion; this module does not compute geometry.

Costs use the **same declared unit as decision loss**, never implicit nats,
currency-to-risk conversions, or raw time mixed with monetary losses. Losses
are scenario preferences, not authority to declare compliance or move equipment.
Availability and permission are separate three-state declarations; only
AVAILABLE + PERMITTED candidates enter the ranking. These declarations do not
grant operational permission: all results carry `physical_action_authorized=false`.

For each possible reading, Bayes' rule updates the **joint** hypotheses. The
decision minimizes `P(not fit)*false_fit_loss` versus `P(fit)*false_reject_loss`.
The planner integrates that minimum loss over readings and subtracts the
measurement cost from the reduction relative to doing nothing. Stable ids break
ties; no measurement is recommended unless the gain exceeds the recorded
numerical tolerance. A decision tie selects REJECT. This binary loss decision
does not replace GAT's SATISFIED / VIOLATED / UNRESOLVED confidence assessment.

The full conditional outcome table preserves shared calibration and correlated
sensor noise. Acquisition-set evaluation marginalizes that table; it never
multiplies separate likelihoods under an undeclared independence assumption.
The one-step selector is intentionally myopic. A calibration measurement can
have zero value alone and substantial value in combination. Fixed-set comparison
supports that investigation; there is no optimal adaptive multi-step policy yet.

Bounds: 256 hypotheses, 16 measurements, 4096 joint outcomes, 64 latent values
per hypothesis. Inputs require finite numbers, consistent identities, normalized
probabilities and complete conditional coverage. Zero-probability readings never
become posterior beliefs. Continuous distributions are not silently quantized;
finite outcome values are model declarations. There is no automatic Gaussian
World/factor-graph adapter or posterior admission into the canonical ledger.

## Reproducible clearance experiment

Run `python -m gat.demo.clearance_voi` to emit the source, canonical model,
ranked plan, all hypothetical posterior branches, comparator results, and digests.
`examples/clearance-voi.json` is a saved result readable without recomputation.
Digests bind the source, model and results; they do not authenticate evidence.

The eight synthetic joint hypotheses combine opening width (2.00 or 2.02 m),
an instrument offset (0 or 0.02 m), and an unrelated panel offset. Equipment
width is fixed at 2.01 m. The opening survey includes the instrument offset;
the calibration survey reveals it. These are generated finite likelihoods,
not independently calibrated sensors. In particular the instrument offset is
not a rigid coordinate-frame translation applied to a width.

False fit costs 10 and false reject costs 2 in declared loss units:

| Fixed measurement policy | Expected decision loss | Cost | Total |
| --- | ---: | ---: | ---: |
| None | 1.00 | 0.00 | 1.00 |
| One-step VOI: opening | 0.50 | 0.10 | 0.60 |
| Cheapest first: panel | 1.00 | 0.01 | 1.01 |
| Largest reading variance first: panel | 1.00 | 0.01 | 1.01 |
| Measure everything | 0.00 | 0.26 | 0.26 |
| Opening + calibration | 0.00 | 0.25 | 0.25 |

The variance comparator is deliberately naive and restricted to these readings
in metres. It is not a valid cross-unit ranking rule. These are fixed acquisition
sets; the first two heuristic policies each take one measurement, not a full
adaptive sequence. Measuring everything buys more information at greater cost.
The example does not claim one-step VOI beats all bundles.

Decision error and Brier score in the artifacts are **model expectations**.
They are not held-out decision accuracy or uncertainty calibration. Independent
evaluation remains `NOT_AVAILABLE`: a separate trial dataset must provide actual
measurement outcomes and independently established fit labels before comparing
empirical loss, costs and calibration. No field-accuracy claim is made.

## Claude / frontend handoff

Render the saved plan and source/model bindings as a distinct analysis artifact,
not a released corpus. Show baseline loss, candidate cost, expected posterior
loss, net value, excluded availability/permission declarations and every possible
reading's posterior decision. Use text for model labels and provenance. Display
`SYNTHETIC` prominently. A recommendation is a proposed measurement, never a
physical FIT verdict or an acquisition button backed by this module.

Keep independent validation separate from predicted benefit. A future retained
Notations Compute API can carry this contract after introducing a strict JSON
parser, source-policy checks and an immutable execution receipt. This increment
provides the Python core and inspectable artifact, not that HTTP integration.
