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
