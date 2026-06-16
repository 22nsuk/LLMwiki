from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.archive_execution_manifest import (
    APPLY_CONFIRMATION,
    ROLLBACK_CONFIRMATION,
    build_report,
    main,
    write_report,
)
from ops.scripts.generated_artifact_index import (
    build_report as build_index_report,
    write_report as write_index_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "archive-execution-manifest.schema.json"
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 29, 10, 0, tzinfo=dt.UTC),
    )


class ArchiveExecutionManifestTests(unittest.TestCase):
    def test_dry_run_records_planned_moves_without_moving_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            report_path = vault / "ops" / "reports" / "eval-initial-2026-04-12.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("{}", encoding="utf-8")
            write_index_report(vault, build_index_report(vault, context=fixed_context()))

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report)

            self.assertTrue(report_path.exists())
            self.assertEqual(destination, vault / "tmp" / "archive-execution-manifest.json")
            self.assertEqual(report["mode"], "dry_run")
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["planned_move_count"], 1)
            self.assertEqual(report["summary"]["deferred_move_count"], 0)
            self.assertEqual(report["moves"][0]["execution_status"], "planned")
            self.assertEqual(report["moves"][0]["rollback_available"], False)
            self.assertEqual(validate_with_schema(report, load_schema(MANIFEST_SCHEMA_PATH)), [])
            self.assertEqual(validate_with_schema(report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_fail_on_attention_exits_nonzero_when_archive_candidates_remain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            report_path = vault / "ops" / "reports" / "eval-initial-2026-04-12.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("{}", encoding="utf-8")
            write_index_report(vault, build_index_report(vault, context=fixed_context()))

            exit_code = main(
                [
                    "--vault",
                    str(vault),
                    "--out",
                    "tmp/archive-execution-manifest-check.json",
                    "--fail-on-attention",
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertTrue(report_path.exists())

    def test_applied_manifest_moves_file_and_records_rollback_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            source = vault / "ops" / "reports" / "eval-initial-2026-04-12.json"
            destination = vault / "ops" / "reports" / "archive" / source.name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("{}", encoding="utf-8")
            write_index_report(vault, build_index_report(vault, context=fixed_context()))

            report = build_report(
                vault,
                apply=True,
                operator_confirmation=APPLY_CONFIRMATION,
                context=fixed_context(),
            )

            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())
            self.assertEqual(report["mode"], "applied")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["applied_move_count"], 1)
            self.assertEqual(report["summary"]["deferred_move_count"], 0)
            self.assertEqual(report["moves"][0]["execution_status"], "applied")
            self.assertEqual(report["moves"][0]["rollback_path"], "ops/reports/eval-initial-2026-04-12.json")
            self.assertTrue(report["moves"][0]["rollback_available"])
            self.assertTrue(any("source_before_apply:" in item for item in report["moves"][0]["evidence"]))
            self.assertTrue(any("destination_after_apply:" in item for item in report["moves"][0]["evidence"]))
            self.assertTrue(any("sha256=" in item for item in report["moves"][0]["evidence"]))
            self.assertEqual(validate_with_schema(report, load_schema(MANIFEST_SCHEMA_PATH)), [])
            self.assertEqual(validate_with_schema(report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_deferred_manifest_records_operator_decision_without_moving_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            source = vault / "ops" / "reports" / "eval-initial-2026-04-12.json"
            destination = vault / "ops" / "reports" / "archive" / source.name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("{}", encoding="utf-8")
            write_index_report(vault, build_index_report(vault, context=fixed_context()))

            report = build_report(vault, defer=True, context=fixed_context())

            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())
            self.assertEqual(report["mode"], "deferred")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["deferred_move_count"], 1)
            self.assertEqual(report["moves"][0]["execution_status"], "deferred")
            self.assertFalse(report["moves"][0]["rollback_available"])
            self.assertTrue(any("source_at_defer:" in item for item in report["moves"][0]["evidence"]))
            self.assertEqual(validate_with_schema(report, load_schema(MANIFEST_SCHEMA_PATH)), [])
            self.assertEqual(validate_with_schema(report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_rollback_manifest_restores_applied_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            source = vault / "ops" / "reports" / "eval-initial-2026-04-12.json"
            destination = vault / "ops" / "reports" / "archive" / source.name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('{"ok": true}', encoding="utf-8")
            write_index_report(vault, build_index_report(vault, context=fixed_context()))
            applied_report = build_report(
                vault,
                apply=True,
                operator_confirmation=APPLY_CONFIRMATION,
                context=fixed_context(),
            )
            write_report(vault, applied_report)

            rollback_report = build_report(
                vault,
                rollback=True,
                operator_confirmation=ROLLBACK_CONFIRMATION,
                context=fixed_context(),
            )

            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_text(encoding="utf-8"), '{"ok": true}')
            self.assertEqual(rollback_report["mode"], "rollback")
            self.assertEqual(rollback_report["status"], "pass")
            self.assertEqual(rollback_report["moves"][0]["execution_status"], "rolled_back")
            self.assertFalse(rollback_report["moves"][0]["rollback_available"])
            self.assertTrue(
                any("destination_before_rollback:" in item for item in rollback_report["moves"][0]["evidence"])
            )
            self.assertTrue(
                any("rollback_path_after_rollback:" in item for item in rollback_report["moves"][0]["evidence"])
            )
            self.assertTrue(any("sha256=" in item for item in rollback_report["moves"][0]["evidence"]))
            self.assertEqual(validate_with_schema(rollback_report, load_schema(MANIFEST_SCHEMA_PATH)), [])
            self.assertEqual(validate_with_schema(rollback_report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_rollback_manifest_restores_applied_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            source = vault / "runs" / "run-20260401-archive-me"
            destination = vault / "runs" / "archive" / source.name
            source.mkdir(parents=True)
            (source / "promotion-report.json").write_text(
                '{"history":{"status":"archived"},"decision":"archived"}',
                encoding="utf-8",
            )
            (source / "payload.txt").write_text("directory payload", encoding="utf-8")
            write_index_report(vault, build_index_report(vault, context=fixed_context()))
            applied_report = build_report(
                vault,
                apply=True,
                operator_confirmation=APPLY_CONFIRMATION,
                context=fixed_context(),
            )
            write_report(vault, applied_report)

            rollback_report = build_report(
                vault,
                rollback=True,
                operator_confirmation=ROLLBACK_CONFIRMATION,
                context=fixed_context(),
            )

            self.assertTrue(source.is_dir())
            self.assertFalse(destination.exists())
            self.assertEqual((source / "payload.txt").read_text(encoding="utf-8"), "directory payload")
            self.assertEqual(applied_report["moves"][0]["move_type"], "directory")
            self.assertEqual(rollback_report["moves"][0]["execution_status"], "rolled_back")
            self.assertTrue(any("type=directory" in item for item in applied_report["moves"][0]["evidence"]))
            self.assertEqual(validate_with_schema(rollback_report, load_schema(MANIFEST_SCHEMA_PATH)), [])
            self.assertEqual(validate_with_schema(rollback_report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_rollback_blocks_when_original_path_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            source = vault / "ops" / "reports" / "eval-initial-2026-04-12.json"
            destination = vault / "ops" / "reports" / "archive" / source.name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("archive me", encoding="utf-8")
            write_index_report(vault, build_index_report(vault, context=fixed_context()))
            applied_report = build_report(
                vault,
                apply=True,
                operator_confirmation=APPLY_CONFIRMATION,
                context=fixed_context(),
            )
            write_report(vault, applied_report)

            unconfirmed_report = build_report(vault, rollback=True, context=fixed_context())
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())
            self.assertEqual(unconfirmed_report["status"], "fail")
            self.assertEqual(unconfirmed_report["moves"][0]["execution_status"], "blocked")
            self.assertIn(
                f"operator confirmation must equal {ROLLBACK_CONFIRMATION}",
                unconfirmed_report["moves"][0]["evidence"],
            )

            source.write_text("operator-created replacement", encoding="utf-8")

            rollback_report = build_report(
                vault,
                rollback=True,
                operator_confirmation=ROLLBACK_CONFIRMATION,
                context=fixed_context(),
            )

            self.assertTrue(source.exists())
            self.assertTrue(destination.exists())
            self.assertEqual(source.read_text(encoding="utf-8"), "operator-created replacement")
            self.assertEqual(destination.read_text(encoding="utf-8"), "archive me")
            self.assertEqual(rollback_report["status"], "fail")
            self.assertEqual(rollback_report["summary"]["blocked_move_count"], 1)
            self.assertEqual(rollback_report["moves"][0]["execution_status"], "blocked")
            self.assertIn("rollback path already exists", rollback_report["moves"][0]["evidence"])
            self.assertFalse(rollback_report["moves"][0]["rollback_available"])


if __name__ == "__main__":
    unittest.main()
