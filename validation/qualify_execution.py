"""Qualify the unchanged historical identity on this actual numerical runtime."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

# Also supports source-tree invocation without an editable install.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from gat.ledger import read_ledger, replay_ledger
from gat.runtime_diagnostics import QUALIFIED_NUMPY, execution_environment
from gat.session import GatSession


EXPECTED = "f628952eaff3bac72edf1705da3d66e196bb6ee2736382535bd3f3c33a73a2ad"


def qualify():
    fixtures = ROOT / "tests/fixtures/identity"
    checks, errors = {}, []
    report = {"contract": "gat-execution-qualification-v1", "environment": execution_environment(),
              "expected_world_digest": EXPECTED, "checks": checks, "errors": errors,
              "fixture_sha256": {name: hashlib.sha256((fixtures/name).read_bytes()).hexdigest()
                                 for name in ("legacy-v1-snapshot.json", "legacy-v1-ledger.json")},
              "scope": "this historical import/snapshot/ledger; not every computation or platform"}
    checks["declared_numpy_version"] = np.__version__ == QUALIFIED_NUMPY
    controls = report["environment"]["controls"]
    checks["declared_blas_core"] = controls.get("OPENBLAS_CORETYPE") == "Haswell"
    checks["declared_blas_threads"] = controls.get("OPENBLAS_NUM_THREADS") == "1"
    try:
        source = (ROOT / "gat/demo/model.ifc").read_bytes().decode("utf-8")
        imported = GatSession.from_text(source, source="legacy-v1-model.ifc", identity_version=1)
        report["imported_world_digest"] = imported.world.digest()
        checks["legacy_import_identity"] = imported.world.digest() == EXPECTED
    except Exception as exc:
        checks["legacy_import_identity"] = False
        errors.append(f"import: {exc}")
    try:
        restored = GatSession.load_snapshot(str(fixtures/"legacy-v1-snapshot.json"))
        checks["legacy_snapshot_identity"] = restored.world.digest() == EXPECTED
        replayed = replay_ledger(restored.world, read_ledger(fixtures/"legacy-v1-ledger.json"))
        checks["legacy_ledger_identity"] = replayed.world.digest() == EXPECTED
    except Exception as exc:
        checks["legacy_snapshot_and_ledger"] = False
        errors.append(f"snapshot/ledger: {exc}")
    report["qualified"] = all(checks.values()) and not errors
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = qualify()
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
