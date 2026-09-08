"""Non-authoritative numerical environment diagnostics; never a world identity."""
import os
import platform
import sys

import numpy as np


QUALIFIED_NUMPY = "2.3.5"


def execution_environment():
    """Selected environment facts, excluding build paths and unrelated env vars.

    Matching metadata does not prove bitwise reproducibility. The unchanged
    snapshot/ledger tests qualify actual replay in the current environment.
    """
    build = getattr(np.__config__, "CONFIG", {}).get("Build Dependencies", {})
    return {
        "contract": "gat-execution-diagnostics-v1",
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "numpy": np.__version__, "qualified_numpy": QUALIFIED_NUMPY,
        "system": platform.system(), "machine": platform.machine(), "byteorder": sys.byteorder,
        "libraries": {name: {key: value for key, value in build.get(name, {}).items()
                             if key in ("name", "version", "openblas configuration")}
                      for name in ("blas", "lapack")},
        "controls": {key: os.environ[key] for key in (
            "OPENBLAS_CORETYPE", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_CBWR", "NPY_DISABLE_CPU_FEATURES") if key in os.environ},
    }

# The facts a downstream consumer must carry for a replay claim to mean
# anything. Named here because the producer is the one that knows which of them
# decide the bytes: this repository has watched Haswell and Sandybridge dispatch
# give byte-identical derived means and different covariance bytes from the same
# inputs, so a version string alone does not describe an envelope. A consumer
# that embeds GAT as a pinned runtime and records only interpreter and platform
# has dropped the dimension its own replay claim turns on.
REPLAY_CRITICAL = (
    "python", "implementation", "numpy", "system", "machine", "byteorder",
    "libraries.blas", "libraries.lapack",
    "controls.OPENBLAS_CORETYPE", "controls.OPENBLAS_NUM_THREADS",
    "controls.OMP_NUM_THREADS", "controls.MKL_CBWR", "controls.NPY_DISABLE_CPU_FEATURES",
)


def replay_critical_facts(report=None):
    """Every replay-critical fact by dotted path, with None where none was recorded.

    Absence is reported rather than omitted. `execution_environment` lists only
    the controls that are set, which leaves a consumer unable to tell an unset
    control from one nobody looked for once the shape is flattened. An unset
    control is not a default control: it means the host took whatever dispatch
    it found, which is precisely the condition under which the covariance bytes
    moved. Reported as None so the gap is a value rather than a missing key.
    """
    report = execution_environment() if report is None else report
    facts = {}
    for path in REPLAY_CRITICAL:
        head, _, tail = path.partition(".")
        value = report.get(head)
        facts[path] = value if not tail else (value or {}).get(tail)
    return facts


def dropped_by(carried):
    """The replay-critical facts a consumer's boundary does not carry across.

    `carried` is the dotted paths that boundary retains. The answer is what its
    replay claim is not evidenced by, and it is the consumer's to state rather
    than this module's to fix: a producer can say which facts matter and cannot
    reach into the shape somebody else declared.
    """
    retained = set(carried)
    return tuple(path for path in REPLAY_CRITICAL if path not in retained)
