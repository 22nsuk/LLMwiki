from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ops.scripts.core import generated_artifact_retention_clean as retention_clean
from ops.scripts.core.generated_artifact_retention_clean import (
    EMPTY_SHA256,
    build_report,
)

pytestmark = pytest.mark.report_contract


class GeneratedArtifactRetentionCleanTests(unittest.TestCase):
    def _vault(self, root: Path) -> Path:
        vault = root / "vault"
        vault.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
        (vault / ".gitignore").write_text(
            "\n".join(
                [
                    "build/",
                    "tmp/",
                    "ops/reports/",
                    "ops/operator/",
                    "runs/",
                    "raw/",
                    "wiki/",
                    "system/",
                    "external-reports/",
                    ".pytest_cache/",
                    ".ruff_cache/",
                    ".mypy_cache/",
                    "llm_wiki_vnext.egg-info/",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return vault

    def _write_freshness_items(
        self, vault: Path, items: list[dict[str, Any]]
    ) -> None:
        report_path = vault / "ops/reports/artifact-freshness-report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"run_log_placeholders": items}),
            encoding="utf-8",
        )

    def _write_freshness_placeholders(self, vault: Path, *paths: str) -> None:
        self._write_freshness_items(
            vault,
            [
                {
                    "path": path,
                    "artifact_role": "run_log_placeholder",
                    "size_bytes": 0,
                    "classification": "empty_run_command_log_placeholder",
                }
                for path in paths
            ],
        )

    def _write_run_artifact_fingerprint(
        self,
        vault: Path,
        owning_run: str,
        rel_path: str,
        *,
        size_bytes: int = 0,
        sha256: str = EMPTY_SHA256,
    ) -> None:
        fingerprint_path = vault / owning_run / "run-artifact-fingerprint.json"
        fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
        fingerprint_path.write_text(
            json.dumps(
                {
                    "artifacts": [
                        {
                            "path": rel_path,
                            "artifact_role": "command_stdout",
                            "schema": "",
                            "size_bytes": size_bytes,
                            "sha256": sha256,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def _write_promoted_run_telemetry(self, vault: Path, owning_run: str) -> None:
        telemetry_path = vault / owning_run / "run-telemetry.json"
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        telemetry_path.write_text(
            json.dumps({"decision": "PROMOTE", "finalized": True}),
            encoding="utf-8",
        )

    def _write_command_log_summary(
        self,
        vault: Path,
        *,
        owning_run: str,
        raw_rel_path: str,
        trace_rel_path: str,
        original_path: str | None = None,
    ) -> None:
        raw_path = vault / raw_rel_path
        trace_path = vault / trace_rel_path
        summary_path = vault / owning_run / "command-log-summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        raw_bytes = raw_path.read_bytes()
        trace_bytes = trace_path.read_bytes()
        summary_path.write_text(
            json.dumps(
                {
                    "streams": [
                        {
                            "original_path": original_path or raw_rel_path,
                            "original_size_bytes": len(raw_bytes),
                            "original_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                            "trace_path": trace_rel_path,
                            "trace_sha256": hashlib.sha256(trace_bytes).hexdigest(),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def _assert_single_retention_blocker(
        self,
        report: dict[str, Any],
        *,
        path: str,
        reason: str,
        blocking_reference: str | None = None,
    ) -> None:
        expected: dict[str, str] = {"path": path, "reason": reason}
        if blocking_reference is not None:
            expected["blocking_reference"] = blocking_reference
        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["retention_status"], "attention")
        self.assertEqual(report["gate_effect"], "advisory")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["retention_blockers"], [expected])

    def test_dry_run_reports_delete_candidates_without_removing_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text(
                "{}", encoding="utf-8"
            )
            (vault / "build/release").mkdir(parents=True)
            (vault / "build/release/release-run-manifest.json").write_text(
                "{}", encoding="utf-8"
            )
            (vault / "runs/goal-demo/state").mkdir(parents=True)
            (vault / "runs/goal-demo/state/local.json").write_text(
                "{}", encoding="utf-8"
            )

            report = build_report(vault)

            candidates = {item["path"]: item for item in report["delete_candidates"]}
            retained = {item["path"]: item for item in report["retained"]}
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["cleanup_status"], "dry_run")
            self.assertEqual(report["retention_status"], "pass")
            self.assertEqual(report["gate_effect"], "none")
            self.assertTrue(candidates["build/source-package-smoke"]["exists"])
            self.assertTrue(candidates["build/source-package-smoke"]["ignored"])
            self.assertEqual(report["deleted_paths"], [])
            self.assertIn("build/release", retained)
            self.assertTrue(retained["build/release"]["exists"])
            self.assertIn("runs/goal-demo/state", retained)
            self.assertTrue(
                (vault / "build/source-package-smoke/report.json").is_file()
            )

    def test_template_run_residue_is_allowlisted_without_unprotecting_runs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "runs/run-YYYYMMDD-slug").mkdir(parents=True)
            (vault / "runs/run-YYYYMMDD-slug/runtime-events.jsonl").write_text(
                "template\n", encoding="utf-8"
            )
            (vault / "runs/run-YYYYMMDD-mechanism-slug").mkdir(parents=True)
            (
                vault / "runs/run-YYYYMMDD-mechanism-slug/runtime-events.jsonl"
            ).write_text(
                "template\n",
                encoding="utf-8",
            )
            (vault / "runs/real-run/state").mkdir(parents=True)
            (vault / "runs/real-run/state/local.json").write_text(
                "{}", encoding="utf-8"
            )

            report = build_report(vault, apply=True)

            candidates = {item["path"]: item for item in report["delete_candidates"]}
            retained = {item["path"]: item for item in report["retained"]}
            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                candidates["runs/run-YYYYMMDD-slug"]["category"], "template_run_residue"
            )
            self.assertEqual(
                candidates["runs/run-YYYYMMDD-slug"]["files"], ["runtime-events.jsonl"]
            )
            self.assertEqual(
                candidates["runs/run-YYYYMMDD-mechanism-slug"]["category"],
                "template_run_residue",
            )
            self.assertIn("runs/run-YYYYMMDD-slug", report["deleted_paths"])
            self.assertIn("runs/run-YYYYMMDD-mechanism-slug", report["deleted_paths"])
            self.assertFalse((vault / "runs/run-YYYYMMDD-slug").exists())
            self.assertFalse((vault / "runs/run-YYYYMMDD-mechanism-slug").exists())
            self.assertIn("runs", retained)
            self.assertTrue((vault / "runs/real-run/state/local.json").is_file())

    def test_template_run_residue_with_run_artifacts_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "runs/run-YYYYMMDD-slug").mkdir(parents=True)
            (vault / "runs/run-YYYYMMDD-slug/runtime-events.jsonl").write_text(
                "template\n", encoding="utf-8"
            )
            (vault / "runs/run-YYYYMMDD-slug/promotion-report.json").write_text(
                "{}", encoding="utf-8"
            )

            report = build_report(vault, apply=True)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["deleted_paths"], [])
            self.assertEqual(
                report["blockers"],
                [
                    {
                        "path": "runs/run-YYYYMMDD-slug",
                        "reason": "template placeholder run directory contains non-runtime-event artifacts",
                    }
                ],
            )
            self.assertTrue(
                (vault / "runs/run-YYYYMMDD-slug/promotion-report.json").is_file()
            )

    def test_archived_run_log_placeholder_is_delete_candidate_without_unprotecting_runs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            archived_log = (
                vault / "runs/archive/run-archived/mutation-command.stdout.txt"
            )
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_run_artifact_fingerprint(
                vault,
                "runs/archive/run-archived",
                "runs/archive/run-archived/mutation-command.stdout.txt",
            )
            current_log = vault / "runs/run-current/mutation-command.stdout.txt"
            current_log.parent.mkdir(parents=True)
            current_log.write_text("", encoding="utf-8")
            non_empty_sibling = (
                vault / "runs/archive/run-archived/repo-health.stderr.txt"
            )
            non_empty_sibling.write_text("kept\n", encoding="utf-8")
            self._write_freshness_placeholders(
                vault,
                "runs/archive/run-archived/mutation-command.stdout.txt",
                "runs/run-current/mutation-command.stdout.txt",
            )

            report = build_report(vault, apply=True)

            candidates = {item["path"]: item for item in report["delete_candidates"]}
            retained = {item["path"]: item for item in report["retained"]}
            self.assertEqual(report["status"], "pass")
            self.assertIn(
                "runs/archive/run-archived/mutation-command.stdout.txt", candidates
            )
            self.assertEqual(
                candidates["runs/archive/run-archived/mutation-command.stdout.txt"][
                    "reason"
                ],
                "archived run zero-byte command log placeholder",
            )
            self.assertIn(
                "runs/archive/run-archived/mutation-command.stdout.txt",
                report["deleted_paths"],
            )
            self.assertFalse(archived_log.exists())
            self.assertTrue(non_empty_sibling.is_file())
            self.assertIn("runs/run-current/mutation-command.stdout.txt", retained)
            self.assertEqual(
                retained["runs/run-current/mutation-command.stdout.txt"]["reason"],
                "run is not archived or closed by rework-closures evidence",
            )
            self.assertTrue(current_log.is_file())
            self.assertIn("runs", retained)

    def test_promoted_archived_raw_run_log_deletes_only_with_summary_fingerprint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            raw_rel_path = "runs/archive/run-promoted/worker.stderr.txt"
            trace_rel_path = "runs/archive/run-promoted/worker.stderr-trace.txt"
            raw_log = vault / raw_rel_path
            trace_log = vault / trace_rel_path
            raw_log.parent.mkdir(parents=True)
            raw_log.write_text("executor failure details\n", encoding="utf-8")
            trace_log.write_text("executor failure details\n", encoding="utf-8")
            self._write_promoted_run_telemetry(vault, "runs/archive/run-promoted")
            self._write_command_log_summary(
                vault,
                owning_run="runs/archive/run-promoted",
                raw_rel_path=raw_rel_path,
                trace_rel_path=trace_rel_path,
                original_path="runs/run-promoted/worker.stderr.txt",
            )

            report = build_report(vault, apply=True)

            candidates = {item["path"]: item for item in report["delete_candidates"]}
            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                candidates[raw_rel_path]["reason"],
                "promoted archived/closed raw command log covered by command-log-summary",
            )
            self.assertIn(raw_rel_path, report["deleted_paths"])
            self.assertFalse(raw_log.exists())
            self.assertTrue(trace_log.is_file())
            self.assertTrue(
                (vault / "runs/archive/run-promoted/command-log-summary.json").is_file()
            )

    def test_promoted_archived_raw_run_log_missing_summary_is_retention_blocker(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            raw_rel_path = "runs/archive/run-missing-summary/worker.stderr.txt"
            raw_log = vault / raw_rel_path
            raw_log.parent.mkdir(parents=True)
            raw_log.write_text("executor failure details\n", encoding="utf-8")
            self._write_promoted_run_telemetry(vault, "runs/archive/run-missing-summary")

            report = build_report(vault)

            retained = {item["path"]: item for item in report["retained"]}
            self._assert_single_retention_blocker(
                report,
                path=raw_rel_path,
                reason="command log summary is missing or malformed",
                blocking_reference="runs/archive/run-missing-summary/command-log-summary.json",
            )
            self.assertFalse(retained[raw_rel_path]["delete_allowed"])
            self.assertTrue(raw_log.is_file())

    def test_promoted_archived_raw_run_log_retained_when_executor_report_still_references_raw(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            raw_rel_path = "runs/archive/run-promoted/worker.stderr.txt"
            trace_rel_path = "runs/archive/run-promoted/worker.stderr-trace.txt"
            raw_log = vault / raw_rel_path
            trace_log = vault / trace_rel_path
            raw_log.parent.mkdir(parents=True)
            raw_log.write_text("executor failure details\n", encoding="utf-8")
            trace_log.write_text("executor failure details\n", encoding="utf-8")
            self._write_promoted_run_telemetry(vault, "runs/archive/run-promoted")
            self._write_command_log_summary(
                vault,
                owning_run="runs/archive/run-promoted",
                raw_rel_path=raw_rel_path,
                trace_rel_path=trace_rel_path,
                original_path="runs/run-promoted/worker.stderr.txt",
            )
            (vault / "runs/archive/run-promoted/worker-executor-report.json").write_text(
                json.dumps({"artifacts": {"stderr": "runs/run-promoted/worker.stderr.txt"}}),
                encoding="utf-8",
            )

            report = build_report(vault)

            self._assert_single_retention_blocker(
                report,
                path=raw_rel_path,
                reason="executor report still references raw command log",
                blocking_reference="runs/archive/run-promoted/worker-executor-report.json",
            )
            self.assertTrue(raw_log.is_file())

    def test_current_evidence_reference_blocks_run_log_placeholder_cleanup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            archived_log = vault / "runs/archive/run-referenced/repo-health.stderr.txt"
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_freshness_placeholders(
                vault,
                "runs/archive/run-referenced/repo-health.stderr.txt",
            )
            (vault / "ops/reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops/reports/goal-run-status.json").write_text(
                '{"active_run": "runs/archive/run-referenced"}',
                encoding="utf-8",
            )

            report = build_report(vault, apply=True)

            retained = {item["path"]: item for item in report["retained"]}
            record = retained["runs/archive/run-referenced/repo-health.stderr.txt"]
            self.assertEqual(report["status"], "pass")
            self.assertNotIn(
                "runs/archive/run-referenced/repo-health.stderr.txt",
                report["deleted_paths"],
            )
            self.assertFalse(record["delete_allowed"])
            self.assertEqual(record["reason"], "current evidence references owning run")
            self.assertEqual(
                record["blocking_reference"], "ops/reports/goal-run-status.json"
            )
            self.assertTrue(archived_log.is_file())

    def test_closed_rework_run_log_placeholder_is_delete_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            closed_log = vault / "runs/run-closed/mutation-command.stderr.txt"
            closed_log.parent.mkdir(parents=True)
            closed_log.write_text("", encoding="utf-8")
            self._write_run_artifact_fingerprint(
                vault,
                "runs/run-closed",
                "runs/run-closed/mutation-command.stderr.txt",
            )
            self._write_freshness_placeholders(
                vault, "runs/run-closed/mutation-command.stderr.txt"
            )
            (vault / "ops/reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops/reports/rework-closures.json").write_text(
                '{"closures": [{"closed_run_ids": ["run-closed"]}]}',
                encoding="utf-8",
            )

            report = build_report(vault, apply=True)

            candidates = {item["path"]: item for item in report["delete_candidates"]}
            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                candidates["runs/run-closed/mutation-command.stderr.txt"]["reason"],
                "closed rework run zero-byte command log placeholder",
            )
            self.assertIn(
                "runs/run-closed/mutation-command.stderr.txt", report["deleted_paths"]
            )
            self.assertFalse(closed_log.exists())

    def test_open_run_log_placeholder_is_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            open_log = vault / "runs/run-open/repo-health.stdout.txt"
            open_log.parent.mkdir(parents=True)
            open_log.write_text("", encoding="utf-8")
            self._write_freshness_placeholders(
                vault, "runs/run-open/repo-health.stdout.txt"
            )

            report = build_report(vault, apply=True)

            retained = {item["path"]: item for item in report["retained"]}
            record = retained["runs/run-open/repo-health.stdout.txt"]
            self.assertEqual(report["status"], "pass")
            self.assertNotIn(
                "runs/run-open/repo-health.stdout.txt", report["deleted_paths"]
            )
            self.assertFalse(record["delete_allowed"])
            self.assertEqual(record["owning_run"], "runs/run-open")
            self.assertEqual(
                record["reason"],
                "run is not archived or closed by rework-closures evidence",
            )
            self.assertTrue(open_log.is_file())

    def test_run_log_placeholder_blocks_without_freshness_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            archived_log = (
                vault / "runs/archive/run-no-freshness/repo-health.stdout.txt"
            )
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")

            report = build_report(vault, apply=True)

            self._assert_single_retention_blocker(
                report,
                path="runs/archive/run-no-freshness/repo-health.stdout.txt",
                reason="artifact freshness report is missing",
                blocking_reference="ops/reports/artifact-freshness-report.json",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertTrue(archived_log.is_file())

    def test_run_log_placeholder_blocks_mismatched_freshness_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            rel_path = "runs/archive/run-wrong-freshness/repo-health.stdout.txt"
            archived_log = vault / rel_path
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_run_artifact_fingerprint(
                vault, "runs/archive/run-wrong-freshness", rel_path
            )
            self._write_freshness_items(
                vault,
                [
                    {
                        "path": rel_path,
                        "artifact_role": "run_log_placeholder",
                        "size_bytes": 0,
                        "classification": "not_a_run_command_log_placeholder",
                    }
                ],
            )

            report = build_report(vault, apply=True)

            self._assert_single_retention_blocker(
                report,
                path=rel_path,
                reason="artifact freshness report does not list this zero-byte run log placeholder",
                blocking_reference="ops/reports/artifact-freshness-report.json",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertTrue(archived_log.is_file())

    def test_run_log_placeholder_blocks_symlink_command_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            rel_path = "runs/archive/run-symlink/repo-health.stdout.txt"
            archived_log = vault / rel_path
            archived_log.parent.mkdir(parents=True)
            (archived_log.parent / "target.txt").write_text("", encoding="utf-8")
            archived_log.symlink_to("target.txt")

            report = build_report(vault, apply=True)

            self._assert_single_retention_blocker(
                report,
                path=rel_path,
                reason="run command log path is a symlink",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertTrue(archived_log.is_symlink())

    def test_run_log_placeholder_blocks_unignored_command_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / ".gitignore").write_text("", encoding="utf-8")
            archived_log = vault / "runs/archive/run-unignored/repo-health.stdout.txt"
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_freshness_placeholders(
                vault, "runs/archive/run-unignored/repo-health.stdout.txt"
            )

            report = build_report(vault, apply=True)

            self._assert_single_retention_blocker(
                report,
                path="runs/archive/run-unignored/repo-health.stdout.txt",
                reason="zero-byte run command log is not ignored by git",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertTrue(archived_log.is_file())

    def test_run_log_placeholder_blocks_fingerprint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            archived_log = (
                vault / "runs/archive/run-fingerprint-drift/mutation-command.stderr.txt"
            )
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            rel_path = "runs/archive/run-fingerprint-drift/mutation-command.stderr.txt"
            self._write_freshness_placeholders(vault, rel_path)
            self._write_run_artifact_fingerprint(
                vault,
                "runs/archive/run-fingerprint-drift",
                rel_path,
                size_bytes=4,
                sha256="0" * 64,
            )

            report = build_report(vault)

            self._assert_single_retention_blocker(
                report,
                path=rel_path,
                reason="run artifact fingerprint records non-empty command log content",
                blocking_reference="runs/archive/run-fingerprint-drift/run-artifact-fingerprint.json",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertTrue(archived_log.is_file())

    def test_run_log_placeholder_blocks_missing_fingerprint_for_delete_scope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            rel_path = "runs/archive/run-missing-fingerprint/repo-health.stdout.txt"
            archived_log = vault / rel_path
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_freshness_placeholders(vault, rel_path)

            report = build_report(vault, apply=True)

            retained = {item["path"]: item for item in report["retained"]}
            record = retained[rel_path]
            self._assert_single_retention_blocker(
                report,
                path=rel_path,
                reason="run artifact fingerprint is missing or malformed",
                blocking_reference="runs/archive/run-missing-fingerprint/run-artifact-fingerprint.json",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertFalse(record["delete_allowed"])
            self.assertEqual(record["fingerprint_status"], "missing")
            self.assertEqual(
                record["blocking_reference"],
                "runs/archive/run-missing-fingerprint/run-artifact-fingerprint.json",
            )
            self.assertTrue(archived_log.is_file())

    def test_run_log_placeholder_blocks_unrecorded_fingerprint_path_for_delete_scope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            rel_path = "runs/archive/run-path-not-recorded/repo-health.stderr.txt"
            archived_log = vault / rel_path
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_freshness_placeholders(vault, rel_path)
            self._write_run_artifact_fingerprint(
                vault,
                "runs/archive/run-path-not-recorded",
                "runs/archive/run-path-not-recorded/mutation-command.stderr.txt",
            )

            report = build_report(vault, apply=True)

            retained = {item["path"]: item for item in report["retained"]}
            record = retained[rel_path]
            self._assert_single_retention_blocker(
                report,
                path=rel_path,
                reason="run artifact fingerprint is missing or malformed",
                blocking_reference="runs/archive/run-path-not-recorded/run-artifact-fingerprint.json",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertFalse(record["delete_allowed"])
            self.assertEqual(record["fingerprint_status"], "path_not_recorded")
            self.assertEqual(
                record["blocking_reference"],
                "runs/archive/run-path-not-recorded/run-artifact-fingerprint.json",
            )
            self.assertTrue(archived_log.is_file())

    def test_apply_blocks_run_log_that_changes_before_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            rel_path = "runs/archive/run-race/repo-health.stdout.txt"
            archived_log = vault / rel_path
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_run_artifact_fingerprint(vault, "runs/archive/run-race", rel_path)
            self._write_freshness_placeholders(vault, rel_path)

            def changed_before_delete(path: Path) -> bool:
                path.write_text("changed\n", encoding="utf-8")
                return False

            with patch.object(
                retention_clean,
                "_empty_regular_run_log_file",
                side_effect=changed_before_delete,
            ):
                report = build_report(vault, apply=True)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["cleanup_status"], "blocked")
            self.assertEqual(report["retention_status"], "pass")
            self.assertEqual(report["gate_effect"], "blocks_execution")
            self.assertEqual(
                report["blockers"],
                [{"path": rel_path, "reason": "run command log changed before deletion"}],
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertEqual(archived_log.read_text(encoding="utf-8"), "changed\n")

    def test_run_log_placeholder_blocks_live_goal_runtime_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            archived_log = (
                vault / "runs/archive/run-active-lock/mutation-command.stdout.txt"
            )
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            rel_path = "runs/archive/run-active-lock/mutation-command.stdout.txt"
            self._write_freshness_placeholders(vault, rel_path)
            lock_path = vault / "build/goal-runs/goal-runtime.lock.json"
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text(
                json.dumps({"pid": os.getpid(), "run_id": "run-active-lock"}),
                encoding="utf-8",
            )

            report = build_report(vault)

            self._assert_single_retention_blocker(
                report,
                path=rel_path,
                reason="goal runtime lock blocks run-log cleanup",
                blocking_reference="build/goal-runs/goal-runtime.lock.json",
            )
            self.assertEqual(report["deleted_paths"], [])
            self.assertTrue(archived_log.is_file())

    def test_apply_deletes_allowed_residue_while_retaining_blocked_run_logs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text(
                "{}", encoding="utf-8"
            )
            rel_path = "runs/archive/run-missing-fingerprint/repo-health.stdout.txt"
            archived_log = vault / rel_path
            archived_log.parent.mkdir(parents=True)
            archived_log.write_text("", encoding="utf-8")
            self._write_freshness_placeholders(vault, rel_path)

            report = build_report(vault, apply=True)

            self._assert_single_retention_blocker(
                report,
                path=rel_path,
                reason="run artifact fingerprint is missing or malformed",
                blocking_reference="runs/archive/run-missing-fingerprint/run-artifact-fingerprint.json",
            )
            self.assertIn("build/source-package-smoke", report["deleted_paths"])
            self.assertFalse((vault / "build/source-package-smoke").exists())
            self.assertTrue(archived_log.is_file())

    def test_apply_deletes_only_ignored_allowlist_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text(
                "{}", encoding="utf-8"
            )
            (vault / "build/release").mkdir(parents=True)
            (vault / "build/release/release-run-manifest.json").write_text(
                "{}", encoding="utf-8"
            )
            (vault / "raw").mkdir()
            (vault / "raw/private.md").write_text("private", encoding="utf-8")

            report = build_report(vault, apply=True)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["cleanup_status"], "applied")
            self.assertEqual(report["retention_status"], "pass")
            self.assertEqual(report["gate_effect"], "none")
            self.assertIn("build/source-package-smoke", report["deleted_paths"])
            self.assertFalse((vault / "build/source-package-smoke").exists())
            self.assertTrue(
                (vault / "build/release/release-run-manifest.json").is_file()
            )
            self.assertTrue((vault / "raw/private.md").is_file())

    def test_apply_blocks_all_deletion_when_goal_runtime_lock_is_active(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text(
                "{}", encoding="utf-8"
            )
            lock_path = vault / "build/goal-runs/goal-runtime.lock.json"
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text(
                json.dumps({"pid": os.getpid(), "run_id": "run-active-lock"}),
                encoding="utf-8",
            )

            report = build_report(vault, apply=True)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["cleanup_status"], "blocked")
            self.assertEqual(report["retention_status"], "pass")
            self.assertEqual(report["gate_effect"], "blocks_execution")
            self.assertEqual(report["deleted_paths"], [])
            self.assertEqual(
                report["blockers"][0]["path"],
                "build/goal-runs/goal-runtime.lock.json",
            )
            self.assertIn("active runner_process", report["blockers"][0]["reason"])
            self.assertTrue(
                (vault / "build/source-package-smoke/report.json").is_file()
            )

    def test_apply_blocks_non_ignored_allowlist_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._vault(Path(temp_dir))
            (vault / ".gitignore").write_text("", encoding="utf-8")
            (vault / "build/source-package-smoke").mkdir(parents=True)
            (vault / "build/source-package-smoke/report.json").write_text(
                "{}", encoding="utf-8"
            )

            report = build_report(vault, apply=True)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["cleanup_status"], "blocked")
            self.assertEqual(report["retention_status"], "pass")
            self.assertEqual(report["gate_effect"], "blocks_execution")
            self.assertEqual(report["deleted_paths"], [])
            self.assertEqual(
                report["blockers"],
                [
                    {
                        "path": "build/source-package-smoke",
                        "reason": "delete candidate exists but is not ignored by git",
                    }
                ],
            )
            self.assertTrue(
                (vault / "build/source-package-smoke/report.json").is_file()
            )


if __name__ == "__main__":
    unittest.main()
