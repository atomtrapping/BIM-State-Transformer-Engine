"""The IfcOpenShell adapter is optional and fail-closed."""

from __future__ import annotations

import os
import unittest

from gat.adapters.ifcopenshell_adapter import (
    IfcOpenShellAdapterError,
    ifcopenshell_available,
    inventory_with_ifcopenshell,
)


class IfcOpenShellAdapterTests(unittest.TestCase):
    def test_missing_runtime_fails_closed(self) -> None:
        if ifcopenshell_available():
            self.skipTest("ifcopenshell is installed in this environment")
        model = os.path.join(os.path.dirname(__file__), "..", "gat", "demo", "model.ifc")
        with self.assertRaisesRegex(IfcOpenShellAdapterError, "not installed"):
            inventory_with_ifcopenshell(model)

    def test_installed_runtime_does_not_claim_solid_authority(self) -> None:
        if not ifcopenshell_available():
            self.skipTest("ifcopenshell extra is not installed")
        model = os.path.join(os.path.dirname(__file__), "..", "gat", "demo", "beam_model.ifc")
        inventory = inventory_with_ifcopenshell(model)
        self.assertGreaterEqual(inventory.product_count, 1)
        self.assertEqual(inventory.geometry_authority, "INSUFFICIENT")


if __name__ == "__main__":
    unittest.main()
