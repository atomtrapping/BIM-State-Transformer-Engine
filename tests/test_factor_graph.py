"""Independent linear-Gaussian oracles and evidence-dependence refusals."""
import unittest

import numpy as np

from gat.gaussian.factors import FactorVariable, GaussianFactorGraph, LinearFactor


class FactorGraphTests(unittest.TestCase):
    def graph(self, mean=(0, 0), covariance=((2, 0.5), (0.5, 1))):
        return GaussianFactorGraph(tuple(FactorVariable(name, "m") for name in ("x", "y")), mean, covariance, ("prior-source",))

    def factor(self, id="f", dependencies=("measurement-1",)):
        return LinearFactor(id, ("x",), [[1]], [1], [[0.25]], "instrument", dependencies)

    def test_prior_only_is_exact_including_correlations(self):
        graph = self.graph()
        result = graph.solve()
        np.testing.assert_array_equal(result.mean, graph.prior_mean)
        np.testing.assert_array_equal(result.covariance, graph.prior_covariance)

    def test_matches_partitioned_gaussian_with_correlated_observation_noise(self):
        graph = self.graph()
        h = np.array([[1., 1.], [1., -1.]])
        noise = np.array([[0.3, 0.1], [0.1, 0.2]])
        observed = np.array([1., 2.])
        factor = LinearFactor("block", ("x", "y"), h, observed, noise, "instrument", ("block-1",))
        result = graph.with_factor(factor).solve()
        gain = np.linalg.solve(h @ graph.prior_covariance @ h.T + noise, h @ graph.prior_covariance).T
        np.testing.assert_allclose(result.mean, gain @ observed, atol=1e-13)
        np.testing.assert_allclose(result.covariance, graph.prior_covariance-gain @ h @ graph.prior_covariance, atol=1e-13)
        self.assertEqual(result.residuals[0]["role"], "in_sample_not_calibration")

    def test_single_measurement_updates_correlated_variable(self):
        result = self.graph().with_factor(self.factor()).solve()
        self.assertAlmostEqual(result.mean[0], 2/2.25)
        self.assertAlmostEqual(result.mean[1], 0.5/2.25)

    def test_exact_directions_are_not_regularized(self):
        graph = self.graph(mean=(2, 0), covariance=((0, 0), (0, 1)))
        result = graph.with_factor(self.factor()).solve()
        self.assertEqual(result.mean[0], 2)
        self.assertEqual(result.covariance[0, 0], 0)
        self.assertEqual(result.residuals[0]["residual"], [-1.0])

    def test_shared_calibration_bias_remains_correlated(self):
        graph = GaussianFactorGraph(tuple(FactorVariable(v, "m") for v in ("x", "y", "bias")),
                                    np.zeros(3), np.diag([100,100,1]), ("prior",))
        first = LinearFactor("a", ("x","bias"), [[1,1]], [2], [[0.01]], "sensor", ("sample-a",))
        second = LinearFactor("b", ("y","bias"), [[1,1]], [3], [[0.01]], "sensor", ("sample-b",))
        result = graph.with_factor(first).with_factor(second).solve()
        self.assertGreater(result.covariance[0,1], 0.9)
        difference_variance = result.covariance[0,0]+result.covariance[1,1]-2*result.covariance[0,1]
        self.assertLess(difference_variance, 0.021)

    def test_factor_order_does_not_change_identity_or_result(self):
        first = self.factor("a", ("a",))
        second = self.factor("b", ("b",))
        a, b = self.graph().with_factor(first).with_factor(second), self.graph().with_factor(second).with_factor(first)
        self.assertEqual(a.digest(), b.digest())
        np.testing.assert_array_equal(a.solve().mean, b.solve().mean)

    def test_duplicate_and_prior_evidence_reuse_refused(self):
        with self.assertRaisesRegex(ValueError, "reused"):
            self.graph().with_factor(self.factor(dependencies=("prior-source",)))
        graph = self.graph().with_factor(self.factor())
        with self.assertRaisesRegex(ValueError, "reused"):
            graph.with_factor(self.factor("other-id"))
        with self.assertRaisesRegex(ValueError, "duplicate factor"):
            graph.with_factor(self.factor(dependencies=("other-source",)))

    def test_unknown_variables_noise_and_prior_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.graph().with_factor(LinearFactor("f", ("absent",), [[1]], [0], [[1]], "s", ("d",)))
        for variance in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                LinearFactor("f", ("x",), [[1]], [0], [[variance]], "s", ("d",))
        with self.assertRaises(ValueError):
            self.graph(covariance=((1,2),(2,1)))

    def test_inputs_are_copied_and_frozen(self):
        covariance = np.eye(2)
        graph = self.graph(covariance=covariance)
        covariance[0,0] = 999
        self.assertEqual(graph.prior_covariance[0,0], 1)
        with self.assertRaises(ValueError):
            graph.solve().mean[0] = 1

    def test_dependency_declarations_are_required(self):
        with self.assertRaises(ValueError):
            self.factor(dependencies=())
        with self.assertRaises(ValueError):
            self.factor(dependencies="not-a-sequence")

    def test_heterogeneous_units_preserve_physical_posterior(self):
        baseline = self.graph().with_factor(self.factor()).solve()
        scale = np.array([1e6, 1e-6])
        graph = self.graph(covariance=self.graph().prior_covariance * scale[:,None] * scale[None,:])
        factor = LinearFactor("scaled", ("x",), [[1/scale[0]]], [1], [[0.25]], "instrument", ("m",))
        result = graph.with_factor(factor).solve()
        np.testing.assert_allclose(result.mean/scale, baseline.mean, atol=1e-13)
        np.testing.assert_allclose(result.covariance/scale[:,None]/scale[None,:], baseline.covariance, atol=1e-13)


if __name__ == "__main__":
    unittest.main()
