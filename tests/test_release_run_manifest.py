from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_remote_sync_governance import (
    remote_sync_governance_record,
    workflow_attachment_result,
)
from ops.scripts.release.release_run_manifest import (
    build_manifest,
    distribution_zip_path_from_manifest,
    main,
    write_manifest,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-run-manifest.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.UTC),
    )


class ReleaseRunManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy("ops/schemas/release-run-manifest.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy(self, rel_path: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_zip(self) -> dict[str, object]:
        path = self.vault / "build" / "release" / "LLMwiki-source.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("LLMwiki/README.md", "hello\n")
        return {
            "path": "build/release/LLMwiki-source.zip",
            "exists": True,
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _write_run_inputs(self) -> None:
        source_zip = self._write_zip()
        self._write_json(
            "build/source-package-smoke/source-package-smoke.json",
            {
                "artifact_kind": "source_package_smoke",
                "status": "pass",
                "input_fingerprints": {"source_zip": source_zip["sha256"]},
                "source_zip": source_zip,
            },
        )

    def _patch_clean_repo(self, fingerprint: str) -> Any:
        return patch.multiple(
            "ops.scripts.release.release_run_manifest",
            release_source_tree_fingerprint=lambda _vault: fingerprint,
            git_commit=lambda _vault: "abc123",
            git_clean=lambda _vault: True,
            remote_sync=lambda _vault: {"status": "pass", "upstream": "origin/main", "ahead": 0, "behind": 0},
            ignored_tracked_file_count=lambda _vault: 0,
        )

    def test_manifest_passes_from_run_inputs_and_ignores_diagnostic_reports(self) -> None:
        self._write_run_inputs()
        self._write_json(
            "ops/reports/release-smoke-report.json",
            {
                "artifact_kind": "release_smoke_report",
                "status": "fail",
                "source_tree_fingerprint": "stale",
            },
        )
        self._write_json(
            "build/release/release-closeout-batch-manifest.json",
            {"artifact_kind": "release_closeout_batch_manifest", "status": "fail"},
        )
        self._write_json(
            "build/release/operator-release-summary.json",
            {"artifact_kind": "operator_release_summary", "status": "attention"},
        )

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                steps=[
                    {
                        "name": "release-test-current",
                        "status": "pass",
                        "summary_mode": "executed",
                        "command": ["make", "release-test-current"],
                        "returncode": 0,
                        "duration_ms": 1,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    }
                ],
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["git_commit"], "abc123")
        self.assertEqual(manifest["source_tree_fingerprint"], "fp-current")
        self.assertEqual(manifest["failures"], [])
        self.assertEqual(manifest["schema_version"], 5)
        self.assertIn("release_authority_status", manifest)
        self.assertIn("machine_release_allowed", manifest)
        self.assertIn("step_duration_summary", manifest)
        self.assertEqual(manifest["step_duration_summary"]["total_duration_ms"], 1)
        self.assertEqual(manifest["step_duration_summary"]["slowest_step"]["name"], "release-test-current")
        self.assertEqual(manifest["steps"][0]["summary_mode"], "executed")
        self.assertNotIn("sealed", manifest)
        self.assertNotIn("ops_reports_reference", manifest)
        self.assertNotIn("payload_status", json.dumps(manifest, ensure_ascii=False))
        self.assertEqual(
            sorted(manifest["input_fingerprints"]),
            [
                "closeout_summary",
                "distribution_zip",
                "source_package_smoke",
                "source_package_smoke_source_zip",
            ],
        )
        self.assertEqual(
            manifest["input_fingerprints"]["distribution_zip"],
            manifest["source_package_smoke"]["source_zip_sha256"],
        )
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(write_manifest(self.vault, manifest, "build/release/release-run-manifest.json").exists())

    def test_step_failure_is_release_run_verdict(self) -> None:
        self._write_run_inputs()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                steps=[
                    {
                        "name": "release-public-current",
                        "status": "fail",
                        "summary_mode": "executed",
                        "command": ["make", "release-public-current"],
                        "returncode": 1,
                        "duration_ms": 1,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    }
                ],
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("step_failed:release-public-current", manifest["failures"])
        self.assertEqual(manifest["step_duration_summary"]["failed_step_count"], 1)
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_manifest_summarizes_step_duration_comparison_groups(self) -> None:
        self._write_run_inputs()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                steps=[
                    {
                        "name": "release-test-current",
                        "status": "pass",
                        "summary_mode": "executed",
                        "command": ["make", "release-test-current"],
                        "returncode": 0,
                        "duration_ms": 100,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    },
                    {
                        "name": "release-public-current",
                        "status": "pass",
                        "summary_mode": "reused",
                        "command": ["make", "release-public-current"],
                        "returncode": 0,
                        "duration_ms": 300,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    },
                    {
                        "name": "release-smoke-full-reuse",
                        "status": "pass",
                        "summary_mode": "reused",
                        "command": ["make", "release-smoke-full-reuse"],
                        "returncode": 0,
                        "duration_ms": 50,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    },
                    {
                        "name": "release-source-package-check",
                        "status": "pass",
                        "summary_mode": "executed",
                        "command": ["make", "release-source-package-check"],
                        "returncode": 0,
                        "duration_ms": 450,
                        "source_tree_fingerprint_before": "fp-current",
                        "source_tree_fingerprint_after": "fp-current",
                    },
                ],
                context=fixed_context(),
            )

        summary = manifest["step_duration_summary"]
        self.assertEqual(summary["total_duration_ms"], 900)
        self.assertEqual(summary["step_count"], 4)
        self.assertEqual(summary["passed_step_count"], 4)
        self.assertEqual(summary["failed_step_count"], 0)
        self.assertEqual(summary["slowest_step"]["name"], "release-source-package-check")
        self.assertEqual(summary["steps_by_duration_desc"][0]["name"], "release-source-package-check")
        self.assertEqual(summary["comparison_groups"]["public"]["total_duration_ms"], 300)
        self.assertEqual(summary["comparison_groups"]["source_package"]["total_duration_ms"], 450)
        self.assertEqual(summary["comparison_groups"]["source_package"]["slowest_step_name"], "release-source-package-check")
        self.assertGreater(
            summary["comparison_groups"]["source_package"]["share_of_total"],
            summary["comparison_groups"]["public"]["share_of_total"],
        )
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_distribution_zip_path_can_be_read_from_manifest_for_release_reuse(self) -> None:
        self._write_run_inputs()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )
        write_manifest(self.vault, manifest, "build/release/release-run-manifest.json")

        self.assertEqual(
            distribution_zip_path_from_manifest(
                self.vault,
                "build/release/release-run-manifest.json",
            ),
            "build/release/LLMwiki-source.zip",
        )

    def test_distribution_zip_path_rejects_invalid_manifest_path(self) -> None:
        self._write_run_inputs()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )
        manifest["distribution_zip"]["path"] = "build/release/LLMwiki-source.zip\"; touch pwned #"
        self._write_json("build/release/release-run-manifest.json", manifest)

        self.assertEqual(
            distribution_zip_path_from_manifest(
                self.vault,
                "build/release/release-run-manifest.json",
            ),
            "",
        )

    def test_manifest_fails_when_smoked_source_zip_does_not_match_distribution(self) -> None:
        self._write_run_inputs()
        smoke_path = self.vault / "build/source-package-smoke/source-package-smoke.json"
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        smoke["source_zip"]["sha256"] = "0" * 64
        smoke["input_fingerprints"]["source_zip"] = "0" * 64
        smoke_path.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("source_package_smoke_source_zip_mismatch", manifest["failures"])
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_manifest_requires_smoke_source_zip_identity_not_input_fingerprint_only(self) -> None:
        self._write_run_inputs()
        smoke_path = self.vault / "build/source-package-smoke/source-package-smoke.json"
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        smoke.pop("source_zip")
        smoke_path.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn(
            "source_package_smoke_source_zip_fingerprint_missing",
            manifest["failures"],
        )
        self.assertEqual(manifest["source_package_smoke"]["source_zip_sha256"], "")
        self.assertEqual(
            manifest["input_fingerprints"]["source_package_smoke_source_zip"],
            "",
        )
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_manifest_records_malformed_smoke_source_zip_fingerprint_as_failure(self) -> None:
        self._write_run_inputs()
        smoke_path = self.vault / "build/source-package-smoke/source-package-smoke.json"
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        smoke["source_zip"]["sha256"] = "not-a-sha"
        smoke["input_fingerprints"]["source_zip"] = "not-a-sha"
        smoke_path.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn(
            "source_package_smoke_source_zip_fingerprint_invalid",
            manifest["failures"],
        )
        self.assertEqual(manifest["source_package_smoke"]["source_zip_sha256"], "")
        self.assertEqual(
            manifest["input_fingerprints"]["source_package_smoke_source_zip"],
            "",
        )
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(
            write_manifest(
                self.vault,
                manifest,
                "build/release/release-run-manifest.json",
            ).exists()
        )

    def test_manifest_fails_when_smoke_source_zip_fingerprints_disagree(self) -> None:
        self._write_run_inputs()
        smoke_path = self.vault / "build/source-package-smoke/source-package-smoke.json"
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        smoke["input_fingerprints"]["source_zip"] = "0" * 64
        smoke_path.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn(
            "source_package_smoke_source_zip_fingerprint_mismatch",
            manifest["failures"],
        )
        self.assertNotIn("_source_zip_input_sha256", manifest["source_package_smoke"])
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_manifest_records_missing_smoke_source_zip_fingerprint_as_failure(self) -> None:
        self._write_run_inputs()
        smoke_path = self.vault / "build/source-package-smoke/source-package-smoke.json"
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        smoke.pop("source_zip")
        smoke["input_fingerprints"].pop("source_zip")
        smoke_path.write_text(json.dumps(smoke, ensure_ascii=False, indent=2), encoding="utf-8")

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn(
            "source_package_smoke_source_zip_fingerprint_missing",
            manifest["failures"],
        )
        self.assertEqual(manifest["source_package_smoke"]["source_zip_sha256"], "")
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(
            write_manifest(
                self.vault,
                manifest,
                "build/release/release-run-manifest.json",
            ).exists()
        )

    def test_manifest_records_rejected_distribution_zip_path_as_schema_valid_failure(self) -> None:
        self._write_run_inputs()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                distribution_zip="/tmp/not-in-vault.zip",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("distribution_zip_path_not_vault_relative", manifest["failures"])
        self.assertEqual(manifest["distribution_zip"]["path"], "")
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])
        self.assertTrue(
            write_manifest(
                self.vault,
                manifest,
                "build/release/release-run-manifest.json",
            ).exists()
        )

    def test_manifest_fails_on_source_fingerprint_drift(self) -> None:
        self._write_run_inputs()

        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-old",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertIn("source_tree_fingerprint_drift", manifest["failures"])

    def test_check_mode_prints_fingerprint_drift_remediation_context(self) -> None:
        self._write_run_inputs()
        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-old",
                context=fixed_context(),
            )
        manifest["generated_at"] = "2026-06-03T12:00:00Z"
        write_manifest(self.vault, manifest, "build/release/release-run-manifest.json")
        original = (self.vault / "build/release/release-run-manifest.json").read_text(
            encoding="utf-8"
        )

        stdout = io.StringIO()
        with patch.multiple(
            "ops.scripts.release.release_run_manifest",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            release_source_tree_change_sample=lambda _vault, *, generated_at: {
                "changed_after_generated_at_count": 2,
                "changed_after_generated_at_path_limit": 10,
                "changed_after_generated_at": [
                    {"path": "docs/release.md", "mtime": "2026-06-03T12:01:00Z"},
                    {"path": "ops/scripts/release/release_run_manifest.py", "mtime": "2026-06-03T12:02:00Z"},
                ],
            },
            git_commit=lambda _vault: "abc123",
            git_clean=lambda _vault: True,
            remote_sync=lambda _vault: {
                "status": "pass",
                "upstream": "origin/main",
                "ahead": 0,
                "behind": 0,
            },
            ignored_tracked_file_count=lambda _vault: 0,
        ), redirect_stdout(stdout):
            result = main(["--vault", str(self.vault), "--check"])

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("release_run_manifest_status=fail", output)
        self.assertIn("failures=source_tree_fingerprint_drift", output)
        self.assertIn("source_tree_fingerprint_drift=expected:fp-old;current:fp-current", output)
        self.assertIn("minimal_remediation_target=release-run-ready", output)
        self.assertIn("changed_after_generated_at_count=2", output)
        self.assertIn("docs/release.md@2026-06-03T12:01:00Z", output)
        self.assertIn(
            "ops/scripts/release/release_run_manifest.py@2026-06-03T12:02:00Z",
            output,
        )
        self.assertEqual(
            (self.vault / "build/release/release-run-manifest.json").read_text(encoding="utf-8"),
            original,
        )

    def test_check_mode_reports_input_fingerprint_drift_without_overwriting_manifest(self) -> None:
        self._write_run_inputs()
        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )
        manifest["input_fingerprints"]["distribution_zip"] = "0" * 64
        self._write_json("build/release/release-run-manifest.json", manifest)
        original = (self.vault / "build/release/release-run-manifest.json").read_text(
            encoding="utf-8"
        )

        stdout = io.StringIO()
        with self._patch_clean_repo("fp-current"), redirect_stdout(stdout):
            result = main(["--vault", str(self.vault), "--check"])

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("failures=release_run_manifest_input_fingerprint_drift", output)
        self.assertIn("input_fingerprint_drift=expected:", output)
        self.assertEqual(
            (self.vault / "build/release/release-run-manifest.json").read_text(encoding="utf-8"),
            original,
        )

    def test_check_mode_rejects_persisted_failure_without_overwriting_manifest(self) -> None:
        self._write_run_inputs()
        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )
        manifest["status"] = "fail"
        manifest["failures"] = ["git_worktree_dirty"]
        write_manifest(self.vault, manifest, "build/release/release-run-manifest.json")
        original = (self.vault / "build/release/release-run-manifest.json").read_text(
            encoding="utf-8"
        )

        stdout = io.StringIO()
        with self._patch_clean_repo("fp-current"), redirect_stdout(stdout):
            result = main(["--vault", str(self.vault), "--check"])

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("release_run_manifest_persisted_not_pass", output)
        self.assertIn("persisted_release_run_manifest_status=fail", output)
        self.assertIn(
            "persisted_release_run_manifest_failures=git_worktree_dirty",
            output,
        )
        self.assertEqual(
            (self.vault / "build/release/release-run-manifest.json").read_text(encoding="utf-8"),
            original,
        )

    def test_check_mode_reports_closeout_summary_drift_without_overwriting_manifest(self) -> None:
        self._write_run_inputs()
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {"machine_release_allowed": False, "note": "old"},
        )
        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )
        write_manifest(self.vault, manifest, "build/release/release-run-manifest.json")
        original = (self.vault / "build/release/release-run-manifest.json").read_text(
            encoding="utf-8"
        )
        self._write_json(
            "ops/reports/release-closeout-summary.json",
            {"machine_release_allowed": True, "note": "new"},
        )

        stdout = io.StringIO()
        with self._patch_clean_repo("fp-current"), redirect_stdout(stdout):
            result = main(["--vault", str(self.vault), "--check"])

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("release_run_manifest_input_fingerprint_drift", output)
        self.assertIn("closeout_summary", output)
        self.assertEqual(
            (self.vault / "build/release/release-run-manifest.json").read_text(encoding="utf-8"),
            original,
        )

    def test_check_mode_reports_source_revision_drift_without_overwriting_manifest(self) -> None:
        self._write_run_inputs()
        with self._patch_clean_repo("fp-current"):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )
        manifest["source_revision"] = "old-commit"
        manifest["git_commit"] = "old-commit"
        write_manifest(self.vault, manifest, "build/release/release-run-manifest.json")
        original = (self.vault / "build/release/release-run-manifest.json").read_text(
            encoding="utf-8"
        )

        stdout = io.StringIO()
        with self._patch_clean_repo("fp-current"), redirect_stdout(stdout):
            result = main(["--vault", str(self.vault), "--check"])

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("release_run_manifest_source_revision_drift", output)
        self.assertIn("release_run_manifest_git_commit_drift", output)
        self.assertIn("source_revision_drift=expected:old-commit;current:abc123", output)
        self.assertIn("git_commit_drift=expected:old-commit;current:abc123", output)
        self.assertEqual(
            (self.vault / "build/release/release-run-manifest.json").read_text(encoding="utf-8"),
            original,
        )

    def test_remote_ahead_is_diagnostic_not_run_ready_blocker(self) -> None:
        self._write_run_inputs()

        with patch.multiple(
            "ops.scripts.release.release_run_manifest",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
            git_clean=lambda _vault: True,
            remote_sync=lambda _vault: {
                "status": "fail",
                "upstream": "origin/main",
                "ahead": 1,
                "behind": 0,
            },
            ignored_tracked_file_count=lambda _vault: 0,
        ):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["remote_sync"]["ahead"], 1)
        self.assertNotIn("remote_not_in_sync", manifest["failures"])

    def test_workflow_attachment_error_is_recorded_without_blocking_sync(self) -> None:
        self._write_run_inputs()
        remote = remote_sync_governance_record(
            {"status": "pass", "upstream": "origin/feature", "ahead": 0, "behind": 0},
            workflow_attachment=workflow_attachment_result(
                workflow_run_attached=False,
                combined_status_check_attached=False,
                error_kind="service",
                error_message="GitHub Actions lookup failed",
            ),
        )

        with patch.multiple(
            "ops.scripts.release.release_run_manifest",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
            git_clean=lambda _vault: True,
            remote_sync=lambda _vault: remote,
            ignored_tracked_file_count=lambda _vault: 0,
        ):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        attachment = manifest["remote_sync"]["workflow_attachment"]
        self.assertEqual(manifest["status"], "pass")
        self.assertEqual(manifest["remote_sync"]["status"], "pass")
        self.assertEqual(attachment["status"], "failed")
        self.assertTrue(attachment["sync_continues"])
        self.assertEqual(attachment["workflow_attachment_error"]["kind"], "service")
        self.assertNotIn("workflow_attachment_error", manifest["failures"])
        self.assertEqual(validate_with_schema(manifest, load_schema(SCHEMA_PATH)), [])

    def test_manifest_fails_when_ignored_tracked_files_are_present(self) -> None:
        self._write_run_inputs()

        with patch.multiple(
            "ops.scripts.release.release_run_manifest",
            release_source_tree_fingerprint=lambda _vault: "fp-current",
            git_commit=lambda _vault: "abc123",
            git_clean=lambda _vault: True,
            remote_sync=lambda _vault: {
                "status": "pass",
                "upstream": "origin/main",
                "ahead": 0,
                "behind": 0,
            },
            ignored_tracked_file_count=lambda _vault: 2,
        ):
            manifest = build_manifest(
                self.vault,
                expected_source_tree_fingerprint="fp-current",
                context=fixed_context(),
            )

        self.assertEqual(manifest["status"], "fail")
        self.assertEqual(manifest["ignored_tracked_file_count"], 2)
        self.assertIn("ignored_tracked_files_present", manifest["failures"])


if __name__ == "__main__":
    unittest.main()
