from __future__ import annotations

import copy
import datetime as dt
import inspect
import json
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.core.artifact_binding_runtime import (
    RAW_BINDING_MODE,
    binding_file_digest,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.operator_release_summary import (
    OperatorReleaseSummaryRequest,
    build_report as build_operator_release_summary,
)
from ops.scripts.release.release_closeout_fixed_point import (
    DEFAULT_OUT,
    POLICY_PATH,
    _policy_runtime,
    build_dry_run_report,
    build_report,
    fixed_point_output_paths_at_or_downstream,
    fixed_point_writer_specs_from_policy,
    parse_args,
    write_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-closeout-fixed-point.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.UTC),
    )


class ReleaseCloseoutFixedPointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file(POLICY_PATH)
        self._copy_support_file(
            "ops/schemas/release-closeout-fixed-point.schema.json"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            (REPO_ROOT / rel_path).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _policy(self) -> dict[str, Any]:
        return json.loads((self.vault / POLICY_PATH).read_text(encoding="utf-8"))

    def _write_policy(self, policy: dict[str, Any]) -> None:
        (self.vault / POLICY_PATH).write_text(
            json.dumps(policy, indent=2) + "\n",
            encoding="utf-8",
        )

    def _writer_outputs(self) -> dict[str, list[str]]:
        return {
            str(writer["target"]): [str(path) for path in writer["produces"]]
            for writer in fixed_point_writer_specs_from_policy(self.vault)
        }

    def _successful_runner(self, calls: list[str]):
        outputs = self._writer_outputs()

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> dict[str, Any]:
            target = argv[1]
            calls.append(target)
            for rel_path in outputs.get(target, []):
                path = cwd / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "target": target,
                            "generated_at": env["LLMWIKI_RUNTIME_UTC_NOW"],
                            "source_revision": f"revision-for-{target}",
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
            return {
                "command": list(argv),
                "returncode": 0,
                "timed_out": False,
                "timeout_seconds": timeout_seconds,
                "termination_reason": "",
                "duration_ms": 1,
                "stdout_tail": "",
                "stderr_tail": "",
                "status": "pass",
            }

        return runner

    def test_policy_derives_binding_aware_tracked_artifacts_in_required_order(
        self,
    ) -> None:
        policy = self._policy()
        runtime = _policy_runtime(self.vault)

        expected_tracked = [
            {
                "name": str(writer["name"]),
                "path": str(path),
                "binding_mode": str(writer["binding_mode"]),
            }
            for writer in policy["writers"]
            for path in writer["produces"]
        ]
        self.assertEqual(runtime.tracked_artifacts, expected_tracked)
        modes = {
            writer["target"]: writer["binding_mode"] for writer in runtime.writers
        }
        self.assertEqual(
            modes["release-closeout-batch-manifest-promote"],
            "revision",
        )
        self.assertEqual(
            {
                target
                for target, mode in modes.items()
                if mode == "revision"
            },
            {
                "auto-improve-readiness-report-body-current-or-refresh",
                "release-closeout-summary-report",
                "release-evidence-cohort",
                "release-closeout-batch-manifest-promote",
            },
        )
        self.assertEqual(set(modes.values()), {"content", "revision"})
        self.assertEqual(runtime.writer_targets[-1], "operator-release-summary-terminal")
        self.assertEqual(
            runtime.writers[-1]["depends_on"],
            ["release-evidence-closeout-self-check"],
        )
        self.assertEqual(
            runtime.writers[-1]["produces"],
            ["ops/operator/operator-release-summary.json"],
        )
        positions = {
            target: runtime.writer_targets.index(target)
            for target in (
                "artifact-freshness",
                "external-report-action-matrix",
                "generated-artifact-index-body-current-or-refresh",
                "auto-improve-readiness-report-body-current-or-refresh",
            )
        }
        self.assertLess(
            positions["artifact-freshness"],
            positions["external-report-action-matrix"],
        )
        self.assertLess(
            positions["external-report-action-matrix"],
            positions["generated-artifact-index-body-current-or-refresh"],
        )
        self.assertLess(
            positions["generated-artifact-index-body-current-or-refresh"],
            positions["auto-improve-readiness-report-body-current-or-refresh"],
        )
        downstream_paths = fixed_point_output_paths_at_or_downstream(
            self.vault,
            "generated-artifact-index-body-current-or-refresh",
        )
        self.assertIn("ops/reports/generated-artifact-index.json", downstream_paths)
        self.assertIn("ops/reports/release-closeout-summary.json", downstream_paths)
        self.assertIn("ops/operator/operator-release-summary.json", downstream_paths)
        self.assertNotIn("ops/reports/artifact-freshness-report.json", downstream_paths)

    def test_policy_rejects_missing_and_invalid_binding_modes(self) -> None:
        for invalid_mode in (None, "not-a-mode"):
            with self.subTest(binding_mode=invalid_mode):
                policy = self._policy()
                if invalid_mode is None:
                    policy["writers"][0].pop("binding_mode")
                else:
                    policy["writers"][0]["binding_mode"] = invalid_mode
                self._write_policy(policy)
                with self.assertRaisesRegex(ValueError, "binding_mode"):
                    _policy_runtime(self.vault)
                self._copy_support_file(POLICY_PATH)

    def test_policy_rejects_cycle_duplicate_producer_unknown_dependency_and_order(
        self,
    ) -> None:
        cases = [
            (
                lambda policy: policy["writers"][0].update(
                    {"depends_on": ["artifact-freshness"]}
                ),
                "dependency cycle",
            ),
            (
                lambda policy: policy["writers"][1].update(
                    {"produces": list(policy["writers"][0]["produces"])}
                ),
                "duplicate produced path",
            ),
            (
                lambda policy: policy["writers"][1].update(
                    {"depends_on": ["not-a-writer"]}
                ),
                "unknown depends_on",
            ),
            (
                lambda policy: policy["writers"].__setitem__(
                    slice(1, 3),
                    [policy["writers"][2], policy["writers"][1]],
                ),
                "not topological",
            ),
        ]
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                policy = self._policy()
                mutate(policy)
                self._write_policy(policy)
                with self.assertRaisesRegex(ValueError, expected):
                    _policy_runtime(self.vault)
                self._copy_support_file(POLICY_PATH)

    def test_obsolete_execution_parameters_are_removed(self) -> None:
        parameters = inspect.signature(build_report).parameters
        self.assertNotIn("max_iterations", parameters)
        self.assertNotIn("baseline_before_first_iteration", parameters)
        with self.assertRaises(SystemExit):
            parse_args(["--max-iterations", "2"])
        with self.assertRaises(SystemExit):
            parse_args(["--baseline-before-first-iteration"])

    def test_v2_report_runs_each_writer_once_and_records_binding_maps(self) -> None:
        calls: list[str] = []
        runtime = _policy_runtime(self.vault)

        report = build_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_runner(calls),
        )

        writer_calls = [target for target in calls if target in runtime.writer_targets]
        self.assertEqual(writer_calls, runtime.writer_targets)
        self.assertEqual(len(writer_calls), len(set(writer_calls)))
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["execution_pass_count"], 1)
        self.assertEqual(report["execution"]["status"], "pass")
        self.assertEqual(
            report["execution"]["reason"],
            "single_topological_pass_completed",
        )
        obsolete_fields = {
            "max_iterations",
            "iteration_count",
            "iterations",
            "converged",
            "converged_iteration",
            "convergence_summary",
            "final_digest_map",
        }
        self.assertTrue(obsolete_fields.isdisjoint(report))
        expected_modes = {
            item["path"]: item["binding_mode"] for item in runtime.tracked_artifacts
        }
        self.assertEqual(report["binding_mode_map"], expected_modes)
        self.assertEqual(
            report["execution"]["binding_mode_map"],
            expected_modes,
        )
        for item in runtime.tracked_artifacts:
            rel_path = item["path"]
            _projection, expected_digest = binding_file_digest(
                self.vault / rel_path,
                binding_mode=item["binding_mode"],
            )
            self.assertEqual(report["binding_digest_map"][rel_path], expected_digest)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        written = write_report(self.vault, report)
        self.assertTrue(written.is_file())

    def test_terminal_operator_writer_reads_final_batch_and_self_check(self) -> None:
        calls: list[str] = []
        observed_summaries: list[dict[str, Any]] = []
        outputs = self._writer_outputs()

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> dict[str, Any]:
            del timeout_seconds
            target = argv[1]
            calls.append(target)
            for rel_path in outputs.get(target, []):
                path = cwd / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if target == "release-closeout-batch-manifest-promote":
                    payload: dict[str, Any] = {
                        "schema_version": 2,
                        "artifacts": [],
                        "release_decision_snapshot": {},
                    }
                elif target == "release-evidence-closeout-self-check":
                    payload = {"status": {"result": "pass"}}
                elif target == "operator-release-summary-terminal":
                    summary = build_operator_release_summary(
                        cwd,
                        OperatorReleaseSummaryRequest(context=fixed_context()),
                    )
                    observed_summaries.append(summary)
                    payload = summary
                else:
                    payload = {
                        "target": target,
                        "generated_at": env["LLMWIKI_RUNTIME_UTC_NOW"],
                        "source_revision": f"revision-for-{target}",
                    }
                path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            return {
                "command": list(argv),
                "returncode": 0,
                "duration_ms": 1,
                "stdout_tail": "",
                "stderr_tail": "",
                "status": "pass",
            }

        report = build_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(calls[-1], "operator-release-summary-terminal")
        self.assertEqual(len(observed_summaries), 1)
        summary = observed_summaries[0]
        self.assertEqual(summary["batch_verify"]["manifest_schema_version"], 2)
        self.assertEqual(summary["batch_verify"]["artifact_count"], 0)
        self.assertEqual(summary["batch_verify"]["tmp_json_count"], 0)

    def test_schema_rejects_writer_run_count_above_single_pass(self) -> None:
        report = build_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_runner([]),
        )
        report["duration_summary"]["writer_costs"][0]["run_count"] = 2

        errors = validate_with_schema(report, load_schema(SCHEMA_PATH))

        self.assertTrue(
            any(
                "$.duration_summary.writer_costs[0].run_count" in error
                for error in errors
            ),
            errors,
        )

    def test_schema_rejects_zero_execution_and_pass_failure_signals(self) -> None:
        report = build_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_runner([]),
        )
        zero_execution = copy.deepcopy(report)
        zero_execution["execution"]["selected_targets"] = []
        zero_execution["execution"]["command_results"] = []
        zero_execution["duration_summary"]["command_run_count"] = 0
        zero_errors = validate_with_schema(zero_execution, load_schema(SCHEMA_PATH))

        failure_signals = copy.deepcopy(report)
        command_result = failure_signals["execution"]["command_results"][0]
        command_result["timed_out"] = True
        command_result["undeclared_tracked_writes"] = ["ops/reports/unexpected.json"]
        command_result["issues"] = ["undeclared_tracked_write"]
        signal_errors = validate_with_schema(failure_signals, load_schema(SCHEMA_PATH))

        self.assertTrue(
            any("$.execution.selected_targets" in error for error in zero_errors),
            zero_errors,
        )
        self.assertTrue(
            any("$.execution.command_results" in error for error in zero_errors),
            zero_errors,
        )
        self.assertTrue(
            any("$.duration_summary.command_run_count" in error for error in zero_errors),
            zero_errors,
        )
        self.assertTrue(signal_errors)

    def test_initial_target_selects_downstream_closure_once(self) -> None:
        calls: list[str] = []
        runtime = _policy_runtime(self.vault)
        initial_target = "external-report-action-matrix"
        expected_writers = [
            target
            for target in runtime.writer_targets
            if target == initial_target
            or target in runtime.downstream_by_target[initial_target]
        ]

        report = build_report(
            self.vault,
            initial_targets=(initial_target,),
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_runner(calls),
        )

        writer_calls = [target for target in calls if target in runtime.writer_targets]
        self.assertEqual(writer_calls, expected_writers)
        self.assertEqual(len(writer_calls), len(set(writer_calls)))
        self.assertNotIn("artifact-freshness", writer_calls)
        self.assertEqual(report["execution"]["selected_targets"], expected_writers)

    def test_content_and_revision_bindings_follow_declared_policy(self) -> None:
        report = build_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_runner([]),
        )
        paths_by_mode = {
            item["binding_mode"]: item["path"]
            for item in report["tracked_artifacts"]
        }
        content_path = paths_by_mode["content"]
        revision_path = paths_by_mode["revision"]
        for rel_path in (content_path, revision_path):
            path = self.vault / rel_path
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["source_revision"] = "changed-revision"
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

        _mode, content_digest = binding_file_digest(
            self.vault / content_path,
            binding_mode="content",
        )
        _mode, revision_digest = binding_file_digest(
            self.vault / revision_path,
            binding_mode="revision",
        )

        self.assertEqual(
            content_digest,
            report["binding_digest_map"][content_path],
        )
        self.assertNotEqual(
            revision_digest,
            report["binding_digest_map"][revision_path],
        )

    def test_raw_binding_policy_emits_schema_valid_report(self) -> None:
        policy = self._policy()
        policy["writers"][0]["binding_mode"] = RAW_BINDING_MODE
        self._write_policy(policy)

        report = build_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_runner([]),
        )

        raw_path = str(policy["writers"][0]["produces"][0])
        self.assertEqual(report["binding_mode_map"][raw_path], RAW_BINDING_MODE)
        self.assertEqual(
            report["execution"]["binding_mode_map"][raw_path],
            RAW_BINDING_MODE,
        )
        self.assertEqual(
            report["tracked_artifacts"][0]["binding_mode"],
            RAW_BINDING_MODE,
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        write_report(self.vault, report)

    def test_undeclared_tracked_write_fails_execution(self) -> None:
        outputs = self._writer_outputs()
        undeclared_path = outputs["generated-artifact-index-body-current-or-refresh"][0]

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> dict[str, Any]:
            target = argv[1]
            for rel_path in outputs.get(target, []):
                path = cwd / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"target": target}), encoding="utf-8")
            if target == "artifact-freshness":
                path = cwd / undeclared_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"written_by": "wrong-writer"}', encoding="utf-8")
            return {
                "command": list(argv),
                "returncode": 0,
                "timed_out": False,
                "timeout_seconds": timeout_seconds,
                "termination_reason": "",
                "duration_ms": 1,
                "stdout_tail": "",
                "stderr_tail": "",
                "status": "pass",
            }

        report = build_report(
            self.vault,
            initial_targets=("artifact-freshness",),
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["execution"]["reason"], "undeclared_tracked_write")
        command_result = report["execution"]["command_results"][0]
        self.assertEqual(command_result["status"], "fail")
        self.assertEqual(
            command_result["termination_reason"],
            "undeclared_tracked_write",
        )
        self.assertEqual(
            command_result["undeclared_tracked_writes"],
            [undeclared_path],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_identical_byte_undeclared_tracked_replacement_fails_execution(
        self,
    ) -> None:
        outputs = self._writer_outputs()
        undeclared_path = outputs["generated-artifact-index-body-current-or-refresh"][0]
        existing_path = self.vault / undeclared_path
        existing_path.parent.mkdir(parents=True, exist_ok=True)
        existing_bytes = b'{"stable": true}\n'
        existing_path.write_bytes(existing_bytes)

        def runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str],
        ) -> dict[str, Any]:
            target = argv[1]
            for rel_path in outputs.get(target, []):
                path = cwd / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"target": target}), encoding="utf-8")
            if target == "artifact-freshness":
                replacement = existing_path.with_suffix(".replacement.json")
                replacement.write_bytes(existing_bytes)
                replacement.replace(existing_path)
            return {
                "command": list(argv),
                "returncode": 0,
                "timed_out": False,
                "timeout_seconds": timeout_seconds,
                "termination_reason": "",
                "duration_ms": 1,
                "stdout_tail": "",
                "stderr_tail": "",
                "status": "pass",
            }

        report = build_report(
            self.vault,
            initial_targets=("artifact-freshness",),
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(report["status"], "fail")
        command_result = report["execution"]["command_results"][0]
        self.assertEqual(
            command_result["termination_reason"],
            "undeclared_tracked_write",
        )
        self.assertEqual(
            command_result["undeclared_tracked_writes"],
            [undeclared_path],
        )
        self.assertEqual(existing_path.read_bytes(), existing_bytes)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_dry_run_rejects_v1_as_current_authority(self) -> None:
        runtime = _policy_runtime(self.vault)
        legacy_map = dict.fromkeys(runtime.tracked_paths, "missing")
        (self.vault / DEFAULT_OUT).parent.mkdir(parents=True, exist_ok=True)
        (self.vault / DEFAULT_OUT).write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "pass",
                    "artifact_status": "current",
                    "currentness": {"status": "current"},
                    "final_digest_map": legacy_map,
                    "iterations": [],
                }
            ),
            encoding="utf-8",
        )

        report = build_dry_run_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["fixed_point_report"]["load_status"],
            "unsupported_schema_version",
        )
        self.assertEqual(
            report["recommended_targets"],
            runtime.writer_targets,
        )

    def test_dry_run_accepts_written_v2_authority(self) -> None:
        report = build_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_runner([]),
        )
        write_report(self.vault, report)

        dry_run = build_dry_run_report(self.vault, context=fixed_context())

        self.assertEqual(dry_run["fixed_point_report"]["load_status"], "ok")
        self.assertEqual(dry_run["fixed_point_report"]["status"], "pass")
