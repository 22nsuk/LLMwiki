from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

from ops.scripts.test.test_lane_registry_runtime import (
    load_registry,
    pack_mark_expr,
)
from tests.makefile_static_helpers import (
    _makefile_text,
    _pytest_collect_nodeid_path_counts,
    _target_block,
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


def _collect_marker_path_counts(mark_expr: str, *, failure_label: str) -> dict[str, int]:
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
            "-m",
            mark_expr,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if completed.returncode != 0:
        raise AssertionError(
            f"{failure_label} contains an uncollectable pytest marker.\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )

    return _pytest_collect_nodeid_path_counts(completed.stdout)


def _assert_collected_paths_self_declare_marker(
    case: unittest.TestCase,
    collected_by_path: dict[str, int],
    marker: str,
) -> None:
    for path in collected_by_path:
        with case.subTest(path=path, marker=marker):
            case.assertIn(marker, (REPO_ROOT / path).read_text(encoding="utf-8"))


class MakefileFastSmokeStaticGateTests(unittest.TestCase):
    def test_fast_smoke_is_curated_developer_feedback_loop(self) -> None:
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "fast-smoke")

        self.assertIn("fast-smoke", _target_block(text, ".PHONY"))
        self.assertIn(
            "`make fast-smoke` is the curated Subagent/developer precheck pytest slice.",
            development_text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(FAST_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)",
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
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "runtime-hotspot-smoke")

        self.assertIn("runtime-hotspot-smoke", _target_block(text, ".PHONY"))
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
        self.assertTrue(collected_by_path)
        self.assertTrue(
            all(
                path.startswith("tests/") and path.endswith(".py")
                for path in collected_by_path
            )
        )
        _assert_collected_paths_self_declare_marker(
            self,
            collected_by_path,
            "runtime_hotspot_smoke",
        )

    def test_default_test_boundary_is_chained_into_make_test(self) -> None:
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "test-boundary-contract-smoke")

        self.assertIn("test-boundary-contract-smoke", _target_block(text, ".PHONY"))
        self.assertIn("test: test-fast test-boundary-contract-smoke", text)
        self.assertIn(
            "`make test` chains the fast unit lane with `make test-boundary-contract-smoke`",
            development_text,
        )
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
        self.assertTrue(collected_by_path)
        self.assertTrue(
            all(
                path.startswith("tests/") and path.endswith(".py")
                for path in collected_by_path
            )
        )
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
        self.assertTrue(collected_by_path)
        self.assertTrue(
            all(
                path.startswith("tests/") and path.endswith(".py")
                for path in collected_by_path
            )
        )
        _assert_collected_paths_self_declare_marker(
            self,
            collected_by_path,
            "fast_smoke",
        )
