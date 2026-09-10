# Replayable transition commitment (optional attested arithmetic) v1

Historical filename: `proof-carrying-state-v1.md`. The artifact is a
**replayable transition commitment** plus an optional bounded arithmetic
guest. It is not a proof that the building, the Gaussian update, or the
observations are correct.

## Purpose

`gat-computation-proof-manifest` is a portable commitment to one accepted GAT
state transition and its external proof artifact. It answers:

> Does this proof claim concern this exact accepted operation, prior state,
> result state, invariant report, numerical contract, and ledger history?

It does not answer whether the observations were truthful, the calibration was
representative, the engineering model was appropriate, or the building is
safe. Those are evidence, calibration, validation, and professional-authority
questions outside the proof claim.

The permitted claim scope is fixed in schema v1:

```text
computational-integrity-only
```
