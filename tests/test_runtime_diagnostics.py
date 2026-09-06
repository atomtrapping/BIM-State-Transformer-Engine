"""Execution diagnostics must not become a substitute for exact identity."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from gat.session import GatSession
from gat.errors import SnapshotError
from gat.runtime_diagnostics import execution_environment
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

    def test_qualification_does_not_accept_an_undeclared_numpy(self):
        with patch("validation.qualify_execution.np.__version__", "unqualified-test-runtime"):
            report = qualify()
        self.assertFalse(report["qualified"])
        self.assertFalse(report["checks"]["declared_numpy_version"])


if __name__ == "__main__":
    unittest.main()
