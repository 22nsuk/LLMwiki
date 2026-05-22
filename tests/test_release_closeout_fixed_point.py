from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from ops.scripts.release_closeout_fixed_point import (
    ARTIFACT_FRESHNESS_REPORT_PATH,
    DRY_RUN_SCHEMA_PATH,
    DEFAULT_OUT,
    bootstrap_post_promote_freshness,
    build_dry_run_report,
    build_report,
    main as fixed_point_main,
    write_dry_run_plan,
    write_dry_run_recommended_targets,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-closeout-fixed-point.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 9, 12, 0, tzinfo=dt.timezone.utc),
    )


TARGET_TO_TRACKED_PATH = {
    "auto-improve-readiness-worktree-guard": "ops/reports/goal-worktree-guard.json",
    "generated-artifact-index-body": "ops/reports/generated-artifact-index.json",
    "artifact-freshness": "ops/reports/artifact-freshness-report.json",
    "auto-improve-readiness-report-body": "ops/reports/auto-improve-readiness.json",
    "release-closeout-summary-report": "ops/reports/release-closeout-summary.json",
    "learning-readiness-signoff-revalidation": "ops/reports/learning-readiness-signoff-revalidation.json",
    "release-evidence-cohort": "ops/reports/release-evidence-cohort.json",
    "release-evidence-dashboard-report": "ops/reports/release-evidence-dashboard.json",
    "release-lane-summary": "ops/reports/release-lane-summary.json",
    "release-clean-blocker-ledger": "ops/reports/release-clean-blocker-ledger.json",
    "release-closeout-batch-manifest-promote": "ops/reports/release-closeout-batch-manifest.json",
    "release-evidence-closeout-self-check": "ops/reports/release-evidence-closeout-self-check.json",
}


class ReleaseCloseoutFixedPointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self._copy_support_file("ops/schemas/release-closeout-fixed-point.schema.json")
        self._copy_support_file("ops/schemas/release-closeout-post-check-finalizer.schema.json")
        self._copy_support_file("ops/policies/release-closeout-fixed-point.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            (REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8"
        )

    def _write_tracked_payload(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def _write_artifact_freshness_fixed_point_debt(self, *, has_debt: bool) -> None:
        record: dict[str, Any] = {
            "path": DEFAULT_OUT,
            "schema_validation_status": "pass",
            "issues": [],
            "schema_validation_errors": [],
        }
        if has_debt:
            record.update(
                {
                    "schema_validation_status": "fail",
                    "issues": ["schema_validation_failed"],
                    "schema_validation_errors": [
                        "$.iterations[0]: missing required property 'selected_targets'"
                    ],
                }
            )
        self._write_tracked_payload(
            ARTIFACT_FRESHNESS_REPORT_PATH,
            {
                "artifact_records": [record],
            },
        )

    def _seed_tracked_artifacts_with_fixed_point_baseline(self) -> None:
        source_tree_fingerprint = release_source_tree_fingerprint(self.vault)
        for rel_path in TARGET_TO_TRACKED_PATH.values():
            self._write_tracked_payload(
                rel_path,
                {
                    "stable": True,
                    "path": rel_path,
                    "source_tree_fingerprint": source_tree_fingerprint,
                },
            )
        self._write_tracked_payload(
            ARTIFACT_FRESHNESS_REPORT_PATH,
            {
                "status": "pass",
                "source_tree_fingerprint": source_tree_fingerprint,
                "artifact_records": [
                    {
                        "path": rel_path,
                        "schema_validation_status": "pass",
                        "issues": [],
                    }
                    for rel_path in TARGET_TO_TRACKED_PATH.values()
                ],
            },
        )
        final_digest_map = {
            rel_path: hashlib.sha256((self.vault / rel_path).read_bytes()).hexdigest()
            for rel_path in TARGET_TO_TRACKED_PATH.values()
        }
        self._write_tracked_payload(
            DEFAULT_OUT,
            {"final_digest_map": final_digest_map, "status": "pass"},
        )

    def test_fixed_point_passes_when_digest_map_repeats(self) -> None:
        calls: list[str] = []

        def runner(
            argv: Sequence[str], cwd: Path, timeout_seconds: int, env: Mapping[str, str]
        ) -> dict[str, Any]:
            target = argv[1]
            calls.append(target)
            if target in TARGET_TO_TRACKED_PATH:
                rel_path = TARGET_TO_TRACKED_PATH[target]
                self._write_tracked_payload(
                    rel_path,
                    {
                        "target": target,
                        "stable": True,
                        "runtime_now": env["LLMWIKI_RUNTIME_UTC_NOW"],
                    },
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

        report = build_report(
            self.vault,
            max_iterations=5,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["converged"], True)
        self.assertEqual(report["converged_iteration"], 2)
        self.assertEqual(report["iteration_count"], 2)
        self.assertEqual(
            calls[:3],
            [
                "closure-registry-envelope",
                "manual-mutate-defect-registry",
                "release-risk-taxonomy-matrix",
            ],
        )
        self.assertEqual(calls.count("generated-artifact-index-body"), 2)
        self.assertIn("release-evidence-closeout-self-check", calls)
        duration_summary = report["duration_summary"]
        self.assertEqual(duration_summary["iteration_count"], 2)
        self.assertEqual(duration_summary["command_run_count"], len(calls))
        self.assertEqual(duration_summary["total_duration_ms"], len(calls))
        generated_index_cost = next(
            item
            for item in duration_summary["writer_costs"]
            if item["target"] == "generated-artifact-index-body"
        )
        self.assertEqual(generated_index_cost["run_count"], 2)
        self.assertEqual(generated_index_cost["skipped_after_first_iteration_count"], 0)
        expensive = duration_summary["expensive_prerequisites_once"]
        self.assertEqual(expensive["first_iteration_run_count"], 3)
        self.assertEqual(expensive["post_first_iteration_run_count"], 0)
        self.assertEqual(expensive["post_first_iteration_selected_count"], 0)
        self.assertTrue(expensive["skip_policy_effective"])
        self.assertEqual(
            sorted(report["final_digest_map"]),
            sorted(TARGET_TO_TRACKED_PATH.values()),
        )
        for rel_path, digest in report["final_digest_map"].items():
            actual = hashlib.sha256((self.vault / rel_path).read_bytes()).hexdigest()
            self.assertEqual(digest, actual)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_fixed_point_reruns_feedback_targets_after_downstream_changes(self) -> None:
        calls: list[str] = []
        downstream_version = 0

        def runner(
            argv: Sequence[str], cwd: Path, timeout_seconds: int, env: Mapping[str, str]
        ) -> dict[str, Any]:
            nonlocal downstream_version
            target = argv[1]
            calls.append(target)
            rel_path = TARGET_TO_TRACKED_PATH.get(target)
            if rel_path:
                if target in {
                    "generated-artifact-index-body",
                    "artifact-freshness",
                }:
                    payload = {
                        "target": target,
                        "observed_downstream_version": downstream_version,
                    }
                else:
                    downstream_version = 1
                    payload = {"target": target, "downstream_version": downstream_version}
                self._write_tracked_payload(rel_path, payload)
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
            max_iterations=5,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(report["status"], "pass")
        selected_by_iteration = {
            item["iteration_index"]: item["selected_targets"]
            for item in report["iterations"]
        }
        self.assertIn("generated-artifact-index-body", selected_by_iteration[2])
        self.assertIn("artifact-freshness", selected_by_iteration[2])
        self.assertGreaterEqual(calls.count("generated-artifact-index-body"), 2)
        self.assertEqual(
            json.loads(
                (self.vault / TARGET_TO_TRACKED_PATH["generated-artifact-index-body"])
                .read_text(encoding="utf-8")
            )["observed_downstream_version"],
            1,
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_dry_run_reports_affected_paths_and_recommended_targets(self) -> None:
        self._seed_tracked_artifacts_with_fixed_point_baseline()
        rel_path = "ops/reports/release-closeout-summary.json"
        payload = json.loads((self.vault / rel_path).read_text(encoding="utf-8"))
        payload["changed_after_check"] = True
        self._write_tracked_payload(rel_path, payload)

        report = build_dry_run_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["diagnostic_status"], "drift_detected")
        self.assertTrue(report["refresh_required"])
        self.assertEqual(report["affected_paths"], [rel_path])
        self.assertEqual(report["mutating_finalizer_target"], "release-closeout-fixed-point")
        self.assertEqual(
            report["recommended_targets"],
            [
                "release-closeout-summary-report",
                "learning-readiness-signoff-revalidation",
                "release-evidence-cohort",
                "release-evidence-dashboard-report",
                "release-lane-summary",
                "release-clean-blocker-ledger",
                "release-closeout-batch-manifest-promote",
                "release-evidence-closeout-self-check",
            ],
        )
        plan = report["closeout_plan"]
        self.assertEqual(plan["status"], "drift_detected")
        self.assertEqual(plan["recommended_target_count"], 8)
        self.assertEqual(
            plan["recommended_targets"][0]["target"],
            "release-closeout-summary-report",
        )
        self.assertIn(
            "ops/reports/release-closeout-summary.json",
            plan["recommended_targets"][0]["writes"],
        )
        self.assertRegex(
            plan["recommended_targets"][0]["expected_digest_to_settle"][
                "ops/reports/release-closeout-summary.json"
            ],
            r"^[a-f0-9]{64}$",
        )
        self.assertFalse(plan["recommended_targets"][0]["safe_to_run_in_dry_run"])
        self.assertEqual(validate_with_schema(report, load_schema(REPO_ROOT / DRY_RUN_SCHEMA_PATH)), [])

    def test_dry_run_writes_recommended_targets_text_for_ci_artifact(self) -> None:
        self._seed_tracked_artifacts_with_fixed_point_baseline()
        rel_path = "ops/reports/release-closeout-summary.json"
        payload = json.loads((self.vault / rel_path).read_text(encoding="utf-8"))
        payload["changed_after_check"] = True
        self._write_tracked_payload(rel_path, payload)
        report = build_dry_run_report(self.vault, context=fixed_context())

        path = write_dry_run_recommended_targets(
            self.vault,
            report,
            "tmp/recommended-targets.txt",
        )

        self.assertEqual(
            path.read_text(encoding="utf-8").splitlines(),
            report["recommended_targets"],
        )

    def test_dry_run_writes_closeout_plan_json_for_ci_artifact(self) -> None:
        self._seed_tracked_artifacts_with_fixed_point_baseline()
        rel_path = "ops/reports/release-closeout-summary.json"
        payload = json.loads((self.vault / rel_path).read_text(encoding="utf-8"))
        payload["changed_after_check"] = True
        self._write_tracked_payload(rel_path, payload)
        report = build_dry_run_report(self.vault, context=fixed_context())

        path = write_dry_run_plan(self.vault, report, "tmp/closeout-plan.json")

        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_kind"], "release_closeout_post_check_finalizer_plan")
        self.assertEqual(payload["status"], "drift_detected")
        self.assertEqual(payload["recommended_targets"], report["closeout_plan"]["recommended_targets"])

    def test_dry_run_writes_placeholder_when_no_recommended_targets(self) -> None:
        self._seed_tracked_artifacts_with_fixed_point_baseline()
        report = build_dry_run_report(self.vault, context=fixed_context())

        path = write_dry_run_recommended_targets(
            self.vault,
            report,
            "tmp/recommended-targets.txt",
        )

        self.assertEqual(path.read_text(encoding="utf-8"), "no recommended targets\n")

    def test_dry_run_can_fail_when_refresh_is_required(self) -> None:
        self._seed_tracked_artifacts_with_fixed_point_baseline()
        rel_path = "ops/reports/release-closeout-summary.json"
        payload = json.loads((self.vault / rel_path).read_text(encoding="utf-8"))
        payload["changed_after_check"] = True
        self._write_tracked_payload(rel_path, payload)

        status = fixed_point_main(
            [
                "--vault",
                str(self.vault),
                "--dry-run",
                "--out",
                "tmp/post-check.json",
                "--fail-on-refresh-required",
            ]
        )

        self.assertEqual(status, 1)

    def test_dry_run_passes_when_fixed_point_digest_map_and_source_tree_match(self) -> None:
        self._seed_tracked_artifacts_with_fixed_point_baseline()

        report = build_dry_run_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["diagnostic_status"], "settled")
        self.assertFalse(report["refresh_required"])
        self.assertEqual(report["affected_paths"], [])
        self.assertEqual(report["recommended_targets"], [])
        self.assertEqual(report["closeout_plan"]["recommended_targets"], [])
        self.assertEqual(validate_with_schema(report, load_schema(REPO_ROOT / DRY_RUN_SCHEMA_PATH)), [])

    def test_dry_run_distinguishes_missing_evidence_from_drift(self) -> None:
        report = build_dry_run_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["diagnostic_status"], "evidence_insufficient")
        self.assertTrue(report["refresh_required"])
        self.assertIn("fixed_point_report_unavailable", report["closeout_plan"]["evidence_gap_reasons"])
        self.assertEqual(report["closeout_plan"]["drift_reasons"], [])
        self.assertEqual(validate_with_schema(report, load_schema(REPO_ROOT / DRY_RUN_SCHEMA_PATH)), [])

    def test_fixed_point_reports_non_converged_when_budget_exhausted(self) -> None:
        call_count = 0

        def runner(
            argv: Sequence[str], cwd: Path, timeout_seconds: int, env: Mapping[str, str]
        ) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            target = argv[1]
            if target in TARGET_TO_TRACKED_PATH:
                rel_path = TARGET_TO_TRACKED_PATH[target]
                self._write_tracked_payload(
                    rel_path,
                    {
                        "target": target,
                        "call_count": call_count,
                    },
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

        report = build_report(
            self.vault,
            max_iterations=2,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(report["status"], "non_converged")
        self.assertEqual(report["converged"], False)
        self.assertEqual(report["converged_iteration"], 0)
        self.assertEqual(report["iteration_count"], 2)
        self.assertGreater(report["convergence_summary"]["changed_path_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_fixed_point_passes_runtime_clock_by_subprocess_env_without_global_override(
        self,
    ) -> None:
        os.environ["LLMWIKI_RUNTIME_UTC_NOW"] = "1999-01-01T00:00:00Z"
        observed: list[str] = []

        def runner(
            argv: Sequence[str], cwd: Path, timeout_seconds: int, env: Mapping[str, str]
        ) -> dict[str, Any]:
            target = argv[1]
            observed.append(env["LLMWIKI_RUNTIME_UTC_NOW"])
            if target in TARGET_TO_TRACKED_PATH:
                self._write_tracked_payload(
                    TARGET_TO_TRACKED_PATH[target],
                    {"target": target, "stable": True},
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

        try:
            report = build_report(
                self.vault,
                max_iterations=5,
                timeout_seconds=30,
                python_executable="python",
                context=fixed_context(),
                command_runner=runner,
            )
        finally:
            original = os.environ.pop("LLMWIKI_RUNTIME_UTC_NOW")

        self.assertEqual(original, "1999-01-01T00:00:00Z")
        self.assertEqual(report["status"], "pass")
        self.assertTrue(observed)
        self.assertEqual(set(observed), {"2026-05-09T12:00:00Z"})

    def test_post_promote_bootstrap_refreshes_fixed_point_schema_debt_in_artifact_freshness(
        self,
    ) -> None:
        self._write_artifact_freshness_fixed_point_debt(has_debt=True)
        calls: list[str] = []

        def runner(
            argv: Sequence[str], cwd: Path, timeout_seconds: int, env: Mapping[str, str]
        ) -> dict[str, Any]:
            target = argv[1]
            calls.append(target)
            if target == "artifact-freshness":
                self._write_artifact_freshness_fixed_point_debt(has_debt=False)
            if target in TARGET_TO_TRACKED_PATH:
                self._write_tracked_payload(
                    TARGET_TO_TRACKED_PATH[target],
                    {"target": target, "stable": True},
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

        result = bootstrap_post_promote_freshness(
            self.vault,
            max_bootstrap_passes=2,
            max_iterations=5,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["bootstrap_required"], True)
        self.assertEqual(len(result["passes"]), 1)
        self.assertTrue(result["initial_fixed_point_freshness_debt"]["has_schema_debt"])
        self.assertFalse(result["final_fixed_point_freshness_debt"]["has_schema_debt"])
        self.assertGreaterEqual(calls.count("artifact-freshness"), 1)
        fixed_point = json.loads((self.vault / DEFAULT_OUT).read_text(encoding="utf-8"))
        self.assertEqual(fixed_point["status"], "pass")
        self.assertEqual(
            validate_with_schema(fixed_point, load_schema(SCHEMA_PATH)), []
        )

    def test_post_promote_bootstrap_skips_when_artifact_freshness_has_no_fixed_point_schema_debt(
        self,
    ) -> None:
        self._write_artifact_freshness_fixed_point_debt(has_debt=False)
        calls: list[str] = []

        def runner(
            argv: Sequence[str], cwd: Path, timeout_seconds: int, env: Mapping[str, str]
        ) -> dict[str, Any]:
            calls.append(argv[1])
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

        result = bootstrap_post_promote_freshness(
            self.vault,
            max_bootstrap_passes=2,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=runner,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["bootstrap_required"], False)
        self.assertEqual(result["passes"], [])
        self.assertEqual(calls, [])
