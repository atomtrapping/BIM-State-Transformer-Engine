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

The first pinned CI run qualified Python 3.12 but still refused Python 3.11
with NumPy 2.3.5. A local subprocess experiment then changed only the BLAS
core selection: Haswell preserved the golden world, while Sandybridge gave
`5c80deec20ba0422f8861c7eb13e1ed66daa109305d66c2710be69323fdc6759`.
The derived means remained byte-identical; covariance bytes differed.
Thus the qualification also declares Haswell dispatch and one BLAS thread.
This is a bounded x86-64/AVX2 configuration, not an ARM or arbitrary-CPU
contract. The numerical probe must still pass on the actual host.

## Qualification

Set controls **before starting Python**, after installation and before relying
on historical exact continuation. On a compatible x86-64/AVX2 host:

```sh
export OPENBLAS_CORETYPE=Haswell
export OPENBLAS_NUM_THREADS=1
python validation/qualify_execution.py --output execution-qualification.json
```

PowerShell uses `$env:OPENBLAS_CORETYPE='Haswell'` and
`$env:OPENBLAS_NUM_THREADS='1'` before the same Python command. GAT's library
import does not overwrite caller process settings. CI declares both controls
for every job. Reusing an already-imported NumPy process is not sufficient.

The command checks the NumPy version and declared controls, a fresh legacy import, the
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

## What a consumer must carry

The sections above address an operator setting up a host. A consumer that
embeds GAT as a pinned runtime has the same problem through a narrower opening:
it records some facts about the execution and drops the rest, and whatever it
drops is what its own replay claim is not evidenced by.

`gat.runtime_diagnostics.REPLAY_CRITICAL` names the thirteen dotted paths that
decide the bytes, and `dropped_by(carried)` answers what a given boundary loses.
The producer names them because the producer is what watched them matter: this
repository has seen Haswell and Sandybridge dispatch give byte-identical derived
means and different covariance bytes from the same inputs. A Python and NumPy
version pair does not describe an envelope, and a boundary carrying only those
has kept the facts that are easy to serialise and dropped the one the finding
was about.

`replay_critical_facts()` reports an unrecorded control as `None` rather than
omitting the key. An unset control is not a default control — it means the host
took whatever dispatch it found, which is exactly the condition under which the
covariance bytes moved — and a shape that omits it leaves a consumer unable to
tell an unset control from one nobody looked for.

The observed instance: Payload OS pins this engine as a local runtime and its
`GatRuntimeIdentity` carries the engine commit, source tree digest, adapter
version, Python version, NumPy version, platform and architecture. Nine of the
thirteen replay-critical facts do not cross, including both library builds and
all five controls. Its grader marks such a run `REPLAYABLE_HERE`, which is
right about the arithmetic and unevidenced about the word *here*: nothing in the
receipt says which envelope that was. Its `src/gat/crossing.ts` records the drop
against this list rather than repairing it, and the two sides now name the same
facts, which is what makes the gap measurable instead of arguable.

Nothing here fixes that boundary. A producer can say which facts matter; it
cannot reach into a shape somebody else declared.

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
