from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest

from ops.scripts.test.test_lane_registry_runtime import (
    load_registry,
    pack_summary_suite,
)
from tests.makefile_static_helpers import (
    _assert_assignment_exists,
    _assert_assignment_not_exists,
    _assert_recipe_contains_tokens,
    _makefile_text,
    _target_block,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]

REPO_ROOT = Path(__file__).resolve().parents[1]


TEST_EXECUTION_SUMMARY_PHONY_TARGETS = (
    "test-execution-summary-fast",
    "test-execution-summary-report-contract",
    "test-execution-summary-full",
)

COMPATIBILITY_TEST_EXECUTION_SUMMARY_TARGETS = {
    "test-execution-summary": "test-execution-summary-report-contract",
    "test-execution-summary-report-contract-refresh": (
        "test-execution-summary-report-contract "
        "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=bootstrap-refresh"
    ),
    "test-execution-summary-report-contract-refresh-no-smoke": (
        "test-execution-summary-report-contract "
        "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=bootstrap-refresh-no-smoke"
    ),
    "test-execution-summary-current-check": (
        "test-execution-summary-report-contract "
        "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=current-check"
    ),
    "test-execution-summary-current-or-refresh": (
        "test-execution-summary-report-contract "
        "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=current-or-refresh"
    ),
    "test-execution-summary-revision-rebind": (
        "test-execution-summary-report-contract "
        "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=revision-rebind"
    ),
    "test-execution-summary-full-body": (
        "test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=body"
    ),
    "test-execution-summary-full-refresh": (
        "test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=refresh"
    ),
    "test-execution-summary-full-refresh-no-converge": (
        "test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=refresh-no-converge"
    ),
    "test-execution-summary-full-revision-rebind": (
        "test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=revision-rebind"
    ),
    "test-execution-summary-full-current-check": (
        "test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=current-check"
    ),
    "test-execution-summary-full-current-or-refresh": (
        "test-execution-summary-full TEST_EXECUTION_SUMMARY_FULL_MODE=current-or-refresh"
    ),
}

REMOVED_TEST_EXECUTION_SUMMARY_TARGETS = ("test-execution-summary-public",)

TEST_EXECUTION_SUMMARY_ASSIGNMENTS = (
    ("TEST_EXECUTION_SUMMARY_OUT", "ops/reports/test-execution-summary.json"),
    ("TEST_EXECUTION_SUMMARY_CANDIDATE_OUT", "tmp/test-execution-summary.candidate.json"),
    ("TEST_EXECUTION_SUMMARY_CHECK_OUT", "tmp/test-execution-summary-check.json"),
    ("TEST_EXECUTION_SUMMARY_FAST_OUT", "ops/reports/test-execution-summary-fast.json"),
    (
        "TEST_EXECUTION_SUMMARY_FAST_CANDIDATE_OUT",
        "tmp/test-execution-summary-fast.candidate.json",
    ),
    ("TEST_EXECUTION_SUMMARY_FULL_OUT", "ops/reports/test-execution-summary-full.json"),
    (
        "TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT",
        "tmp/test-execution-summary-full.candidate.json",
    ),
    ("TEST_EXECUTION_SUMMARY_FULL_CHECK_OUT", "tmp/test-execution-summary-full-check.json"),
    ("TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE", "run"),
    ("TEST_EXECUTION_SUMMARY_FULL_MODE", "run"),
    ("RELEASE_AUDIT_PAYLOAD_STAGING_DIR", "build/release-payloads"),
    (
        "TEST_EXECUTION_SUMMARY_FULL_JUNIT_OUT",
        "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.junit.xml",
    ),
    (
        "TEST_EXECUTION_SUMMARY_FULL_LOG_OUT",
        "$(RELEASE_AUDIT_PAYLOAD_STAGING_DIR)/test-execution-summary-full.log",
    ),
    ("TEST_EXECUTION_SUMMARY_REUSE_FROM", "$(TEST_EXECUTION_SUMMARY_OUT)"),
    ("TEST_EXECUTION_SUMMARY_FULL_REUSE_FROM", "$(TEST_EXECUTION_SUMMARY_FULL_OUT)"),
    ("TEST_EXECUTION_SUMMARY_FULL_PYTEST_FLAGS", "$(PYTEST_FLAGS)"),
    (
        "TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR",
        "ops/reports/test-execution-summary-full-shards",
    ),
    ("TEST_EXECUTION_SUMMARY_FULL_HEARTBEAT_INTERVAL_SECONDS", "30"),
)

TEST_EXECUTION_SUMMARY_ABSENT_ASSIGNMENTS = (
    "TEST_EXECUTION_SUMMARY_PUBLIC_OUT",
    "TEST_EXECUTION_SUMMARY_PUBLIC_CANDIDATE_OUT",
    "TEST_EXECUTION_SUMMARY_PUBLIC_SUITE",
    "TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT",
    "TEST_EXECUTION_SUMMARY_SHARD_DIR",
)


def _test_lane_registry() -> dict[str, object]:
    return load_registry(REPO_ROOT)


