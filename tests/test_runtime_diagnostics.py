"""Execution diagnostics must not become a substitute for exact identity."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from gat.session import GatSession
from gat.errors import SnapshotError
from gat.runtime_diagnostics import (
    REPLAY_CRITICAL, dropped_by, execution_environment, replay_critical_facts)
from gat.state_snapshot import _content_digest, capture_snapshot, reconstruct_snapshot
from validation.qualify_execution import qualify


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_environment_is_explicit_and_does_not_export_build_paths(self):
        report = execution_environment()
        self.assertEqual(report["contract"], "gat-execution-diagnostics-v1")
        self.assertEqual(report["qualified_numpy"], "2.3.5")
        for library in report["libraries"].values():
            self.assertFalse(any("directory" in key for key in library))

    def test_mismatch_is_refused_with_digests_and_runtime(self):
        world = GatSession.load_ifc(Path(__file__).parents[1] / "gat/demo/model.ifc").world
        document = capture_snapshot(world)
        document["payload"]["source_world_digest"] = "0"*64
        document["integrity"]["digest"] = _content_digest(document)
        original = copy.deepcopy(document)
        with self.assertRaises(SnapshotError) as error:
            reconstruct_snapshot(document)
        self.assertIn("exact continuation refused", str(error.exception))
        self.assertIn(world.digest(), str(error.exception))
        self.assertIn('"numpy"', str(error.exception))
        self.assertEqual(document, original)

    def test_every_replay_critical_fact_is_one_the_contract_emits(self):
        """A producer cannot name a fact its own report has no place for."""
        report = execution_environment()
        for path in REPLAY_CRITICAL:
            head, _, tail = path.partition(".")
            self.assertIn(head, report, path)
            if tail:
                self.assertIsInstance(report[head], dict, path)

    def test_an_unrecorded_control_is_reported_as_absent_and_never_omitted(self):
        """An unset control is not a default control; the gap is a value."""
        with patch.dict("os.environ", {"OPENBLAS_CORETYPE": "Haswell"}, clear=False):
            facts = replay_critical_facts()
        self.assertEqual(facts["controls.OPENBLAS_CORETYPE"], "Haswell")
        environment = {key: value for key, value in __import__("os").environ.items()
                       if not key.startswith(("OPENBLAS_", "OMP_", "MKL_", "NPY_"))}
        with patch.dict("os.environ", environment, clear=True):
            bare = replay_critical_facts()
        self.assertEqual(set(bare), set(REPLAY_CRITICAL))
        self.assertIsNone(bare["controls.OPENBLAS_CORETYPE"])

    def test_a_consumer_that_carries_versions_alone_drops_the_dispatch(self):
        """The observed case: a boundary keeping interpreter and platform only."""
        dropped = dropped_by(["python", "numpy", "system", "machine"])
        self.assertIn("libraries.blas", dropped)
        self.assertIn("controls.OPENBLAS_CORETYPE", dropped)
        self.assertIn("controls.OPENBLAS_NUM_THREADS", dropped)
        self.assertEqual((), dropped_by(REPLAY_CRITICAL))

    def test_qualification_does_not_accept_an_undeclared_numpy(self):
        with patch("validation.qualify_execution.np.__version__", "unqualified-test-runtime"):
            report = qualify()
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["declared_numpy_version"])


if __name__ == "__main__":
    unittest.main()
