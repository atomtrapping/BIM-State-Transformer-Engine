# Exact replay execution envelope

`gat-world-v1` hashes the module and the raw bytes of the derived float64
mean and covariance. Numerical closeness does not imply identical state.
BLAS/kernel/build differences can change those bytes. A Python/NumPy version
string alone is not a complete reproducibility guarantee.

## Observed boundary

The unchanged legacy identity fixture passed locally on Windows / Python
3.12.14 / NumPy 2.3.5 / scipy-openblas 0.3.30. Claude reported a mismatch on
Linux / Python 3.11.15 / NumPy 2.4.6. The failed PR #30 job 101395218717
installed NumPy **2.5.2** on Python 3.12 from the former `numpy>=1.24`
dependency and failed the same exact legacy reconstruction check.

These observations establish a compatibility boundary; they do not isolate
which changed BLAS instruction or NumPy operation caused every mismatch.
The dependency now pins NumPy 2.3.5. An upgrade requires the original replay
qualification on each supported Python/platform build, not a regenerated
golden fixture or an approximate numerical comparison.

## Qualification

Run after installation and before relying on historical exact continuation:

```console
python validation/qualify_execution.py --output execution-qualification.json
```

The command checks the declared NumPy version, a fresh legacy import, the
unchanged checked-in snapshot, and its unchanged ledger. Their world identity
must remain `f628952eaff3bac72edf1705da3d66e196bb6ee2736382535bd3f3c33a73a2ad`.
Failure returns a nonzero exit code; there is no skip or alternative expected
digest. The report records fixture hashes, current Python/NumPy/platform,
selected BLAS/LAPACK build facts and relevant execution controls. Build paths
and unrelated environment variables are not exported. CI retains this JSON
for both Python matrix jobs before running the full suite.

Passing qualifies this fixture's import/snapshot/ledger paths on that actual
runtime. It does not prove every matrix operation, hardware dispatch, thread
configuration, future observation update or third-party binary reproducible.
Same-environment continuation and broader invariants remain separately tested.

## Preserved identity and refusal

No historical fixture, snapshot schema, ledger event, world hash algorithm or
source digest was rewritten. A world mismatch still refuses reconstruction;
its error now reports source/reconstructed digests and runtime diagnostics.
Do not replace the source digest or relax equality to load a historical state.
Use a source-compatible qualified environment. An explicit state migration
would need its own identity and evidence policy and is not implemented here.

Diagnostics are not inserted into canonical state or snapshot payloads. Old
snapshots lack producer environment metadata, so it cannot be recovered from
their contents; retain qualification reports alongside new deployments.

The package pin is an operational restriction, not a claim that NumPy 2.3.5
is universally identical across all machines. Future execution-contract work
can define reproducible arithmetic and versioned environment metadata without
silently reinterpreting `gat-world-v1`.
