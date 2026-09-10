"""Sparse inventory is a reading of IR relationships, not a second oracle."""

from __future__ import annotations

from pathlib import Path
import unittest

import gat.demo
from gat.gaussian.sparse_factors import inventory_sparse_factors
from gat.session import GatSession


class SparseFactorTests(unittest.TestCase):
    def test_office_demo_has_contains_and_voids_cliques(self) -> None:
        session = GatSession.load_ifc(str(Path(gat.demo.__file__).parent / "model.ifc"))
        inventory = inventory_sparse_factors(session.world)
        self.assertEqual(inventory.world_digest, session.world.digest())
        self.assertGreater(inventory.contains_cliques, 0)
        self.assertGreater(inventory.voids_cliques, 0)
        self.assertEqual(
            inventory.dense_covariance_entries,
            inventory.raw_variables * inventory.raw_variables,
        )


if __name__ == "__main__":
    unittest.main()
