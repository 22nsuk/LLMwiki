from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest
from ops.scripts.test_lane_registry_runtime import load_registry, pack_summary_suite

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

MAKEFILE = Path("Makefile")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _test_lane_registry() -> dict[str, object]:
    return load_registry(REPO_ROOT)


def _makefile_text() -> str:
    text = MAKEFILE.read_text(encoding="utf-8")
    for mk_file in sorted(REPO_ROOT.glob("mk/*.mk")):
        text += "\n" + mk_file.read_text(encoding="utf-8")
    return text


def _target_block(text: str, target: str) -> str:
    if target == ".PHONY":
        matches = list(
            re.finditer(
                rf"^{re.escape(target)}:(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
                text,
                flags=re.MULTILINE,
            )
        )
        if not matches:
            raise AssertionError(f"missing Makefile target: {target}")
        return "\n".join(m.group(0) for m in matches)
    match = re.search(
        rf"^{re.escape(target)}:(?P<deps>[^\n]*)(?P<body>(?:\n\t[^\n]*)*)",
        text,
        flags=re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing Makefile target: {target}")
    return match.group(0)


def _target_dependencies(text: str, target: str) -> tuple[str, ...]:
    header = _target_block(text, target).splitlines()[0]
    _, _, raw_deps = header.partition(":")
    return tuple(raw_deps.split())


def _assert_target_depends_on(
    case: unittest.TestCase, text: str, target: str, dependency: str
) -> None:
    case.assertIn(dependency, _target_dependencies(text, target))


def _makefile_assignment_value(text: str, variable: str) -> str:
    prefix = f"{variable} ?="
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    raise AssertionError(f"missing Makefile assignment: {variable}")


def _assert_assignment_exists(
    case: unittest.TestCase,
    text: str,
    variable: str,
    expected_value: str | None = None,
) -> str:
    value = _makefile_assignment_value(text, variable)
    if expected_value is not None:
        case.assertEqual(value, expected_value)
    return value


def _assert_assignment_not_exists(
    case: unittest.TestCase, text: str, variable: str
) -> None:
    with case.assertRaises(AssertionError):
        _makefile_assignment_value(text, variable)


def _assert_recipe_contains_tokens(
    case: unittest.TestCase,
    text: str,
    target: str,
    required_tokens: tuple[str, ...],
) -> None:
    block = _target_block(text, target)
    missing = [token for token in required_tokens if token not in block]
    case.assertEqual(missing, [], f"{target} recipe missing required tokens")


class MakefileTestExecutionSummaryGateTests(unittest.TestCase):
    def test_test_execution_summary_target_wraps_report_contracts(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        for target in (
            "test-execution-summary",
            "test-execution-summary-fast",
            "test-execution-summary-public",
            "test-execution-summary-report-contract",
            "test-execution-summary-report-contract-refresh",
            "test-execution-summary-report-contract-refresh-no-smoke",
            "test-execution-summary-current-check",
            "test-execution-summary-current-or-refresh",
            "test-execution-summary-full-body",
            "test-execution-summary-full",
            "test-execution-summary-full-refresh",
            "test-execution-summary-full-refresh-no-converge",
            "test-execution-summary-full-aggregate-reuse",
            "test-execution-summary-full-current-check",
            "test-execution-summary-full-current-or-refresh",
            "test-execution-summary-reuse",
        ):
            self.assertIn(target, _target_block(text, ".PHONY"))
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_OUT",
            "ops/reports/test-execution-summary.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_CANDIDATE_OUT",
            "tmp/test-execution-summary.candidate.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_CHECK_OUT",
            "tmp/test-execution-summary-check.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FAST_OUT",
            "ops/reports/test-execution-summary-fast.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT",
            "tmp/test-execution-summary-fast.candidate.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_PUBLIC_OUT",
            "ops/reports/test-execution-summary-public.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_PUBLIC_CANDIDATE_OUT",
            "tmp/test-execution-summary-public.candidate.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_OUT",
            "ops/reports/test-execution-summary-full.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT",
            "tmp/test-execution-summary-full.candidate.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT",
            "tmp/test-execution-summary-full-check.json",
        )
        _assert_assignment_not_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT"
        )
        _assert_assignment_exists(
            self, text, "RELEASE_AUDIT_PAYLOAD_STAGING_DIR", "build/release-payloads"
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT",
            "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.junit.xml",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_LOG_OUT",
            "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.log",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_REUSE_FROM",
            "$(TEST_EXECUTION_SUMMARY_OUT)",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM",
            "$(TEST_EXECUTION_SUMMARY_FULL_OUT)",
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FULL_PYTEST_FLAGS", "$(PYTEST_FLAGS)"
        )
        _assert_assignment_not_exists(self, text, "TEST_EXECUTION_SUMMARY_SHARD_DIR")
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR",
            "ops/reports/test-execution-summary-full-shards",
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FAST_SUITE",
            pack_summary_suite(registry, "fast")["suite_id"],
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_PUBLIC_SUITE", "public"
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE",
            pack_summary_suite(registry, "report_contract_core")["suite_id"],
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FULL_SUITE", "full"
        )
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FULL_SHARD_SUITE", "full-shard-1"
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-fast",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                '$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-public",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                '$(PYTHON) -m pytest -m "$(PYTEST_PUBLIC_MARK_EXPR)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        _assert_target_depends_on(
            self, text, "test-public", "test-execution-summary-public"
        )
        self.assertIn(
            '$(MAKE) test-execution-summary-public PYTEST_FLAGS="$(PYTEST_SERIAL_FLAGS)"',
            _target_block(text, "test-public-serial"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-report-contract",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                '--deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)"',
                "$(REPORT_CONTRACT_SUMMARY_TESTS)",
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        refresh_block = _target_block(
            text, "test-execution-summary-report-contract-refresh"
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-report-contract-refresh",
            (
                "ops.scripts.test_execution_summary",
                "ops.scripts.canonical_artifact_promote",
                "$(MAKE) auto-improve-readiness-report",
                "$(MAKE) release-smoke-full-reuse",
                "$(MAKE) generated-artifact-converge",
            ),
        )
        self.assertNotIn("$(MAKE) release-smoke-full\n", refresh_block)
        self.assertEqual(refresh_block.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertEqual(
            refresh_block.count("$(MAKE) archive-execution-manifest-report"), 0
        )
        self.assertNotIn("$(MAKE) artifact-freshness", refresh_block)
        self.assertNotIn("$(MAKE) generated-artifact-index", refresh_block)
        self.assertIn(
            "strict test-execution-summary will rerun later in closeout", refresh_block
        )
        no_smoke_refresh_block = _target_block(
            text, "test-execution-summary-report-contract-refresh-no-smoke"
        )
        self.assertIn("$(MAKE) auto-improve-readiness-report", no_smoke_refresh_block)
        self.assertEqual(
            no_smoke_refresh_block.count("$(MAKE) generated-artifact-converge"), 2
        )
        self.assertNotIn("$(MAKE) release-smoke-full-reuse", no_smoke_refresh_block)
        self.assertNotIn("$(MAKE) generated-artifact-index", no_smoke_refresh_block)
        self.assertNotIn("$(MAKE) artifact-freshness", no_smoke_refresh_block)
        self.assertIn(
            "test-execution-summary-report-contract-refresh-no-smoke promoted a non-pass bootstrap summary",
            no_smoke_refresh_block,
        )
        self.assertIn(
            "test-execution-summary: test-execution-summary-report-contract", text
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-current-check",
            (
                "ops.scripts.test_execution_summary",
                '--out "$(TEST_EXECUTION_SUMMARY_CHECK_OUT)"',
                "--collect-nodeids",
                "--reuse-if-current",
                "--reuse-only",
                '--reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)"',
                '--deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)"',
            ),
        )
        current_or_refresh_block = _target_block(
            text, "test-execution-summary-current-or-refresh"
        )
        self.assertIn(
            "$(MAKE) test-execution-summary-current-check",
            current_or_refresh_block,
        )
        self.assertIn(
            "$(MAKE) test-execution-summary-reuse",
            current_or_refresh_block,
        )
        self.assertIn(
            "test execution summary is current; reused $(TEST_EXECUTION_SUMMARY_REUSE_FROM)",
            current_or_refresh_block,
        )
        runtime_hotspot_block = _target_block(text, "runtime-hotspot-goldens-check")
        self.assertIn("runtime-hotspot-goldens-check", _target_block(text, ".PHONY"))
        self.assertIn(
            "tests/test_runtime_hotspot_facade_golden_outputs.py",
            runtime_hotspot_block,
        )
        self.assertIn("$(PYTEST_CACHE_ISOLATION_FLAGS)", runtime_hotspot_block)
        self.assertIn("$(PYTEST_SERIAL_FLAGS)", runtime_hotspot_block)
        generated_preflight_block = _target_block(text, "full-pytest-generated-preflight")
        self.assertIn("full-pytest-generated-preflight", _target_block(text, ".PHONY"))
        _assert_recipe_contains_tokens(
            self,
            text,
            "full-pytest-generated-preflight",
            (
                "$(MAKE) report-schema-samples-check",
                "$(MAKE) script-output-surfaces-check",
                "$(MAKE) runtime-hotspot-goldens-check",
            ),
        )
        self.assertNotIn(
            "ops.scripts.canonical_artifact_promote", generated_preflight_block
        )
        full_body_block = _target_block(text, "test-execution-summary-full-body")
        self.assertNotIn("$(MAKE) refresh-generated-core", full_body_block)
        self.assertNotIn("$(MAKE) auto-improve-readiness-report-body", full_body_block)
        self.assertNotIn("$(MAKE) release-smoke-full", full_body_block)
        self.assertIn("$(TEST_EXECUTION_SUMMARY_FULL_PYTEST_FLAGS)", full_body_block)
        self.assertNotIn("$(PYTEST_SERIAL_FLAGS)", full_body_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-full-body",
            (
                "$(MAKE) full-pytest-generated-preflight",
                'rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                'mkdir -p "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                '"$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)"',
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                "--junit-xml-path",
                "--execution-log-out",
                "--failed-nodeids-out",
                "--aggregate",
                "--aggregate-dir",
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        self.assertLess(
            full_body_block.index("$(MAKE) full-pytest-generated-preflight"),
            full_body_block.index('rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"'),
        )
        self.assertNotIn("$(MAKE) generated-artifact-converge", full_body_block)
        self.assertNotIn(
            "$(MAKE) test-execution-summary-report-contract-refresh", full_body_block
        )
        full_block = _target_block(text, "test-execution-summary-full")
        _assert_target_depends_on(
            self, text, "test-execution-summary-full", "test-execution-summary-full-body"
        )
        self.assertEqual(full_block.count("$(MAKE) generated-artifact-converge"), 1)
        self.assertNotIn("$(PYTHON) -m pytest", full_block)
        self.assertGreater(
            full_block.rindex("$(MAKE) generated-artifact-converge"),
            full_block.index("test-execution-summary-full-body"),
        )
        full_refresh_block = _target_block(text, "test-execution-summary-full-refresh")
        _assert_target_depends_on(
            self,
            text,
            "test-execution-summary-full-refresh",
            "test-execution-summary-full",
        )
        self.assertIn(
            "full-suite evidence refreshed; collect-only nodeid digest and count recorded in $(TEST_EXECUTION_SUMMARY_FULL_OUT)",
            full_refresh_block,
        )
        self.assertNotIn("node count $$actual does not match expected", full_refresh_block)
        no_converge_full_refresh_block = _target_block(
            text, "test-execution-summary-full-refresh-no-converge"
        )
        _assert_target_depends_on(
            self,
            text,
            "test-execution-summary-full-refresh-no-converge",
            "test-execution-summary-full-body",
        )
        self.assertNotIn(
            "$(MAKE) generated-artifact-converge", no_converge_full_refresh_block
        )
        self.assertIn(
            "full-suite evidence refreshed without generated artifact convergence",
            no_converge_full_refresh_block,
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-full-aggregate-reuse",
            (
                "ops.scripts.test_execution_summary",
                "--aggregate",
                "--aggregate-dir",
                "--reuse-if-current",
                "--refresh-revision-if-same-tree",
                '--reuse-from "$(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-full-current-check",
            (
                "ops.scripts.test_execution_summary",
                '--out "$(TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT)"',
                "--aggregate",
                "--reuse-if-current",
                "--reuse-only",
                '--reuse-from "$(TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM)"',
            ),
        )
        full_current_or_refresh_block = _target_block(
            text, "test-execution-summary-full-current-or-refresh"
        )
        self.assertIn(
            "$(MAKE) test-execution-summary-full-current-check",
            full_current_or_refresh_block,
        )
        self.assertIn(
            "$(MAKE) test-execution-summary-full-aggregate-reuse",
            full_current_or_refresh_block,
        )
        self.assertIn(
            "$(MAKE) test-execution-summary-full-refresh-no-converge",
            full_current_or_refresh_block,
        )
        self.assertIn("full-suite evidence is current", full_current_or_refresh_block)
        _assert_recipe_contains_tokens(
            self,
            text,
            "test-execution-summary-reuse",
            (
                "ops.scripts.test_execution_summary",
                "--reuse-if-current",
                "--refresh-revision-if-same-tree",
                '--reuse-from "$(TEST_EXECUTION_SUMMARY_REUSE_FROM)"',
                '--deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)"',
                "ops.scripts.canonical_artifact_promote",
            ),
        )
