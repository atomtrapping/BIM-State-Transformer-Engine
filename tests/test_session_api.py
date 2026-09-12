"""The GatSession public surface is a contract, not an accident.

`main` once carried a `GatSession` that had lost 19 of its 20 public methods
to a bad merge.  Every downstream module still imported it, so the failure
surfaced as 221 unrelated test errors rather than as one clear message.
This module pins the surface itself: if a constructor, a recorder, or an
exporter disappears again, exactly one test fails and it says which.
"""

from __future__ import annotations

import inspect
import unittest

from gat.session import GatSession


#: Every public entry point the engine, CLI, demos, and headless boundary
#: rely on.  Adding to this set is fine; removing from it is a breaking
#: change that must be deliberate.
REQUIRED_SURFACE: frozenset[str] = frozenset(
    {
        # constructors
        "load_ifc",
        "from_text",
        "load_snapshot",
        "load_openusd",
        "load_usd",
        # queries
        "entity_by_name",
        "var",
        "verify",
        # execution
        "run",
        # causal record keeping
        "record_assessment",
        "record_policy",
        "record_approval",
        "record_external_action",
        # exports
        "export_ifc",
        "export_json",
        "export_usd",
        "export_openusd",
        "export_snapshot",
        "export_ledger",
    }
)

#: Constructors are classmethods; losing that binding breaks every caller.
REQUIRED_CLASSMETHODS: frozenset[str] = frozenset(
    {"load_ifc", "from_text", "load_snapshot", "load_openusd", "load_usd"}
)


class SessionSurfaceTests(unittest.TestCase):
    def test_every_required_method_is_present_and_callable(self) -> None:
        missing = sorted(
            name
            for name in REQUIRED_SURFACE
            if not callable(getattr(GatSession, name, None))
        )
        self.assertEqual(
            missing,
            [],
            "GatSession lost public methods: " + ", ".join(missing),
        )

    def test_constructors_are_classmethods(self) -> None:
        for name in sorted(REQUIRED_CLASSMETHODS):
            with self.subTest(constructor=name):
                attribute = inspect.getattr_static(GatSession, name)
                self.assertIsInstance(
                    attribute,
                    classmethod,
                    f"GatSession.{name} must stay a classmethod",
                )

    def test_instances_expose_the_audit_state(self) -> None:
        for name in ("world", "trace", "ledger", "initial_report"):
            with self.subTest(attribute=name):
                self.assertIn(
                    name,
                    inspect.getsource(GatSession.__init__),
                    f"GatSession.__init__ must still establish {name!r}",
                )

    def test_load_ifc_accepts_a_lowering_scope(self) -> None:
        signature = inspect.signature(GatSession.load_ifc)
        self.assertIn("scope", signature.parameters)
        self.assertIsNone(signature.parameters["scope"].default)


if __name__ == "__main__":
    unittest.main()
