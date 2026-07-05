from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from ops.scripts.test.generate_pytest_ini_markers import (
    PYTEST_MARKERS_END,
    PYTEST_MARKERS_START,
    render_pytest_marker_block,
    synced_pytest_ini_text,
)
from ops.scripts.test.test_lane_registry_runtime import (
    load_registry,
    pytest_marker_docs,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
    pytest.mark.default_test_boundary,
]

REPO_ROOT = Path(__file__).resolve().parents[1]


class GeneratePytestIniMarkersTests(unittest.TestCase):
    def test_rendered_marker_block_is_derived_from_registry_docs(self) -> None:
        registry = load_registry(REPO_ROOT)
        rendered = render_pytest_marker_block(registry)
        lines = rendered.splitlines()

        self.assertEqual(lines[0], PYTEST_MARKERS_START)
        self.assertEqual(lines[1], "markers =")
        self.assertEqual(lines[-1], PYTEST_MARKERS_END)
        for marker, semantics in pytest_marker_docs(registry).items():
            with self.subTest(marker=marker):
                self.assertIn(f"    {marker}: {semantics}", lines)
        self.assertNotIn("deprecated compatibility alias for artifact_finalization", rendered)

    def test_sync_replaces_managed_block_without_touching_other_pytest_options(self) -> None:
        registry = load_registry(REPO_ROOT)
        original = "\n".join(
            [
                "[pytest]",
                "testpaths = tests",
                PYTEST_MARKERS_START,
                "markers =",
                "    stale_marker: stale docs",
                PYTEST_MARKERS_END,
                "addopts = -q",
                "",
            ]
        )

        updated = synced_pytest_ini_text(original, registry)

        self.assertIn("testpaths = tests", updated)
        self.assertIn("addopts = -q", updated)
        self.assertIn(PYTEST_MARKERS_START, updated)
        self.assertIn(PYTEST_MARKERS_END, updated)
        self.assertNotIn("stale_marker", updated)
        self.assertTrue(updated.endswith("\n"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