def _assert_phony_targets(testcase: unittest.TestCase, text: str) -> None:
    phony = _target_block(text, ".PHONY")
    for target in TEST_EXECUTION_SUMMARY_PHONY_TARGETS:
        testcase.assertRegex(
            phony,
            rf"(?<![A-Za-z0-9_.-]){re.escape(target)}(?![A-Za-z0-9_.-])",
        )
    for target in COMPATIBILITY_TEST_EXECUTION_SUMMARY_TARGETS:
        testcase.assertRegex(
            phony,
            rf"(?<![A-Za-z0-9_.-]){re.escape(target)}(?![A-Za-z0-9_.-])",
        )
    for target in REMOVED_TEST_EXECUTION_SUMMARY_TARGETS:
        testcase.assertNotRegex(
            phony,
            rf"(?<![A-Za-z0-9_.-]){re.escape(target)}(?![A-Za-z0-9_.-])",
        )


def _assert_assignments(testcase: unittest.TestCase, text: str) -> None:
    for name, value in TEST_EXECUTION_SUMMARY_ASSIGNMENTS:
        _assert_assignment_exists(testcase, text, name, value)
    for name in TEST_EXECUTION_SUMMARY_ABSENT_ASSIGNMENTS:
        _assert_assignment_not_exists(testcase, text, name)


def _mode_block(text: str, variable: str, mode: str) -> str:
    first_marker = f"ifeq ($({variable}),{mode})"
    later_marker = f"else ifeq ($({variable}),{mode})"
    marker = first_marker if first_marker in text else later_marker
    if marker not in text:
        raise AssertionError(f"missing mode branch: {variable}={mode}")
    start = text.index(marker)
    next_positions = [
        position
        for position in (
            text.find(f"\nelse ifeq ($({variable}),", start + 1),
            text.find("\nelse\n", start + 1),
            text.find("\nendif", start + 1),
        )
        if position != -1
    ]
    end = min(next_positions) if next_positions else len(text)
    return text[start:end]


