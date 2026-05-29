from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from ops.scripts.command_runtime import TimedProcessResult
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import TEST_EXECUTION_SUMMARY_SCHEMA_PATH
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.test_execution_summary import (
    build_aggregate_report,
    build_report,
    build_reused_report,
    classify_interpreter_path,
    classify_status,
    collect_pytest_nodeid_digest,
    parse_pytest_counts,
    resolve_pytest_target_paths,
    reusable_summary_is_current,
    semantic_command,
)
from ops.scripts.test_execution_summary import (
    main as summary_main,
)

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.report_contract


def _result(
    *,
    returncode: int,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    termination_reason: str = "completed",
) -> TimedProcessResult:
    return TimedProcessResult(
        args=["python", "-m", "pytest"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        timeout_seconds=30,
        termination_reason=termination_reason,
    )


def _fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 29, 0, 0, tzinfo=dt.UTC),
    )


class TestExecutionSummaryTest(unittest.TestCase):
    def test_parse_pytest_counts_reads_terminal_summary(self) -> None:
        counts = parse_pytest_counts("= 4 failed, 12 passed, 2 skipped, 1 warning in 0.50s =")

        self.assertEqual(counts["passed"], 12)
        self.assertEqual(counts["failed"], 4)
        self.assertEqual(counts["skipped"], 2)
        self.assertEqual(counts["warnings"], 1)

    def test_classify_status_distinguishes_release_relevant_outcomes(self) -> None:
        self.assertEqual(classify_status(_result(returncode=0), parse_pytest_counts("2 passed")), "pass")
        self.assertEqual(
            classify_status(_result(returncode=1), parse_pytest_counts("1 failed")),
            "fail",
        )
        self.assertEqual(
            classify_status(_result(returncode=1), parse_pytest_counts("1 failed, 3 passed")),
            "partial-pass",
        )
        self.assertEqual(
            classify_status(_result(returncode=1, timed_out=True), parse_pytest_counts("3 passed")),
            "timeout",
        )
        self.assertEqual(
            classify_status(_result(returncode=130), parse_pytest_counts("")),
            "interrupted",
        )

    def test_build_report_validates_schema_and_preserves_partial_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            test_file = vault / "tests" / "test_sample.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(
                "def test_ok():\n    assert True\n",
                encoding="utf-8",
            )

            report = build_report(
                vault,
                command=["python", "-m", "pytest", "tests/test_sample.py::test_ok"],
                result=_result(returncode=1, stdout="= 1 failed, 2 passed in 1.00s ="),
                duration_ms=1234,
                suite="unit",
                context=_fixed_context(),
            )
            schema = load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["artifact_kind"], "test_execution_summary")
            self.assertEqual(report["$schema"], TEST_EXECUTION_SUMMARY_SCHEMA_PATH)
            self.assertEqual(report["generated_at"], "2026-04-29T00:00:00Z")
            self.assertEqual(report["suite_scope"], "fast_unit")
            self.assertFalse(report["represents_full_suite"])
            self.assertIn("pytest selectors", report["not_full_suite_reason"])
            self.assertEqual(report["full_suite_evidence"]["status"], "not_represented")
            self.assertEqual(report["full_suite_evidence"]["release_builder_environment"], ".venv clean release-builder")
            self.assertEqual(report["status"], "partial-pass")
            self.assertEqual(report["counts"]["passed"], 2)
            self.assertEqual(report["counts"]["failed"], 1)
            self.assertRegex(report["execution_environment"]["python_version"], r"^\d+\.\d+\.\d+")
            self.assertRegex(report["execution_environment"]["pytest_version"], r"^(unavailable|\d+\.\d+)")
            self.assertEqual(
                report["execution_environment"]["plugin_autoload_policy"]["env_var"],
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            )
            self.assertIn(
                report["execution_environment"]["interpreter_path_class"],
                {"path_lookup", "external_absolute"},
            )
            self.assertEqual(report["execution_environment"]["toolchain_contract"]["status"], "pass")
            self.assertEqual(
                report["execution_environment"]["toolchain_contract"]["release_evidence_effect"],
                "eligible",
            )
            self.assertEqual(
                report["test_target_fingerprints"],
                [
                    {
                        "path": "tests/test_sample.py",
                        "sha256": hashlib.sha256(test_file.read_bytes()).hexdigest(),
                    }
                ],
            )
            self.assertIn("test_targets", report["input_fingerprints"])
            self.assertEqual(report["deselected_tests"], [])
            self.assertEqual(report["pytest_collect_nodeid_digest"]["status"], "skipped")
            self.assertEqual(report["nodeid_outcome_consistency"]["status"], "skipped")
            self.assertEqual(report["evidence_artifacts"], [])

    def test_build_report_marks_selector_free_pytest_as_full_suite_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = build_report(
                vault,
                command=["python", "-m", "pytest"],
                result=_result(returncode=0, stdout="= 7 passed in 1.00s ="),
                duration_ms=1234,
                suite="pytest",
                context=_fixed_context(),
            )

            self.assertEqual(report["suite_scope"], "full_suite")
            self.assertTrue(report["represents_full_suite"])
            self.assertEqual(report["not_full_suite_reason"], "")
            self.assertEqual(report["full_suite_evidence"]["status"], "represented")
            self.assertEqual(report["full_suite_evidence"]["required_command"], "python -m pytest")
            self.assertEqual(
                validate_with_schema(report, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_build_report_does_not_treat_selector_limited_full_suite_as_full_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = build_report(
                vault,
                command=["python", "-m", "pytest", "-m", "not slow"],
                result=_result(returncode=0, stdout="= 7 passed, 3 deselected in 1.00s ="),
                duration_ms=1234,
                suite="full",
                context=_fixed_context(),
            )

            self.assertEqual(report["suite_scope"], "full_suite")
            self.assertFalse(report["represents_full_suite"])
            self.assertEqual(report["full_suite_evidence"]["status"], "not_represented")
            self.assertEqual(
                report["not_full_suite_reason"],
                "pytest selectors limit this execution to a targeted suite subset",
            )
            self.assertEqual(
                validate_with_schema(report, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_unsupported_toolchain_blocks_full_suite_evidence_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            with patch("ops.scripts.test_execution_summary.platform.python_version", return_value="3.10.99"):
                report = build_report(
                    vault,
                    command=["python", "-m", "pytest"],
                    result=_result(returncode=0, stdout="= 7 passed in 1.00s ="),
                    duration_ms=1234,
                    suite="pytest",
                    context=_fixed_context(),
                )

            self.assertFalse(report["represents_full_suite"])
            self.assertEqual(report["full_suite_evidence"]["status"], "not_represented")
            self.assertEqual(
                report["execution_environment"]["toolchain_contract"]["release_evidence_effect"],
                "blocked_unsupported_toolchain",
            )
            self.assertIn("unsupported toolchain", report["not_full_suite_reason"])
            self.assertEqual(
                validate_with_schema(report, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_reused_report_validates_schema_and_preserves_existing_pass_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            test_file = vault / "tests" / "test_sample.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            command = ["python", "-m", "pytest", "tests/test_sample.py"]
            existing = build_report(
                vault,
                command=command,
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="unit",
                context=_fixed_context(),
            )

            self.assertTrue(
                reusable_summary_is_current(
                    existing,
                    vault=vault,
                    command=command,
                    suite="unit",
                    collect_nodeids=False,
                    collect_nodeid_digest=None,
                )
            )

            reused = build_reused_report(
                vault,
                existing=existing,
                command=command,
                suite="unit",
                context=RuntimeContext(
                    display_timezone=dt.UTC,
                    clock=lambda: dt.datetime(2026, 4, 30, 0, 0, tzinfo=dt.UTC),
                ),
            )
            schema = load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(reused, schema), [])
            self.assertEqual(reused["summary_mode"], "reused")
            self.assertEqual(reused["reused_from"], "2026-04-29T00:00:00Z")
            self.assertEqual(reused["generated_at"], "2026-04-30T00:00:00Z")
            self.assertEqual(reused["counts"]["passed"], 2)
            self.assertEqual(reused["termination_reason"], "reused_current_summary")

    def test_interpreter_path_classification_is_portable_and_does_not_record_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            self.assertEqual(classify_interpreter_path(vault, "python3"), "path_lookup")
            self.assertEqual(classify_interpreter_path(vault, ".venv/bin/python"), "repo_virtualenv")
            self.assertEqual(classify_interpreter_path(vault, "tools/python"), "repo_relative")
            self.assertEqual(
                classify_interpreter_path(vault, (vault / ".venv" / "bin" / "python").as_posix()),
                "repo_virtualenv",
            )
            self.assertEqual(classify_interpreter_path(vault, "/opt/venv/bin/python"), "external_virtualenv")

    def test_semantic_command_strips_interpreter_prefix(self) -> None:
        self.assertEqual(
            semantic_command(["python", "-m", "pytest", "tests/test_sample.py"]),
            ["-m", "pytest", "tests/test_sample.py"],
        )
        self.assertEqual(
            semantic_command([".venv/bin/python", "-m", "pytest", "-q"]),
            ["-m", "pytest", "-q"],
        )
        self.assertEqual(
            semantic_command(["/opt/venv/bin/python3", "-m", "pytest"]),
            ["-m", "pytest"],
        )
        self.assertEqual(
            semantic_command(["pytest", "tests/test_sample.py"]),
            ["pytest", "tests/test_sample.py"],
        )
        self.assertEqual(
            semantic_command(["python3", "pytest", "tests/test_sample.py"]),
            ["pytest", "tests/test_sample.py"],
        )
        self.assertEqual(semantic_command([]), [])
        self.assertEqual(semantic_command(["python"]), ["python"])

    def test_resolve_pytest_target_paths_expands_files_directories_and_node_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "tests" / "nested").mkdir(parents=True)
            (vault / "tests" / "test_alpha.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
            (vault / "tests" / "nested" / "beta_test.py").write_text(
                "def test_b():\n    pass\n",
                encoding="utf-8",
            )

            targets = resolve_pytest_target_paths(
                vault,
                [
                    "python",
                    "-m",
                    "pytest",
                    "-m",
                    "not slow",
                    "tests/test_alpha.py::test_a",
                    "tests/nested",
                    "-q",
                ],
            )

            self.assertEqual(
                targets,
                [
                    "tests/nested/beta_test.py",
                    "tests/test_alpha.py",
                ],
            )

    def test_collect_pytest_nodeid_digest_records_stable_selector_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "tests").mkdir()
            (vault / "tests" / "test_collect_sample.py").write_text(
                "def test_one():\n    assert True\n\ndef test_two():\n    assert True\n",
                encoding="utf-8",
            )

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(
                    returncode=0,
                    stdout=(
                        "tests/test_collect_sample.py::test_one\n"
                        "tests/test_collect_sample.py::test_two\n"
                    ),
                ),
            ) as run:
                digest = collect_pytest_nodeid_digest(
                    vault,
                    ["python", "-m", "pytest", "tests/test_collect_sample.py"],
                    timeout_seconds=30,
                )

            self.assertEqual(digest["status"], "collected")
            self.assertEqual(digest["nodeid_count"], 2)
            self.assertRegex(digest["sha256"], r"^[a-f0-9]{64}$")
            self.assertIn("--collect-only", digest["command"])
            self.assertEqual(run.call_count, 1)

    def test_collect_pytest_nodeid_digest_collects_selector_free_full_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(
                    returncode=0,
                    stdout=(
                        "tests/test_alpha.py::test_one\n"
                        "tests/test_beta.py::test_two\n"
                    ),
                ),
            ) as run:
                digest = collect_pytest_nodeid_digest(
                    vault,
                    ["python", "-m", "pytest"],
                    timeout_seconds=30,
                )

            self.assertEqual(digest["status"], "collected")
            self.assertEqual(digest["nodeid_count"], 2)
            self.assertIn("--collect-only", digest["command"])
            self.assertNotIn("tests/test_alpha.py", digest["command"])
            self.assertEqual(run.call_count, 1)

    def test_build_report_checks_nodeid_outcome_count_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = build_report(
                vault,
                command=["python", "-m", "pytest"],
                result=_result(returncode=0, stdout="= 2 passed, 1 skipped, 1 xfailed in 1.00s ="),
                duration_ms=1234,
                suite="pytest",
                context=_fixed_context(),
                collect_nodeids=True,
                collect_nodeid_digest={
                    "status": "collected",
                    "command": "python -m pytest --collect-only -q",
                    "nodeid_count": 4,
                    "sha256": "a" * 64,
                    "reason": "",
                },
            )

            self.assertEqual(report["nodeid_outcome_consistency"]["status"], "pass")
            self.assertEqual(report["nodeid_outcome_consistency"]["outcome_count"], 4)
            self.assertEqual(report["nodeid_outcome_consistency"]["delta"], 0)
            self.assertEqual(
                validate_with_schema(report, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_build_report_exposes_nodeid_outcome_count_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = build_report(
                vault,
                command=["python", "-m", "pytest"],
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1234,
                suite="pytest",
                context=_fixed_context(),
                collect_nodeids=True,
                collect_nodeid_digest={
                    "status": "collected",
                    "command": "python -m pytest --collect-only -q",
                    "nodeid_count": 3,
                    "sha256": "a" * 64,
                    "reason": "",
                },
            )

            self.assertEqual(report["nodeid_outcome_consistency"]["status"], "fail")
            self.assertEqual(report["nodeid_outcome_consistency"]["delta"], 1)
            self.assertEqual(
                validate_with_schema(report, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_collect_pytest_nodeid_digest_preserves_deselected_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "tests").mkdir()
            (vault / "tests" / "test_collect_sample.py").write_text(
                "def test_one():\n    assert True\n\ndef test_two():\n    assert True\n",
                encoding="utf-8",
            )

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(
                    returncode=0,
                    stdout="tests/test_collect_sample.py::test_one\n",
                ),
            ) as run:
                digest = collect_pytest_nodeid_digest(
                    vault,
                    [
                        "python",
                        "-m",
                        "pytest",
                        "-m",
                        "not release_sealing",
                        "tests/test_collect_sample.py",
                        "--deselect=tests/test_collect_sample.py::test_two",
                    ],
                    timeout_seconds=30,
                )
            targets = resolve_pytest_target_paths(
                vault,
                [
                    "python",
                    "-m",
                    "pytest",
                    "tests/test_collect_sample.py",
                    "--deselect",
                    "tests/test_collect_sample.py::test_two",
                ],
            )

            self.assertEqual(digest["status"], "collected")
            self.assertEqual(digest["nodeid_count"], 1)
            self.assertIn("-m 'not release_sealing'", digest["command"])
            self.assertIn("--deselect=tests/test_collect_sample.py::test_two", digest["command"])
            self.assertEqual(targets, ["tests/test_collect_sample.py"])
            self.assertEqual(run.call_count, 1)

    def test_build_report_structures_deselected_tests_from_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy_path = vault / "ops" / "policies" / "test-deselections.json"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/test-deselection-policy.schema.json",
                        "policy_kind": "test_deselection_policy",
                        "deselection_budget": {
                            "max_count": 1,
                            "risk_owner": "runtime-maintainer",
                            "expires_at": "2026-05-14T00:00:00Z",
                            "count_increase_gate_effect": "fail",
                            "expiry_gate_effect": "fail",
                        },
                        "deselected_tests": [
                            {
                                "nodeid": "tests/test_sample.py::test_two",
                                "reason": "self-referential generated artifact assertion",
                                "policy_ref": "ops/policies/test-deselections.json#sample",
                                "risk_owner": "runtime-maintainer",
                                "expires_at": "2026-05-14T00:00:00Z",
                                "release_blocking": False,
                                "expected_to_pass_after_refresh": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = build_report(
                vault,
                command=[
                    "python",
                    "-m",
                    "pytest",
                    "tests/test_sample.py",
                    "--deselect=tests/test_sample.py::test_two",
                ],
                result=_result(returncode=0, stdout="= 1 passed, 1 deselected in 1.00s ="),
                duration_ms=1234,
                suite="unit",
                context=_fixed_context(),
                deselection_policy_path="ops/policies/test-deselections.json",
            )

            self.assertEqual(
                report["deselected_tests"],
                [
                    {
                        "nodeid": "tests/test_sample.py::test_two",
                        "reason": "self-referential generated artifact assertion",
                        "policy_ref": "ops/policies/test-deselections.json#sample",
                        "risk_owner": "runtime-maintainer",
                        "expires_at": "2026-05-14T00:00:00Z",
                        "release_blocking": False,
                        "expected_to_pass_after_refresh": True,
                    }
                ],
            )
            self.assertEqual(report["deselection_lifecycle"]["status"], "pass")
            self.assertEqual(report["deselection_lifecycle"]["actual_deselected_count"], 1)
            self.assertIn("deselection_policy", report["input_fingerprints"])
            self.assertIn("deselected_tests", report["input_fingerprints"])
            self.assertIn("deselection_lifecycle", report["input_fingerprints"])
            self.assertEqual(
                validate_with_schema(report, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_deselection_lifecycle_fails_for_expired_or_over_budget_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy_path = vault / "ops" / "policies" / "test-deselections.json"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/test-deselection-policy.schema.json",
                        "policy_kind": "test_deselection_policy",
                        "deselection_budget": {
                            "max_count": 0,
                            "risk_owner": "runtime-maintainer",
                            "expires_at": "2026-04-29T00:00:00Z",
                            "count_increase_gate_effect": "fail",
                            "expiry_gate_effect": "fail",
                        },
                        "deselected_tests": [
                            {
                                "nodeid": "tests/test_sample.py::test_two",
                                "reason": "temporary self-reference",
                                "policy_ref": "ops/policies/test-deselections.json#sample",
                                "risk_owner": "runtime-maintainer",
                                "expires_at": "2026-04-29T00:00:00Z",
                                "release_blocking": False,
                                "expected_to_pass_after_refresh": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = build_report(
                vault,
                command=[
                    "python",
                    "-m",
                    "pytest",
                    "tests/test_sample.py",
                    "--deselect=tests/test_sample.py::test_two",
                ],
                result=_result(returncode=0, stdout="= 1 passed, 1 deselected in 1.00s ="),
                duration_ms=1234,
                suite="unit",
                context=_fixed_context(),
                deselection_policy_path="ops/policies/test-deselections.json",
            )

            lifecycle = report["deselection_lifecycle"]
            blocker_codes = {item["code"] for item in lifecycle["blockers"]}
            self.assertEqual(lifecycle["status"], "fail")
            self.assertTrue(lifecycle["over_budget"])
            self.assertEqual(lifecycle["expired_count"], 1)
            self.assertIn("deselection_budget_exceeded", blocker_codes)
            self.assertIn("expired_deselection", blocker_codes)
            self.assertIn("expired_deselection_budget", blocker_codes)
            self.assertEqual(
                validate_with_schema(report, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_aggregate_report_reuses_shards_without_running_pytest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            shard_dir = vault / "ops" / "reports" / "test-execution-summary-shards"
            shard_dir.mkdir(parents=True)
            first = build_report(
                vault,
                command=["python", "-m", "pytest", "tests/test_alpha.py"],
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="alpha",
                context=_fixed_context(),
            )
            second = build_report(
                vault,
                command=["python", "-m", "pytest", "tests/test_beta.py"],
                result=_result(returncode=0, stdout="= 3 passed, 1 skipped in 1.00s ="),
                duration_ms=2000,
                suite="beta",
                context=_fixed_context(),
            )
            (shard_dir / "alpha.json").write_text(json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8")
            (shard_dir / "beta.json").write_text(json.dumps(second, ensure_ascii=False, indent=2), encoding="utf-8")

            aggregate = build_aggregate_report(
                vault,
                shard_paths=[
                    "ops/reports/test-execution-summary-shards/alpha.json",
                    "ops/reports/test-execution-summary-shards/beta.json",
                ],
                suite="report-contract-summary",
                context=_fixed_context(),
            )

            self.assertEqual(aggregate["summary_mode"], "aggregate")
            self.assertEqual(aggregate["suite_scope"], "report_contract_summary")
            self.assertFalse(aggregate["represents_full_suite"])
            self.assertIn("report-contract-summary", aggregate["not_full_suite_reason"])
            self.assertEqual(aggregate["full_suite_evidence"]["status"], "not_represented")
            self.assertEqual(aggregate["status"], "pass")
            self.assertEqual(aggregate["counts"]["passed"], 5)
            self.assertEqual(aggregate["counts"]["skipped"], 1)
            self.assertEqual(aggregate["duration_ms"], 3000)
            self.assertEqual(len(aggregate["shards"]), 2)
            self.assertIn("shard_1", aggregate["input_fingerprints"])
            self.assertEqual(
                aggregate["shards"],
                [
                    {
                        "path": "ops/reports/test-execution-summary-shards/alpha.json",
                        "suite": "alpha",
                        "status": "pass",
                        "generated_at": "2026-04-29T00:00:00Z",
                        "duration_ms": 1000,
                        "counts": {
                            "passed": 2,
                            "failed": 0,
                            "errors": 0,
                            "skipped": 0,
                            "xfailed": 0,
                            "xpassed": 0,
                            "warnings": 0,
                        },
                        "represents_full_suite": False,
                    },
                    {
                        "path": "ops/reports/test-execution-summary-shards/beta.json",
                        "suite": "beta",
                        "status": "pass",
                        "generated_at": "2026-04-29T00:00:00Z",
                        "duration_ms": 2000,
                        "counts": {
                            "passed": 3,
                            "failed": 0,
                            "errors": 0,
                            "skipped": 1,
                            "xfailed": 0,
                            "xpassed": 0,
                            "warnings": 0,
                        },
                        "represents_full_suite": False,
                    },
                ],
            )
            self.assertEqual(
                validate_with_schema(aggregate, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_aggregate_report_marks_full_suite_only_when_every_shard_represents_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            shard_dir = vault / "ops" / "reports" / "test-execution-summary-full-shards"
            shard_dir.mkdir(parents=True)

            shard = build_report(
                vault,
                command=["python", "-m", "pytest"],
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="full-shard-1",
                context=_fixed_context(),
                collect_nodeids=True,
                collect_nodeid_digest={
                    "status": "collected",
                    "command": "python -m pytest --collect-only -q",
                    "nodeid_count": 2,
                    "sha256": "a" * 64,
                    "reason": "",
                },
            )
            (shard_dir / "full-suite-shard-1.json").write_text(
                json.dumps(shard, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            aggregate = build_aggregate_report(
                vault,
                shard_paths=["ops/reports/test-execution-summary-full-shards/full-suite-shard-1.json"],
                suite="full",
                context=_fixed_context(),
            )

            self.assertEqual(aggregate["summary_mode"], "aggregate")
            self.assertEqual(aggregate["suite_scope"], "full_suite")
            self.assertTrue(aggregate["represents_full_suite"])
            self.assertEqual(aggregate["not_full_suite_reason"], "")
            self.assertEqual(aggregate["full_suite_evidence"]["status"], "represented")
            self.assertEqual(aggregate["pytest_collect_nodeid_digest"]["status"], "collected")
            self.assertEqual(aggregate["pytest_collect_nodeid_digest"]["nodeid_count"], 2)
            self.assertEqual(aggregate["nodeid_outcome_consistency"]["status"], "pass")
            self.assertEqual(
                set(aggregate["nodeid_outcome_consistency"]),
                {
                    "status",
                    "nodeid_count",
                    "outcome_count",
                    "counted_outcomes",
                    "delta",
                    "reason",
                },
            )
            self.assertEqual(aggregate["shards"][0]["represents_full_suite"], True)
            self.assertEqual(
                validate_with_schema(aggregate, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)),
                [],
            )

    def test_cli_only_reuses_shards_when_aggregate_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            shard_dir = vault / "ops" / "reports" / "test-execution-summary-shards"
            shard_dir.mkdir(parents=True)
            shard = build_report(
                vault,
                command=["python", "-m", "pytest", "tests/test_alpha.py"],
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="alpha",
                context=_fixed_context(),
            )
            (shard_dir / "alpha.json").write_text(json.dumps(shard, ensure_ascii=False, indent=2), encoding="utf-8")
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(returncode=0, stdout="= 1 passed in 0.01s ="),
            ) as run:
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/test-execution-summary.json",
                        "--suite",
                        "unit",
                        "--",
                        sys.executable,
                        "-m",
                        "pytest",
                        "tests/test_sample.py",
                    ]
                )
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(returncode, 0)
            self.assertEqual(run.call_count, 1)
            self.assertNotEqual(payload.get("summary_mode"), "aggregate")
            self.assertEqual(payload["counts"]["passed"], 1)

    def test_cli_reuse_if_current_skips_pytest_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            test_file = vault / "tests" / "test_sample.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            command = [sys.executable, "-m", "pytest", "tests/test_sample.py"]
            existing = build_report(
                vault,
                command=command,
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="unit",
                context=_fixed_context(),
            )
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(returncode=1, stdout="= 1 failed in 0.01s ="),
            ) as run:
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/test-execution-summary.json",
                        "--suite",
                        "unit",
                        "--reuse-if-current",
                        "--",
                        *command,
                    ]
                )
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(returncode, 0)
            self.assertEqual(run.call_count, 0)
            self.assertEqual(payload["summary_mode"], "reused")
            self.assertEqual(payload["counts"]["passed"], 2)
            self.assertEqual(payload["reused_from"], "2026-04-29T00:00:00Z")

    def test_cli_reuse_if_current_falls_back_when_target_fingerprint_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            test_file = vault / "tests" / "test_sample.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            command = [sys.executable, "-m", "pytest", "tests/test_sample.py"]
            existing = build_report(
                vault,
                command=command,
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="unit",
                context=_fixed_context(),
            )
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            test_file.write_text("def test_ok():\n    assert True\n\ndef test_new():\n    assert True\n", encoding="utf-8")

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(returncode=0, stdout="= 3 passed in 0.01s ="),
            ) as run:
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/test-execution-summary.json",
                        "--suite",
                        "unit",
                        "--reuse-if-current",
                        "--",
                        *command,
                    ]
                )
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(returncode, 0)
            self.assertEqual(run.call_count, 1)
            self.assertNotEqual(payload.get("summary_mode"), "reused")
            self.assertEqual(payload["counts"]["passed"], 3)

    def test_cli_reuse_only_fails_fast_when_source_tree_fingerprint_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            test_file = vault / "tests" / "test_sample.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
            command = [sys.executable, "-m", "pytest", "tests/test_sample.py"]
            existing = build_report(
                vault,
                command=command,
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="unit",
                context=_fixed_context(),
            )
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
            (vault / "README.md").write_text("# Test\n\nSource tree changed.\n", encoding="utf-8")

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(returncode=0, stdout="= 3 passed in 0.01s ="),
            ) as run:
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "tmp/test-execution-summary-check.json",
                        "--suite",
                        "unit",
                        "--reuse-if-current",
                        "--reuse-only",
                        "--reuse-from",
                        "ops/reports/test-execution-summary.json",
                        "--",
                        *command,
                    ]
                )

            self.assertEqual(returncode, 1)
            self.assertEqual(run.call_count, 0)
            self.assertFalse((vault / "tmp" / "test-execution-summary-check.json").exists())

    def test_cli_aggregate_reuse_only_fails_fast_when_full_suite_evidence_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            shard = build_report(
                vault,
                command=[sys.executable, "-m", "pytest"],
                result=_result(returncode=0, stdout="= 2 passed in 1.00s ="),
                duration_ms=1000,
                suite="full-shard-1",
                context=_fixed_context(),
                collect_nodeids=True,
                collect_nodeid_digest={
                    "status": "collected",
                    "command": "python -m pytest --collect-only -q",
                    "nodeid_count": 2,
                    "sha256": "a" * 64,
                    "reason": "",
                },
            )
            shard_dir = vault / "ops" / "reports" / "test-execution-summary-full-shards"
            shard_dir.mkdir(parents=True)
            (shard_dir / "full-suite-shard-1.json").write_text(
                json.dumps(shard, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            aggregate = build_aggregate_report(
                vault,
                shard_paths=["ops/reports/test-execution-summary-full-shards/full-suite-shard-1.json"],
                suite="full",
                context=_fixed_context(),
            )
            out_path = vault / "ops" / "reports" / "test-execution-summary-full.json"
            out_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
            (vault / "README.md").write_text("# Test\n\nSource tree changed.\n", encoding="utf-8")

            returncode = summary_main(
                [
                    "--vault",
                    str(vault),
                    "--out",
                    "tmp/test-execution-summary-full-check.json",
                    "--suite",
                    "full",
                    "--aggregate",
                    "--reuse-if-current",
                    "--reuse-only",
                    "--reuse-from",
                    "ops/reports/test-execution-summary-full.json",
                ]
            )

            self.assertEqual(returncode, 1)
            self.assertFalse((vault / "tmp" / "test-execution-summary-full-check.json").exists())

    def test_cli_preserves_deselection_policy_in_written_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "tests").mkdir()
            (vault / "tests" / "test_sample.py").write_text(
                "def test_one():\n    assert True\n\ndef test_two():\n    assert True\n",
                encoding="utf-8",
            )
            policy_path = vault / "ops" / "policies" / "test-deselections.json"
            policy_path.parent.mkdir(parents=True, exist_ok=True)
            policy_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/test-deselection-policy.schema.json",
                        "policy_kind": "test_deselection_policy",
                        "deselection_budget": {
                            "max_count": 1,
                            "risk_owner": "runtime-maintainer",
                            "expires_at": "2026-05-14T00:00:00Z",
                            "count_increase_gate_effect": "fail",
                            "expiry_gate_effect": "fail",
                        },
                        "deselected_tests": [
                            {
                                "nodeid": "tests/test_sample.py::test_two",
                                "reason": "self-referential generated artifact assertion",
                                "policy_ref": "ops/policies/test-deselections.json#sample",
                                "risk_owner": "runtime-maintainer",
                                "expires_at": "2026-05-14T00:00:00Z",
                                "release_blocking": False,
                                "expected_to_pass_after_refresh": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"

            with (
                patch("ops.scripts.test_execution_summary.RuntimeContext.from_policy", return_value=_fixed_context()),
                patch(
                    "ops.scripts.test_execution_summary.run_with_timeout",
                    return_value=_result(returncode=0, stdout="= 1 passed, 1 deselected in 0.01s ="),
                ),
            ):
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/test-execution-summary.json",
                        "--suite",
                        "unit",
                        "--deselection-policy",
                        "ops/policies/test-deselections.json",
                        "--",
                        sys.executable,
                        "-m",
                        "pytest",
                        "tests/test_sample.py",
                        "--deselect=tests/test_sample.py::test_two",
                    ]
                )
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(returncode, 0)
            self.assertIn("--deselection-policy ops/policies/test-deselections.json", payload["source_command"])
            self.assertEqual(payload["deselected_tests"][0]["policy_ref"], "ops/policies/test-deselections.json#sample")
            self.assertEqual(payload["deselected_tests"][0]["release_blocking"], False)
            self.assertEqual(payload["deselection_lifecycle"]["status"], "pass")

    def test_cli_records_junit_and_execution_log_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            junit_path = vault / "tmp" / "pytest.xml"
            log_path = vault / "tmp" / "pytest.log"
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"

            def fake_run(command: list[str], *, cwd: Path, timeout_seconds: int) -> TimedProcessResult:
                junit_path.parent.mkdir(parents=True, exist_ok=True)
                junit_path.write_text("<testsuite tests='1'></testsuite>\n", encoding="utf-8")
                return _result(returncode=0, stdout="= 1 passed in 0.01s =")

            with patch("ops.scripts.test_execution_summary.run_with_timeout", side_effect=fake_run):
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/test-execution-summary.json",
                        "--suite",
                        "pytest",
                        "--junit-xml-path",
                        "tmp/pytest.xml",
                        "--execution-log-out",
                        "tmp/pytest.log",
                        "--",
                        sys.executable,
                        "-m",
                        "pytest",
                    ]
                )
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(returncode, 0)
            self.assertTrue(log_path.exists())
            artifacts = {item["kind"]: item for item in payload["evidence_artifacts"]}
            self.assertEqual(set(artifacts), {"junit_xml", "execution_log"})
            self.assertTrue(artifacts["junit_xml"]["exists"])
            self.assertTrue(artifacts["execution_log"]["exists"])
            self.assertRegex(artifacts["junit_xml"]["sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(artifacts["execution_log"]["sha256"], r"^[a-f0-9]{64}$")
            self.assertEqual(artifacts["junit_xml"]["consistency_status"], "pass")
            self.assertEqual(artifacts["junit_xml"]["observed_count"], 1)
            self.assertEqual(artifacts["junit_xml"]["expected_count"], 1)
            self.assertEqual(validate_with_schema(payload, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)), [])

    def test_cli_marks_junit_count_mismatch_as_artifact_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            junit_path = vault / "tmp" / "pytest.xml"
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"

            def fake_run(command: list[str], *, cwd: Path, timeout_seconds: int) -> TimedProcessResult:
                junit_path.parent.mkdir(parents=True, exist_ok=True)
                junit_path.write_text("<testsuite tests='1'></testsuite>\n", encoding="utf-8")
                return _result(returncode=0, stdout="= 2 passed in 0.01s =")

            with patch("ops.scripts.test_execution_summary.run_with_timeout", side_effect=fake_run):
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/test-execution-summary.json",
                        "--suite",
                        "pytest",
                        "--junit-xml-path",
                        "tmp/pytest.xml",
                        "--",
                        sys.executable,
                        "-m",
                        "pytest",
                    ]
                )
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            artifacts = {item["kind"]: item for item in payload["evidence_artifacts"]}

            self.assertEqual(returncode, 0)
            self.assertEqual(artifacts["junit_xml"]["consistency_status"], "attention")
            self.assertEqual(artifacts["junit_xml"]["observed_count"], 1)
            self.assertEqual(artifacts["junit_xml"]["expected_count"], 2)
            self.assertIn("does not match", artifacts["junit_xml"]["consistency_reason"])
            self.assertEqual(validate_with_schema(payload, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)), [])

    def test_cli_records_failed_and_error_nodeids_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            failed_nodeids_path = vault / "tmp" / "failed-nodeids.txt"
            out_path = vault / "ops" / "reports" / "test-execution-summary.json"

            with patch(
                "ops.scripts.test_execution_summary.run_with_timeout",
                return_value=_result(
                    returncode=1,
                    stdout=(
                        "FAILED tests/test_sample.py::test_one - AssertionError: boom\n"
                        "ERROR tests/test_sample.py::test_two - RuntimeError: nope\n"
                        "= 1 failed, 1 error in 0.01s =\n"
                    ),
                ),
            ):
                returncode = summary_main(
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "ops/reports/test-execution-summary.json",
                        "--suite",
                        "pytest",
                        "--failed-nodeids-out",
                        "tmp/failed-nodeids.txt",
                        "--",
                        sys.executable,
                        "-m",
                        "pytest",
                        "tests/test_sample.py",
                    ]
                )
            payload = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(returncode, 1)
            self.assertTrue(failed_nodeids_path.exists())
            self.assertEqual(
                failed_nodeids_path.read_text(encoding="utf-8"),
                "tests/test_sample.py::test_one\ntests/test_sample.py::test_two\n",
            )
            artifacts = {item["kind"]: item for item in payload["evidence_artifacts"]}
            self.assertIn("failed_nodeids", artifacts)
            self.assertEqual(artifacts["failed_nodeids"]["path"], "tmp/failed-nodeids.txt")
            self.assertTrue(artifacts["failed_nodeids"]["exists"])
            self.assertRegex(artifacts["failed_nodeids"]["sha256"], r"^[a-f0-9]{64}$")
            self.assertEqual(artifacts["failed_nodeids"]["consistency_status"], "pass")
            self.assertEqual(artifacts["failed_nodeids"]["observed_count"], 2)
            self.assertEqual(artifacts["failed_nodeids"]["expected_count"], 2)
            self.assertEqual(validate_with_schema(payload, load_schema(vault / TEST_EXECUTION_SUMMARY_SCHEMA_PATH)), [])


if __name__ == "__main__":
    unittest.main()
