from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from ops.scripts.test.test_lane_registry_runtime import (
    load_registry,
    pack_documented_entrypoints,
    pack_mark_expr,
)
from tests.makefile_static_helpers import (
    _assert_collected_paths_are_tests,
    _assert_collected_paths_self_declare_marker,
    _collect_marker_path_counts,
    _makefile_text,
    _target_block,
    _target_dependencies,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
    pytest.mark.default_test_boundary,
]

DOCS_DEVELOPMENT = Path("docs/development.md")
REPO_ROOT = Path(__file__).resolve().parents[1]


class MakefileFastSmokeStaticGateTests(unittest.TestCase):
    def test_fast_smoke_is_curated_developer_feedback_loop(self) -> None:
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "fast-smoke")
        registry = load_registry(REPO_ROOT)

        self.assertIn("fast-smoke", _target_block(text, ".PHONY"))
        self.assertIn(
            "make fast-smoke",
            pack_documented_entrypoints(registry, "fast_smoke"),
        )
        self.assertIn("`make fast-smoke`", development_text)
        self.assertIn(
            "$(PYTHON) -m pytest $(FAST_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)",
            block,
        )
        self.assertNotIn("lint", block)
        self.assertNotIn("eval", block)
        self.assertNotIn("stage2-eval", block)
        self.assertNotIn("release-smoke", block)

    def test_runtime_hotspot_smoke_is_curated_decomposition_feedback_loop(self) -> None:
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "runtime-hotspot-smoke")
        registry = load_registry(REPO_ROOT)

        self.assertIn("runtime-hotspot-smoke", _target_block(text, ".PHONY"))
        self.assertIn(
            "make runtime-hotspot-smoke",
            pack_documented_entrypoints(registry, "runtime_hotspot_smoke"),
        )
        self.assertIn("`make runtime-hotspot-smoke`", development_text)
        self.assertIn(
            "$(PYTHON) -m pytest -q $(RUNTIME_HOTSPOT_SMOKE_TESTS) "
            "$(PYTEST_CACHE_ISOLATION_FLAGS) $(PYTEST_SERIAL_FLAGS)",
            block,
        )
        self.assertNotIn("test-report-contract", block)
        self.assertNotIn("test-fast", block)

    def test_runtime_hotspot_smoke_collects_via_supported_entrypoint(self) -> None:
        registry = load_registry(REPO_ROOT)
        collected_by_path = _collect_marker_path_counts(
            pack_mark_expr(registry, "runtime_hotspot_smoke"),
            failure_label="RUNTIME_HOTSPOT_SMOKE_TESTS",
        )
        _assert_collected_paths_are_tests(self, collected_by_path)
        _assert_collected_paths_self_declare_marker(
            self,
            collected_by_path,
            "runtime_hotspot_smoke",
        )

    def test_default_test_boundary_is_chained_into_make_test(self) -> None:
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "test-boundary-contract-smoke")
        registry = load_registry(REPO_ROOT)

        self.assertIn("test-boundary-contract-smoke", _target_block(text, ".PHONY"))
        self.assertEqual(
            _target_dependencies(text, "test"),
            ("test-fast", "test-boundary-contract-smoke"),
        )
        self.assertEqual(
            pack_documented_entrypoints(registry, "default_test_boundary"),
            ("make test", "make test-boundary-contract-smoke"),
        )
        self.assertIn("`make test-boundary-contract-smoke`", development_text)
        self.assertIn(
            "$(PYTHON) -m pytest $(DEFAULT_TEST_BOUNDARY_TESTS) $(PYTEST_SERIAL_FLAGS)",
            block,
        )

    def test_default_test_boundary_collects_via_supported_entrypoint(self) -> None:
        registry = load_registry(REPO_ROOT)
        collected_by_path = _collect_marker_path_counts(
            pack_mark_expr(registry, "default_test_boundary"),
            failure_label="DEFAULT_TEST_BOUNDARY_TESTS",
        )
        _assert_collected_paths_are_tests(self, collected_by_path)
        _assert_collected_paths_self_declare_marker(
            self,
            collected_by_path,
            "default_test_boundary",
        )

    def test_fast_smoke_selectors_collect_via_supported_pytest_entrypoint(self) -> None:
        registry = load_registry(REPO_ROOT)
        collected_by_path = _collect_marker_path_counts(
            pack_mark_expr(registry, "fast_smoke"),
            failure_label="FAST_SMOKE_TESTS",
        )
        _assert_collected_paths_are_tests(self, collected_by_path)
        _assert_collected_paths_self_declare_marker(
            self,
            collected_by_path,
            "fast_smoke",
        )
