from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ops.scripts.test.test_lane_registry_runtime import (
    excluded_markers_from_expr,
    load_registry,
    module_level_pytest_marks,
    pack_effective_selectors,
)


class TestLaneRegistryMarkerFilteringTests(unittest.TestCase):
    def test_excluded_markers_from_expr_parses_negated_marks(self) -> None:
        self.assertEqual(
            excluded_markers_from_expr("not slow and not integration_heavy"),
            {"slow", "integration_heavy"},
        )

    def test_module_level_pytest_marks_detects_slow_marker(self) -> None:
        marks = module_level_pytest_marks(Path("tests/test_auto_improve_readiness_runtime.py"))
        self.assertIn("slow", marks)

    def test_module_level_pytest_marks_detects_multiline_pytestmark(self) -> None:
        with TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test_multiline_marks.py"
            test_file.write_text(
                "import pytest\n\n"
                "pytestmark = [\n"
                "    pytest.mark.slow,\n"
                "    pytest.mark.integration_heavy,\n"
                "]\n",
                encoding="utf-8",
            )

            marks = module_level_pytest_marks(test_file)

        self.assertEqual(marks, {"slow", "integration_heavy"})

    def test_fast_smoke_effective_selectors_exclude_module_slow_files(self) -> None:
        registry = load_registry(Path())
        effective = pack_effective_selectors(registry, "fast_smoke", vault=Path())

        for selector in effective:
            module_marks = module_level_pytest_marks(
                Path(selector.split("::", 1)[0])
            )
            with self.subTest(selector=selector):
                self.assertNotIn("slow", module_marks)
                self.assertNotIn("integration_heavy", module_marks)
        self.assertIn("tests/test_auto_improve_readiness_queue_runtime.py", effective)