class MakefileTestExecutionSummaryGateTests(unittest.TestCase):
    def test_test_execution_summary_declares_three_developer_facing_targets(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        _assert_phony_targets(self, text)
        _assert_assignments(self, text)
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_FAST_SUITE",
            pack_summary_suite(registry, "fast")["suite_id"],
        )
        _assert_assignment_exists(
            self,
            text,
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_SUITE",
            pack_summary_suite(registry, "report_contract_core")["suite_id"],
        )
        _assert_assignment_exists(self, text, "TEST_EXECUTION_SUMMARY_FULL_SUITE", "full")
        _assert_assignment_exists(
            self, text, "TEST_EXECUTION_SUMMARY_FULL_SHARD_SUITE", "full-shard-1"
        )

    def test_fast_public_and_report_contract_summary_recipes(self) -> None:
        text = _makefile_text()

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
        public_block = _target_block(text, "test-public")
        self.assertIn('$(PYTHON) -m pytest -m "$(PYTEST_PUBLIC_MARK_EXPR)"', public_block)
        self.assertNotIn("test-execution-summary-public", public_block)
        self.assertIn('$(PYTEST_SERIAL_FLAGS)', _target_block(text, "test-public-serial"))

        run_block = _mode_block(text, "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE", "run")
        _assert_recipe_contains_tokens(
            self,
            run_block,
            "test-execution-summary-report-contract",
            (
                "ops.scripts.test_execution_summary",
                "--collect-nodeids",
                '--deselection-policy "$(REPORT_CONTRACT_SUMMARY_DESELECT_POLICY)"',
                "$(REPORT_CONTRACT_SUMMARY_TESTS)",
                "ops.scripts.canonical_artifact_promote",
            ),
        )
    def test_report_contract_modes_separate_revision_rebind_from_test_execution(self) -> None:
        text = _makefile_text()

        refresh_block = _mode_block(
            text, "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE", "bootstrap-refresh"
        )
        self.assertIn("$(MAKE) auto-improve-readiness-report", refresh_block)
        self.assertIn("$(MAKE) release-smoke-full-reuse", refresh_block)
        self.assertEqual(refresh_block.count("$(MAKE) generated-artifact-converge"), 2)
        self.assertIn("bootstrap refresh promoted a non-pass summary", refresh_block)

        no_smoke_block = _mode_block(
            text,
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE",
            "bootstrap-refresh-no-smoke",
        )
        self.assertIn("$(MAKE) auto-improve-readiness-report", no_smoke_block)
        self.assertNotIn("$(MAKE) release-smoke-full-reuse", no_smoke_block)
        self.assertEqual(no_smoke_block.count("$(MAKE) generated-artifact-converge"), 2)

        current_or_refresh_block = _mode_block(
            text, "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE", "current-or-refresh"
        )
        self.assertIn(
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=current-check",
            current_or_refresh_block,
        )
        self.assertIn(
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=revision-rebind",
            current_or_refresh_block,
        )
        self.assertIn(
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE=run",
            current_or_refresh_block,
        )
        rebind_block = _mode_block(
            text,
            "TEST_EXECUTION_SUMMARY_REPORT_CONTRACT_MODE",
            "revision-rebind",
        )
        self.assertIn("--reuse-if-current", rebind_block)
        self.assertIn("--reuse-only", rebind_block)
        self.assertIn("--refresh-revision-if-same-tree", rebind_block)
        self.assertIn("--binding-mode revision", rebind_block)
        self.assertIn('rm -f "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)"', rebind_block)
        self.assertIn(
            'test -f "$(TEST_EXECUTION_SUMMARY_CANDIDATE_OUT)"',
            rebind_block,
        )

    def test_full_summary_modes_preserve_body_refresh_and_reuse_paths(self) -> None:
        text = _makefile_text()

        run_block = _mode_block(text, "TEST_EXECUTION_SUMMARY_FULL_MODE", "run")
        self.assertIn("TEST_EXECUTION_SUMMARY_FULL_MODE=body", run_block)
        self.assertIn("$(MAKE) generated-artifact-converge", run_block)

        body_block = _mode_block(text, "TEST_EXECUTION_SUMMARY_FULL_MODE", "body")
        _assert_recipe_contains_tokens(
            self,
            body_block,
            "test-execution-summary-full",
            (
                "$(MAKE) full-pytest-generated-preflight",
                'rm -rf "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                'mkdir -p "$(TEST_EXECUTION_SUMMARY_FULL_SHARD_DIR)"',
                "test-execution-summary-full: suite=$(TEST_EXECUTION_SUMMARY_FULL_SUITE) shard=full-suite-shard-1",
                "heartbeat_interval_seconds=$(TEST_EXECUTION_SUMMARY_FULL_HEARTBEAT_INTERVAL_SECONDS)",
                "log=$(TEST_EXECUTION_SUMMARY_FULL_LOG_OUT)",
                '--heartbeat-interval-seconds "$(TEST_EXECUTION_SUMMARY_FULL_HEARTBEAT_INTERVAL_SECONDS)"',
                '--heartbeat-label "full-suite-shard-1"',
                "--junit-xml-path",
                "--execution-log-out",
                "--failed-nodeids-out",
                "--aggregate",
                "--aggregate-dir",
                "ops.scripts.canonical_artifact_promote",
            ),
        )
        self.assertNotIn("$(MAKE) generated-artifact-converge", body_block)

        refresh_no_converge_block = _mode_block(
            text, "TEST_EXECUTION_SUMMARY_FULL_MODE", "refresh-no-converge"
        )
        self.assertIn("TEST_EXECUTION_SUMMARY_FULL_MODE=body", refresh_no_converge_block)
        self.assertNotIn("$(MAKE) generated-artifact-converge", refresh_no_converge_block)

        current_or_refresh_block = _mode_block(
            text, "TEST_EXECUTION_SUMMARY_FULL_MODE", "current-or-refresh"
        )
        self.assertIn("TEST_EXECUTION_SUMMARY_FULL_MODE=current-check", current_or_refresh_block)
        self.assertIn("TEST_EXECUTION_SUMMARY_FULL_MODE=revision-rebind", current_or_refresh_block)
        self.assertIn("TEST_EXECUTION_SUMMARY_FULL_MODE=refresh-no-converge", current_or_refresh_block)
        rebind_block = _mode_block(text, "TEST_EXECUTION_SUMMARY_FULL_MODE", "revision-rebind")
        self.assertIn("--reuse-only", rebind_block)
        self.assertIn("--refresh-revision-if-same-tree", rebind_block)
        self.assertIn("--binding-mode revision", rebind_block)
        self.assertIn('rm -f "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)"', rebind_block)
        self.assertIn(
            'test -f "$(TEST_EXECUTION_SUMMARY_FULL_CANDIDATE_OUT)"',
            rebind_block,
        )

    def test_compatibility_summary_targets_delegate_to_mode_targets(self) -> None:
        text = _makefile_text()

        for target, expected in COMPATIBILITY_TEST_EXECUTION_SUMMARY_TARGETS.items():
            with self.subTest(target=target):
                block = _target_block(text, target)
                if target == "test-execution-summary":
                    self.assertEqual(
                        block.splitlines()[0],
                        "test-execution-summary: test-execution-summary-report-contract",
                    )
                    continue
                self.assertIn(f"$(MAKE) {expected}", block)
                if target.endswith("revision-rebind"):
                    self.assertIn("no tests were run", block)
                    self.assertIn("release-source-ready-prepare", block)

    def test_report_contract_closeout_uses_generated_artifact_orchestrator(self) -> None:
        text = _makefile_text()
        closeout_block = _target_block(text, "report-contract-closeout")
        orchestrator_block = _target_block(text, "report-contract-closeout-generated-artifacts")

        self.assertIn("$(MAKE) report-contract-closeout-generated-artifacts", closeout_block)
        self.assertNotIn("$(MAKE) generated-artifact-converge", closeout_block)
        self.assertIn("$(MAKE) release-closeout-summary-report", orchestrator_block)
        self.assertIn("$(MAKE) release-evidence-cohort", orchestrator_block)
        self.assertIn("$(MAKE) auto-improve-readiness-report-body", orchestrator_block)
        self.assertEqual(orchestrator_block.count("$(MAKE) generated-artifact-converge"), 2)
