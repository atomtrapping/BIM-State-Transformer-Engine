"""Sparse information form matches dense Σ on small worlds and stays linear."""

from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

import gat.demo
from gat.demo.incremental_scale import dense_state_bytes, synthetic_storey_module
from gat.engine.executor import World
from gat.engine.propagate import jacobian_rows
from gat.errors import NumericalError
from gat.gaussian.condition import condition
from gat.gaussian.information import (
    DENSE_MATERIALIZE_LIMIT,
    from_prior_belief,
    from_world,
)
from gat.gaussian.state import GaussianState, VarIndex
from gat.ids import EntityId, VarId
from gat.session import GatSession


def _state(mu, sigma, names=None):
    n = len(mu)
    if names is None:
        names = [f"q{i}" for i in range(n)]
    entity = EntityId("IfcWall", "TESTENTITY0000000000")
    variables = tuple(VarId(entity, name) for name in names)
    return GaussianState(VarIndex(variables), np.asarray(mu), np.asarray(sigma))


class InformationFormTests(unittest.TestCase):
    def test_diagonal_prior_stays_linear_in_n(self) -> None:
        world = World.compile(synthetic_storey_module(400))
        info = from_world(world)
        self.assertEqual(info.n, 400)
        self.assertEqual(info.nnz, 400)
        self.assertEqual(len(info.components()), 400)
        self.assertLess(info.resident_bytes(), dense_state_bytes(400, 1200) // 20)
        self.assertEqual(world.digest(), World.compile(synthetic_storey_module(400)).digest())
        with self.assertRaisesRegex(NumericalError, "refusing to materialize"):
            info.to_dense()

    def test_means_and_variances_match_dense_prior(self) -> None:
        world = World.compile(synthetic_storey_module(12))
        info = from_world(world)
        dense = info.to_dense()
        np.testing.assert_allclose(dense.mu, world.belief.mu, atol=1e-12, rtol=0.0)
        np.testing.assert_allclose(dense.sigma, world.belief.sigma, atol=1e-12, rtol=0.0)
        target = world.binding.raw_index.vars[0]
        self.assertAlmostEqual(info.mean(target), world.belief.mean(target), places=12)
        self.assertAlmostEqual(info.variance(target), world.belief.var_of(target), places=12)

    def test_office_demo_prior_matches_and_does_not_change_digest(self) -> None:
        session = GatSession.load_ifc(str(Path(gat.demo.__file__).parent / "model.ifc"))
        before = session.world.digest()
        info = from_world(session.world)
        self.assertEqual(session.world.digest(), before)
        self.assertEqual(info.nnz, session.world.binding.n_raw)
        for var in session.world.binding.raw_index.vars:
            self.assertAlmostEqual(
                info.mean(var), session.world.belief.mean(var), places=12
            )
            self.assertAlmostEqual(
                info.variance(var), session.world.belief.var_of(var), places=12
            )

    def test_condition_matches_joseph_on_coupled_observation(self) -> None:
        prior = _state(
            [3.0, 2.0],
            [[0.04, 0.01], [0.01, 0.09]],
            names=["a", "b"],
        )
        H = np.array([[1.0, 1.0]])
        predicted = np.array([5.0])
        observed = np.array([5.5])
        noise = np.array([0.01])
        expected, record = condition(prior, H, predicted, observed, noise)
        sparse, sparse_record = from_prior_belief(prior).condition(
            H, predicted, observed, noise
        )
        got = sparse.to_dense()
        np.testing.assert_allclose(got.mu, expected.mu, atol=1e-12, rtol=0.0)
        np.testing.assert_allclose(got.sigma, expected.sigma, atol=1e-12, rtol=0.0)
        self.assertEqual(sparse_record.innovations, record.innovations)
        self.assertEqual(len(sparse.components()), 1)

    def test_derived_observation_stays_inside_its_support(self) -> None:
        session = GatSession.load_ifc(str(Path(gat.demo.__file__).parent / "model.ifc"))
        volume = session.var("Office-A", "Volume")
        H, predicted = jacobian_rows(
            session.world.binding, session.world.belief, (volume,)
        )
        observed = predicted + 0.2
        noise = np.array([0.05**2])
        dense_post, _ = condition(session.world.belief, H, predicted, observed, noise)
        sparse_post, _ = from_world(session.world).condition(
            H, predicted, observed, noise
        )
        support = tuple(
            session.world.binding.raw_index.var(int(col))
            for col in np.flatnonzero(H[0])
        )
        self.assertGreaterEqual(len(support), 2)
        for var in support:
            self.assertAlmostEqual(
                sparse_post.mean(var), dense_post.mean(var), places=10
            )
            self.assertAlmostEqual(
                sparse_post.variance(var), dense_post.var_of(var), places=10
            )
        untouched = [
            var
            for var in session.world.binding.raw_index.vars
            if var not in support
        ]
        self.assertGreater(len(untouched), 0)
        for var in untouched:
            self.assertAlmostEqual(
                sparse_post.mean(var), session.world.belief.mean(var), places=12
            )

    def test_materialize_limit_is_the_published_gate(self) -> None:
        self.assertEqual(DENSE_MATERIALIZE_LIMIT, 256)


if __name__ == "__main__":
    unittest.main()
