from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.test.generate_test_mk_selectors import PACK_VARIABLES
from ops.scripts.test.test_lane_registry_runtime import (
    compatibility_map,
    excluded_markers_from_expr,
    load_registry,
    module_level_pytest_marks,
    pack_by_id,
    pack_deselects,
    pack_effective_selectors,
    pack_mark_expr,
    pack_selection_mode,
    pack_selectors,
    pytest_marker_docs,
)


class TestLaneRegistryMarkerFilteringTests(unittest.TestCase):
    def test_marker_expression_schema_rejects_selector_exceptions(self) -> None:
        schema = load_schema(Path("ops/schemas/test-lane-registry.schema.json"))

        for field, value in (
            ("selectors", ["tests/test_sample.py"]),
            ("deselects", ["tests/test_sample.py::test_one"]),
        ):
            with self.subTest(field=field):
                registry = deepcopy(load_registry(Path()))
                for pack in registry["derived_packs"]:
                    if pack["pack_id"] != "fast_smoke":
                        continue
                    pack["selection"][field] = value
                    break
                else:  # pragma: no cover - protected by registry fixture shape
                    raise AssertionError("missing fast_smoke pack")

                errors = validate_with_schema(registry, schema)

                self.assertTrue(errors)

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

    def test_explicit_selector_effective_selectors_exclude_module_slow_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_fast.py").write_text("def test_fast(): pass\n", encoding="utf-8")
            (tests_dir / "test_slow.py").write_text(
                "import pytest\n\npytestmark = pytest.mark.slow\n\ndef test_slow(): pass\n",
                encoding="utf-8",
            )
            registry = {
                "derived_packs": [
                    {
                        "pack_id": "sample",
                        "selection": {
                            "mode": "explicit_selectors",
                            "pytest_mark_expr": "not slow",
                            "selectors": [
                                "tests/test_fast.py",
                                "tests/test_slow.py",
                            ],
                        },
                    }
                ]
            }

            effective = pack_effective_selectors(registry, "sample", vault=root)

        self.assertEqual(effective, ("tests/test_fast.py",))

    def test_fast_smoke_is_marker_pack_without_nodeid_exceptions(self) -> None:
        registry = load_registry(Path())

        self.assertEqual(pack_selection_mode(registry, "fast_smoke"), "marker_expression")
        self.assertEqual(pack_mark_expr(registry, "fast_smoke"), "fast_smoke")
        self.assertEqual(pack_selectors(registry, "fast_smoke"), ())
        self.assertEqual(pack_deselects(registry, "fast_smoke"), ())

    def test_curated_core_packs_are_marker_owned(self) -> None:
        registry = load_registry(Path())

        for pack_id in (
            "runtime_hotspot_smoke",
            "report_contract_core",
            "release_sealing_core",
        ):
            with self.subTest(pack_id=pack_id):
                self.assertEqual(pack_selection_mode(registry, pack_id), "marker_expression")
                self.assertEqual(pack_mark_expr(registry, pack_id), pack_id)

    def test_generated_selector_projection_packs_are_marker_owned(self) -> None:
        registry = load_registry(Path())
        marker_docs = pytest_marker_docs(registry)

        for pack_id in PACK_VARIABLES:
            with self.subTest(pack_id=pack_id):
                self.assertEqual(pack_selection_mode(registry, pack_id), "marker_expression")
                self.assertIn(pack_mark_expr(registry, pack_id), marker_docs)
                self.assertEqual(pack_selectors(registry, pack_id), ())
                self.assertEqual(pack_deselects(registry, pack_id), ())

    def test_remaining_explicit_selector_packs_are_make_target_wrappers(self) -> None:
        registry = load_registry(Path())
        make_target_compatibility = compatibility_map(registry, "make_target")

        for pack_id in pack_by_id(registry):
            if pack_selection_mode(registry, pack_id) != "explicit_selectors":
                continue
            with self.subTest(pack_id=pack_id):
                self.assertNotIn(pack_id, PACK_VARIABLES)
                selectors = pack_selectors(registry, pack_id)
                self.assertTrue(selectors)
                for selector in selectors:
                    self.assertEqual(make_target_compatibility.get(selector), pack_id)
