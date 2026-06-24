from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

from ops.scripts.test.test_lane_registry_runtime import (
    load_registry,
    pack_effective_selectors,
    pack_selectors,
)
from tests.makefile_static_helpers import (
    _makefile_text,
    _target_block,
)
from tests.test_makefile_static_gates import _makefile_assignment_items

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

DOCS_DEVELOPMENT = Path("docs/development.md")
REPO_ROOT = Path(__file__).resolve().parents[1]


class MakefileFastSmokeStaticGateTests(unittest.TestCase):
    def test_fast_smoke_is_curated_developer_feedback_loop(self) -> None:
        registry = load_registry(REPO_ROOT)
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "fast-smoke")
        expected_tests = pack_effective_selectors(registry, "fast_smoke")

        self.assertIn("fast-smoke", _target_block(text, ".PHONY"))
        self.assertIn(
            "PYTEST_FAST_SMOKE_MARK_EXPR ?= not slow and not integration_heavy", text
        )
        self.assertIn("FAST_SMOKE_TESTS ?=", text)
        self.assertIn(
            "`make fast-smoke` is the curated Subagent/developer precheck pytest slice.",
            development_text,
        )
        for test_path in expected_tests:
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, text)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_FAST_SMOKE_MARK_EXPR)" $(FAST_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)',
            block,
        )
        self.assertNotIn("lint", block)
        self.assertNotIn("eval", block)
        self.assertNotIn("stage2-eval", block)
        self.assertNotIn("release-smoke", block)
        self.assertNotIn("tests/test_report_generation_smoke.py", block)
        self.assertNotIn("tests/test_mutation_proposal.py \\", block)
        self.assertNotIn("tests/test_artifact_freshness_runtime.py \\", block)
        self.assertNotIn("tests/test_release_smoke.py \\", block)

    def test_runtime_hotspot_smoke_is_curated_decomposition_feedback_loop(self) -> None:
        registry = load_registry(REPO_ROOT)
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "runtime-hotspot-smoke")
        expected_tests = pack_selectors(registry, "runtime_hotspot_smoke")

        self.assertIn("runtime-hotspot-smoke", _target_block(text, ".PHONY"))
        self.assertIn("RUNTIME_HOTSPOT_SMOKE_TESTS ?=", text)
        self.assertIn("`make runtime-hotspot-smoke`", development_text)
        for test_path in expected_tests:
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, text)
        self.assertIn(
            "$(PYTHON) -m pytest -q $(RUNTIME_HOTSPOT_SMOKE_TESTS) "
            "$(PYTEST_CACHE_ISOLATION_FLAGS) $(PYTEST_SERIAL_FLAGS)",
            block,
        )
        self.assertNotIn("test-report-contract", block)
        self.assertNotIn("test-fast", block)

    def test_default_test_boundary_is_chained_into_make_test(self) -> None:
        registry = load_registry(REPO_ROOT)
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "test-boundary-contract-smoke")
        expected_tests = pack_selectors(registry, "default_test_boundary")

        self.assertIn("test-boundary-contract-smoke", _target_block(text, ".PHONY"))
        self.assertIn("test: test-fast test-boundary-contract-smoke", text)
        self.assertIn("DEFAULT_TEST_BOUNDARY_TESTS ?=", text)
        self.assertIn(
            "`make test` chains the fast unit lane with `make test-boundary-contract-smoke`",
            development_text,
        )
        for test_path in expected_tests:
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, text)
        self.assertIn(
            "$(PYTHON) -m pytest $(DEFAULT_TEST_BOUNDARY_TESTS) $(PYTEST_SERIAL_FLAGS)",
            block,
        )

    def test_fast_smoke_selectors_collect_via_supported_pytest_entrypoint(self) -> None:
        text = _makefile_text()
        selectors = _makefile_assignment_items(text, "FAST_SMOKE_TESTS")
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                *selectors,
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "FAST_SMOKE_TESTS contains an uncollectable pytest selector.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
