from __future__ import annotations

import datetime as dt
import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path

import pytest
from ops.scripts.artifact_freshness_runtime import (
    ArtifactFreshnessContext,
    build_canonical_report_envelope,
    build_report,
    write_report,
)
from ops.scripts.command_runtime import TimedProcessResult
from ops.scripts.external_report_action_matrix import (
    build_report as build_external_report_action_matrix,
    write_report as write_external_report_action_matrix,
)
from ops.scripts.generated_artifact_index import (
    build_report as build_generated_artifact_index,
    write_report as write_generated_artifact_index,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import CYCLONEDX_16_SCHEMA_URI
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint
from ops.scripts.test_execution_summary import (
    build_report as build_test_execution_summary,
    write_report as write_test_execution_summary,
)

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-freshness-report.schema.json"
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"
ROOT_EPHEMERAL_PATTERNS = [
    "pytest_*.log",
    "pytest_*.xml",
    "pytest_*_output.txt",
    "pytest_*_requested*.txt",
]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 24, 12, 0, tzinfo=dt.UTC),
    )


def test_no_root_ephemeral_test_artifacts() -> None:
    offenders: list[str] = []
    for pattern in ROOT_EPHEMERAL_PATTERNS:
        offenders.extend(path.as_posix() for path in REPO_ROOT.glob(pattern) if path.is_file())

    assert offenders == [], f"Root ephemeral artifacts found: {offenders}"


class ArtifactFreshnessRuntimeTests(unittest.TestCase):
    def test_canonical_report_envelope_fingerprints_source_paths_and_flat_script_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            script_path = vault / "ops" / "scripts" / "core" / "example_runtime.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("VALUE = 1\n", encoding="utf-8")
            common_kwargs = {
                "generated_at": "2026-04-24T12:00:00Z",
                "artifact_kind": "example_report",
                "producer": "tests.example_report",
                "source_command": "pytest",
                "resolved_policy_path": vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                "schema_path": "ops/schemas/artifact-envelope.schema.json",
            }

            legacy_alias_envelope = build_canonical_report_envelope(
                vault,
                **common_kwargs,
                source_paths=["ops/scripts/example_runtime.py"],
            )
            canonical_envelope = build_canonical_report_envelope(
                vault,
                **common_kwargs,
                source_paths=["ops/scripts/core/example_runtime.py"],
            )
            script_path.write_text("VALUE = 2\n", encoding="utf-8")
            changed_envelope = build_canonical_report_envelope(
                vault,
                **common_kwargs,
                source_paths=["ops/scripts/example_runtime.py"],
            )

            self.assertIn("source_paths", legacy_alias_envelope["input_fingerprints"])
            self.assertEqual(
                legacy_alias_envelope["input_fingerprints"]["source_paths"],
                canonical_envelope["input_fingerprints"]["source_paths"],
            )
            self.assertNotEqual(
                legacy_alias_envelope["input_fingerprints"]["source_paths"],
                changed_envelope["input_fingerprints"]["source_paths"],
            )

    def _write_current_artifact(self, vault: Path) -> Path:
        (vault / "ops" / "schemas" / "example.schema.json").write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["answer"],
                    "properties": {"answer": {"type": "string"}},
                }
            ),
            encoding="utf-8",
        )
        artifact_path = vault / "ops" / "reports" / "current-report.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(
                {
                    "$schema": "ops/schemas/example.schema.json",
                    "artifact_kind": "example_report",
                    "generated_at": "2026-04-24T12:00:00Z",
                    "producer": "test",
                    "source_command": "pytest",
                    "source_revision": "source_package_without_git",
                    "source_tree_fingerprint": release_source_tree_fingerprint(vault),
                    "input_fingerprints": {"policy": "abc"},
                    "schema_version": 1,
                    "artifact_status": "current",
                    "retention_policy": "canonical_report",
                    "encoding": "utf-8",
                    "currentness": {
                        "status": "current",
                        "checked_at": "2026-04-24T12:00:00Z",
                    },
                    "answer": "ok",
                }
            ),
            encoding="utf-8",
        )
        return artifact_path

    def test_schema_validator_cache_and_progress_jsonl_are_run_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            artifact_path = self._write_current_artifact(vault)
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))

            freshness_context = ArtifactFreshnessContext(vault=vault)
            self.assertEqual(freshness_context.validate_payload(payload), ("pass", []))
            self.assertEqual(freshness_context.validate_payload(payload), ("pass", []))
            self.assertIn("ops/schemas/example.schema.json", freshness_context.schema_cache)
            self.assertIn("ops/schemas/example.schema.json", freshness_context.validator_cache)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                report = build_report(vault, context=fixed_context(), progress="jsonl")

            progress_events = [
                json.loads(line)
                for line in stderr.getvalue().splitlines()
                if line.strip()
            ]
            self.assertTrue(progress_events)
            self.assertTrue(any(event["phase"] == "json_schema_validation" for event in progress_events))
            self.assertTrue(report["phase_timings"])
            self.assertTrue(any(item["phase"] == "json_schema_validation" for item in report["phase_timings"]))
            self.assertTrue(any(item["elapsed_seconds"] > 0 for item in report["phase_timings"]))
            self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_default_phase_timings_do_not_make_canonical_report_nondeterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            first = build_report(vault, context=fixed_context())
            second = build_report(vault, context=fixed_context())

            self.assertEqual(first, second)
            self.assertTrue(first["phase_timings"])
            self.assertTrue(
                all(item["elapsed_seconds"] == 0.0 for item in first["phase_timings"])
            )
            self.assertEqual(validate_with_schema(first, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_test_execution_summary_becomes_stale_when_target_test_file_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            test_file = vault / "tests" / "test_target_sample.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_sample():\n    assert True\n", encoding="utf-8")

            result = TimedProcessResult(
                args=["python", "-m", "pytest", "tests/test_target_sample.py"],
                returncode=0,
                stdout="1 passed in 0.01s",
                stderr="",
                timed_out=False,
                timeout_seconds=30,
                termination_reason="completed",
            )
            summary = build_test_execution_summary(
                vault,
                command=["python", "-m", "pytest", "tests/test_target_sample.py"],
                result=result,
                duration_ms=10,
                suite="unit",
                context=fixed_context(),
            )
            write_test_execution_summary(vault, summary, "ops/reports/test-execution-summary.json")
            newer_timestamp = dt.datetime(2026, 4, 24, 12, 0, 1, tzinfo=dt.UTC).timestamp()
            os.utime(test_file, (newer_timestamp, newer_timestamp))

            report = build_report(vault, context=fixed_context())
            record = next(
                item
                for item in report["artifact_records"]
                if item["path"] == "ops/reports/test-execution-summary.json"
            )

            self.assertIn("generated_at_older_than_file_mtime", record["issues"])
            self.assertEqual(record["recommended_next_action"], "regenerate_artifact_or_refresh_timestamp")
            self.assertEqual(record["gate_effect"], "blocks_promotion")
            self.assertEqual(report["gate_effect"], "blocks_promotion")
            self.assertTrue(record["mtime_sensitive"])

    def test_test_target_fingerprint_mismatch_counts_as_operational_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            test_file = vault / "tests" / "test_target_sample.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("def test_sample():\n    assert True\n", encoding="utf-8")

            result = TimedProcessResult(
                args=["python", "-m", "pytest", "tests/test_target_sample.py"],
                returncode=0,
                stdout="1 passed in 0.01s",
                stderr="",
                timed_out=False,
                timeout_seconds=30,
                termination_reason="completed",
            )
            summary = build_test_execution_summary(
                vault,
                command=["python", "-m", "pytest", "tests/test_target_sample.py"],
                result=result,
                duration_ms=10,
                suite="unit",
                context=fixed_context(),
            )
            write_test_execution_summary(vault, summary, "ops/reports/test-execution-summary.json")
            test_file.write_text("def test_sample():\n    assert False\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())
            record = next(
                item
                for item in report["artifact_records"]
                if item["path"] == "ops/reports/test-execution-summary.json"
            )

            self.assertIn(
                "test_target_fingerprint_mismatch:tests/test_target_sample.py",
                record["issues"],
            )
            self.assertIn(report["status"], {"pass", "attention"})
            self.assertEqual(report["summary"]["operational_attention_artifact_count"], 1)
            self.assertEqual(report["summary"]["operational_attention_issue_count"], 2)
            self.assertIn("source_tree_fingerprint_mismatch", record["issues"])
            self.assertEqual(record["gate_effect"], "blocks_promotion")
            self.assertEqual(report["gate_effect"], "blocks_promotion")

    def test_generated_artifact_index_mtime_drift_is_advisory_not_canonical_debt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            generated_index = build_generated_artifact_index(vault, context=fixed_context())
            generated_index_path = write_generated_artifact_index(vault, generated_index)
            newer_timestamp = dt.datetime(2026, 4, 24, 12, 0, 1, tzinfo=dt.UTC).timestamp()
            os.utime(generated_index_path, (newer_timestamp, newer_timestamp))

            report = build_report(vault, context=fixed_context())
            record = next(
                item
                for item in report["artifact_records"]
                if item["path"] == "ops/reports/generated-artifact-index.json"
            )

            self.assertEqual(record["mtime_status"], "stale")
            self.assertTrue(record["mtime_sensitive"])
            self.assertEqual(record["mtime_sensitive_issues"], ["generated_at_older_than_file_mtime"])
            self.assertNotIn("generated_at_older_than_file_mtime", record["issues"])
            self.assertEqual(record["issues"], [])
            self.assertEqual(record["contract_issue_class"], "mtime_sensitive_attention")
            self.assertEqual(record["gate_effect"], "advisory")
            self.assertEqual(record["recommended_next_action"], "none")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["gate_effect"], "advisory")
            self.assertEqual(report["recommended_next_action"], "none")
            self.assertEqual(report["summary"]["stale_artifact_count"], 0)
            self.assertEqual(report["summary"]["mtime_sensitive_artifact_count"], 1)
            self.assertEqual(report["summary"]["mtime_sensitive_attention_artifact_count"], 1)

    def test_source_current_producer_input_fingerprint_drift_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            action_matrix = build_external_report_action_matrix(
                vault,
                context=fixed_context(),
            )
            action_matrix_path = write_external_report_action_matrix(vault, action_matrix)
            action_matrix["input_fingerprints"] = {
                **action_matrix["input_fingerprints"],
                "action_catalog": "stale-fingerprint",
            }
            action_matrix_path.write_text(
                json.dumps(action_matrix, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            generated_index = build_generated_artifact_index(vault, context=fixed_context())
            generated_index_path = write_generated_artifact_index(vault, generated_index)
            generated_index["input_fingerprints"] = {
                **generated_index["input_fingerprints"],
                "external_report_action_matrix_statuses": "stale-fingerprint",
            }
            generated_index_path.write_text(
                json.dumps(generated_index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            report = build_report(
                vault,
                context=fixed_context(),
                mtime_source="embedded_currentness",
            )
            schema = load_schema(REPORT_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["gate_effect"], "claim_blocker")
            self.assertGreaterEqual(report["summary"]["stale_artifact_count"], 2)
            self.assertGreaterEqual(
                report["summary"]["operational_attention_artifact_count"],
                2,
            )

            records = {
                record["path"]: record
                for record in report["artifact_records"]
                if record["path"]
                in {
                    "ops/reports/external-report-action-matrix.json",
                    "ops/reports/generated-artifact-index.json",
                }
            }
            expected = {
                "ops/reports/external-report-action-matrix.json": "action_catalog",
                "ops/reports/generated-artifact-index.json": (
                    "external_report_action_matrix_statuses"
                ),
            }
            self.assertEqual(set(records), set(expected))
            for path, expected_key in expected.items():
                with self.subTest(path=path):
                    record = records[path]
                    self.assertEqual(record["source_revision_status"], "current")
                    self.assertEqual(record["source_tree_fingerprint_status"], "current")
                    self.assertEqual(record["input_fingerprint_status"], "stale")
                    self.assertEqual(
                        record["input_fingerprint_mismatch_keys"],
                        [expected_key],
                    )
                    self.assertEqual(record["currentness_status"], "stale")
                    self.assertIn(
                        f"input_fingerprint_mismatch:{expected_key}",
                        record["issues"],
                    )
                    self.assertEqual(
                        record["contract_issue_class"],
                        "operational_attention",
                    )
                    self.assertEqual(record["gate_effect"], "claim_blocker")
                    self.assertEqual(
                        record["recommended_next_action"],
                        "regenerate_canonical_report",
                    )
                    self.assertFalse(record["safe_to_backfill"])

    def test_zip_info_mtime_source_uses_archive_metadata_instead_of_filesystem_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            artifact_path = self._write_current_artifact(vault)
            stale_timestamp = dt.datetime(2026, 4, 24, 12, 0, 1, tzinfo=dt.UTC).timestamp()
            os.utime(artifact_path, (stale_timestamp, stale_timestamp))
            archive_path = vault / "tmp" / "release.zip"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            zip_info = zipfile.ZipInfo("ops/reports/current-report.json", (2026, 4, 24, 12, 0, 0))
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(zip_info, artifact_path.read_text(encoding="utf-8"))

            filesystem_report = build_report(vault, context=fixed_context())
            zip_report = build_report(
                vault,
                context=fixed_context(),
                mtime_source="zip_info",
                zip_metadata_path=archive_path,
            )
            schema = load_schema(REPORT_SCHEMA_PATH)
            filesystem_record = next(
                item
                for item in filesystem_report["artifact_records"]
                if item["path"] == "ops/reports/current-report.json"
            )
            zip_record = next(
                item
                for item in zip_report["artifact_records"]
                if item["path"] == "ops/reports/current-report.json"
            )

            self.assertEqual(validate_with_schema(zip_report, schema), [])
            self.assertEqual(filesystem_report["mtime_source"], "filesystem")
            self.assertEqual(filesystem_record["mtime_source"], "filesystem")
            self.assertEqual(filesystem_record["mtime_status"], "stale")
            self.assertIn("generated_at_older_than_file_mtime", filesystem_record["issues"])
            self.assertEqual(zip_report["mtime_source"], "zip_info")
            self.assertEqual(zip_report["zip_metadata_path"], "tmp/release.zip")
            self.assertEqual(zip_record["mtime_source"], "zip_info")
            self.assertEqual(zip_record["file_mtime_utc"], "2026-04-24T12:00:00Z")
            self.assertEqual(zip_record["mtime_status"], "current")
            self.assertNotIn("generated_at_older_than_file_mtime", zip_record["issues"])
            self.assertEqual(zip_report["status"], "pass")
            self.assertEqual(zip_report["summary"]["stale_artifact_count"], 0)

    def test_operator_reports_are_scanned_on_operator_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            reports_dir = vault / "ops" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            operator_dir = vault / "ops" / "operator"
            operator_dir.mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "schemas" / "operator-example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            (operator_dir / "operator-release-summary.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/operator-example.schema.json",
                        "artifact_kind": "operator_example",
                        "generated_at": "2026-04-24T12:00:00Z",
                        "producer": "test",
                        "source_command": "pytest",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "abc",
                        "input_fingerprints": {"policy": "abc"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2026-04-24T12:00:00Z",
                        },
                        "answer": "ok",
                    }
                ),
                encoding="utf-8",
            )
            (reports_dir / "release-closeout-batch-manifest.json").write_text(
                "{not-json",
                encoding="utf-8",
            )
            (reports_dir / "release-evidence-closeout-self-check.json").write_text(
                "{not-json",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            paths = {record["path"] for record in report["artifact_records"]}
            self.assertIn("ops/operator/operator-release-summary.json", paths)
            self.assertNotIn("ops/reports/release-closeout-batch-manifest.json", paths)
            self.assertNotIn("ops/reports/release-evidence-closeout-self-check.json", paths)
            operator_record = next(
                record
                for record in report["artifact_records"]
                if record["path"] == "ops/operator/operator-release-summary.json"
            )
            self.assertEqual(operator_record["owner_surface"], "operator_reports")

    def test_embedded_currentness_mtime_source_ignores_filesystem_mtime_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            artifact_path = self._write_current_artifact(vault)
            stale_timestamp = dt.datetime(2026, 4, 24, 12, 0, 1, tzinfo=dt.UTC).timestamp()
            os.utime(artifact_path, (stale_timestamp, stale_timestamp))

            filesystem_report = build_report(vault, context=fixed_context())
            embedded_report = build_report(
                vault,
                context=fixed_context(),
                mtime_source="embedded_currentness",
            )
            schema = load_schema(REPORT_SCHEMA_PATH)
            filesystem_record = next(
                item
                for item in filesystem_report["artifact_records"]
                if item["path"] == "ops/reports/current-report.json"
            )
            embedded_record = next(
                item
                for item in embedded_report["artifact_records"]
                if item["path"] == "ops/reports/current-report.json"
            )

            self.assertEqual(validate_with_schema(embedded_report, schema), [])
            self.assertEqual(filesystem_record["mtime_status"], "stale")
            self.assertIn("generated_at_older_than_file_mtime", filesystem_record["issues"])
            self.assertEqual(embedded_report["mtime_source"], "embedded_currentness")
            self.assertEqual(embedded_record["mtime_source"], "embedded_currentness")
            self.assertEqual(embedded_record["file_mtime_utc"], "")
            self.assertEqual(embedded_record["mtime_status"], "unknown")
            self.assertEqual(embedded_record["currentness_status"], "current")
            self.assertEqual(embedded_record["schema_validation_status"], "pass")
            self.assertTrue(embedded_record["has_artifact_envelope"])
            self.assertNotIn("generated_at_older_than_file_mtime", embedded_record["issues"])
            self.assertEqual(embedded_report["status"], "pass")
            self.assertEqual(embedded_report["summary"]["stale_artifact_count"], 0)

    def test_report_flags_root_ephemeral_artifacts_and_missing_envelopes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "pytest_target.log").write_text("stale pytest output\n", encoding="utf-8")
            (vault / "ops" / "reports" / "legacy-report.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "generated_at": "2026-04-24T12:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            schema = load_schema(REPORT_SCHEMA_PATH)
            envelope_schema = load_schema(ENVELOPE_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(validate_with_schema(report, envelope_schema), [])
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["recommended_next_action"], "remove_root_ephemeral_artifacts")
            self.assertTrue(report["mtime_sensitive"])
            self.assertTrue(any(item["issue"] == "missing_artifact_envelope" for item in report["top_debt"]))
            self.assertEqual(report["top_debt_files"][0]["path"], "pytest_target.log")
            self.assertEqual(report["top_debt_files"][0]["primary_issue"], "root_ephemeral_artifact")
            self.assertEqual(report["top_debt_files"][0]["recommended_next_action"], "remove_root_ephemeral_artifact")
            self.assertGreaterEqual(report["top_debt_files"][0]["expected_debt_reduction"], 1)
            self.assertEqual(report["summary"]["root_ephemeral_artifact_count"], 1)
            self.assertEqual(report["root_ephemeral_artifacts"][0]["path"], "pytest_target.log")
            self.assertGreaterEqual(report["summary"]["missing_artifact_envelope_count"], 1)
            legacy_record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/legacy-report.json"
            )
            legacy_debt_file = next(
                item for item in report["top_debt_files"] if item["path"] == "ops/reports/legacy-report.json"
            )
            self.assertIn("missing_artifact_envelope", legacy_record["issues"])
            self.assertEqual(legacy_record["owner_surface"], "ops_reports")
            self.assertEqual(legacy_record["recommended_next_action"], "backfill_artifact_envelope")
            self.assertFalse(legacy_record["safe_to_backfill"])
            self.assertEqual(legacy_record["contract_issue_class"], "stable_contract_debt")
            self.assertIn("missing_artifact_envelope", legacy_record["stable_contract_issues"])
            self.assertIn("generated_at_older_than_file_mtime", legacy_record["mtime_sensitive_issues"])
            self.assertEqual(legacy_record["schema_validation_status"], "schema_unavailable")
            self.assertEqual(legacy_record["schema_contract"]["status"], "unavailable")
            self.assertEqual(legacy_record["schema_contract"]["classification"], "schema_reference_unavailable")
            self.assertTrue(legacy_record["schema_validation_errors"])
            self.assertEqual(report["summary"]["stable_contract_debt_artifact_count"], 1)
            self.assertGreaterEqual(report["summary"]["stable_contract_debt_issue_count"], 3)
            self.assertEqual(report["summary"]["mtime_sensitive_attention_artifact_count"], 1)
            self.assertEqual(legacy_debt_file["owner_surface"], "ops_reports")
            self.assertIn("missing_artifact_envelope", legacy_debt_file["issues"])
            self.assertEqual(legacy_debt_file["expected_debt_reduction"], len(legacy_debt_file["issues"]))
            queues = {item["queue"]: item for item in report["debt_queues"]}
            self.assertEqual(queues["ops_reports_producer_refresh"]["status"], "open")
            self.assertEqual(queues["ops_reports_producer_refresh"]["item_count"], 1)
            self.assertIn("Ops report producers emit schema-backed current artifacts", queues["ops_reports_producer_refresh"]["exit_condition"])
            self.assertEqual(queues["mtime_sensitive_regeneration"]["status"], "open")
            self.assertEqual(queues["runs_historical_archive"]["status"], "complete")

    def test_report_classifies_missing_schema_debt_by_artifact_family(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "eval-initial-2026-04-12.json").write_text(
                json.dumps({"summary": {"score": 1}}),
                encoding="utf-8",
            )
            run_report = (
                vault
                / "runs"
                / "run-20260422-raw-intake-registration-and-promotion"
                / "validation"
                / "wiki-lint-final-tree-2026-04-22.json"
            )
            run_report.parent.mkdir(parents=True, exist_ok=True)
            run_report.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
            one_off_note = (
                vault
                / "runs"
                / "run-20260422-raw-intake-registration-and-promotion"
                / "promotion"
                / "concept-continuity-integration-2026-04-22.json"
            )
            one_off_note.parent.mkdir(parents=True, exist_ok=True)
            one_off_note.write_text(
                json.dumps({"manifest_families_updated": [], "concept_pages_updated": []}),
                encoding="utf-8",
            )
            archived_auxiliary = (
                vault
                / "runs"
                / "archive"
                / "run-validator-rejected"
                / "worker-executor-report.json"
            )
            archived_auxiliary.parent.mkdir(parents=True, exist_ok=True)
            archived_auxiliary.write_text(
                json.dumps({"status": "fail", "diagnostics": {"notes": []}}),
                encoding="utf-8",
            )
            archived_reviewer_routing = (
                vault
                / "runs"
                / "archive"
                / "run-validator-rejected"
                / "subagent-routing.reviewer.json"
            )
            archived_reviewer_routing.write_text(
                json.dumps({"role": "reviewer", "selected_rung": "micro"}),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            bootstrap_record = next(
                item
                for item in report["artifact_records"]
                if item["path"] == "ops/reports/eval-initial-2026-04-12.json"
            )
            run_record = next(
                item
                for item in report["artifact_records"]
                if item["path"].endswith("wiki-lint-final-tree-2026-04-22.json")
            )
            one_off_record = next(
                item
                for item in report["artifact_records"]
                if item["path"].endswith("concept-continuity-integration-2026-04-22.json")
            )
            archived_auxiliary_record = next(
                item
                for item in report["artifact_records"]
                if item["path"].endswith("worker-executor-report.json")
            )
            archived_reviewer_routing_record = next(
                item
                for item in report["artifact_records"]
                if item["path"].endswith("subagent-routing.reviewer.json")
            )

            self.assertEqual(report["summary"]["missing_schema_count"], 2)
            self.assertEqual(report["summary"]["stable_contract_debt_artifact_count"], 2)
            queues = {item["queue"]: item for item in report["debt_queues"]}
            self.assertEqual(queues["runs_historical_archive"]["status"], "open")
            self.assertEqual(queues["runs_historical_archive"]["item_count"], 1)
            self.assertTrue(queues["runs_historical_archive"]["paths"][0]["path"].endswith("wiki-lint-final-tree-2026-04-22.json"))
            self.assertEqual(bootstrap_record["schema_contract"]["status"], "missing")
            self.assertEqual(
                bootstrap_record["schema_contract"]["classification"],
                "historical_bootstrap_report_pending_schema_decision",
            )
            self.assertEqual(run_record["schema_contract"]["status"], "missing")
            self.assertEqual(
                run_record["schema_contract"]["classification"],
                "raw_intake_run_artifact_family_pending_schema",
            )
            self.assertEqual(one_off_record["schema_contract"]["status"], "not_applicable")
            self.assertEqual(
                one_off_record["schema_contract"]["classification"],
                "noncanonical_archived_run_note",
            )
            self.assertEqual(one_off_record["contract_issue_class"], "clean")
            self.assertEqual(one_off_record["issues"], [])
            self.assertEqual(
                archived_auxiliary_record["schema_contract"]["classification"],
                "noncanonical_archived_run_note",
            )
            self.assertEqual(archived_auxiliary_record["contract_issue_class"], "clean")
            self.assertEqual(archived_auxiliary_record["issues"], [])
            self.assertEqual(
                archived_reviewer_routing_record["schema_contract"]["classification"],
                "noncanonical_archived_run_note",
            )
            self.assertEqual(archived_reviewer_routing_record["contract_issue_class"], "clean")
            self.assertEqual(archived_reviewer_routing_record["issues"], [])

    def test_report_classifies_zero_byte_run_command_logs_as_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = vault / "runs" / "run-log-placeholder"
            run_dir.mkdir(parents=True)
            (run_dir / "mutation-command.stdout.txt").write_text("", encoding="utf-8")
            (run_dir / "repo-health.stderr.txt").write_text("not empty\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())
            schema = load_schema(REPORT_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["summary"]["run_log_placeholder_count"], 1)
            self.assertEqual(
                report["run_log_placeholders"],
                [
                    {
                        "path": "runs/run-log-placeholder/mutation-command.stdout.txt",
                        "artifact_role": "run_log_placeholder",
                        "size_bytes": 0,
                        "classification": "empty_run_command_log_placeholder",
                    }
                ],
            )
            self.assertFalse(
                any(
                    item["primary_issue"] == "run_log_placeholder"
                    for item in report["top_debt_files"]
                )
            )

    def test_report_accepts_enveloped_current_json_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "current-report.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "example_report",
                        "generated_at": "2999-01-01T00:00:00Z",
                        "producer": "test",
                        "source_command": "pytest",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "abc",
                        "input_fingerprints": {"policy": "abc"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2999-01-01T00:00:00Z",
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/current-report.json"
            )

            self.assertTrue(record["has_artifact_envelope"])
            self.assertEqual(record["currentness_status"], "current")
            self.assertEqual(record["schema_validation_status"], "schema_unavailable")
            self.assertTrue(record["safe_to_backfill"])
            self.assertNotIn("missing_artifact_envelope", record["issues"])

    def test_canonical_report_source_tree_mismatch_overrides_self_declared_currentness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            current_source_tree = release_source_tree_fingerprint(vault)
            self.assertNotEqual(current_source_tree, "stale-source-tree")
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "public-check-summary.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "public_check_summary",
                        "generated_at": "2999-01-01T00:00:00Z",
                        "producer": "test",
                        "source_command": "pytest",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "stale-source-tree",
                        "input_fingerprints": {"policy": "abc"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2999-01-01T00:00:00Z",
                        },
                        "answer": "ok",
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            schema = load_schema(REPORT_SCHEMA_PATH)
            record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/public-check-summary.json"
            )

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["recommended_next_action"], "regenerate_stale_artifacts")
            self.assertEqual(record["declared_currentness_status"], "current")
            self.assertEqual(record["source_tree_fingerprint_status"], "stale")
            self.assertEqual(record["currentness_status"], "stale")
            self.assertIn("source_tree_fingerprint_mismatch", record["issues"])
            self.assertEqual(record["gate_effect"], "claim_blocker")
            self.assertEqual(report["gate_effect"], "claim_blocker")
            self.assertFalse(record["safe_to_backfill"])
            self.assertEqual(record["recommended_next_action"], "regenerate_canonical_report")
            self.assertEqual(report["stale_routing"]["classification"], "source_identity_only")
            self.assertEqual(
                report["stale_routing"]["recommended_lane"],
                "freshness-source-identity-converge",
            )
            self.assertEqual(
                report["stale_routing"]["recommended_targets"],
                ["freshness-source-identity-converge"],
            )
            self.assertEqual(report["stale_routing"]["source_identity_only_artifact_count"], 1)
            self.assertEqual(report["stale_routing"]["execution_blocking_artifact_count"], 0)
            self.assertEqual(
                report["stale_routing"]["source_identity_owner_routes"][0]["recommended_lane"],
                "public-check-summary-current-or-refresh",
            )
            self.assertEqual(
                report["stale_routing"]["source_identity_owner_routes"][0]["artifact_kinds"],
                ["public_check_summary"],
            )

    def test_canonical_report_source_revision_mismatch_overrides_self_declared_currentness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            current_source_tree = release_source_tree_fingerprint(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "public-check-summary.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "public_check_summary",
                        "generated_at": "2999-01-01T00:00:00Z",
                        "producer": "test",
                        "source_command": "pytest",
                        "source_revision": "old-revision",
                        "source_tree_fingerprint": current_source_tree,
                        "input_fingerprints": {"policy": "abc"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2999-01-01T00:00:00Z",
                        },
                        "answer": "ok",
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            schema = load_schema(REPORT_SCHEMA_PATH)
            record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/public-check-summary.json"
            )

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["recommended_next_action"], "regenerate_stale_artifacts")
            self.assertEqual(record["declared_currentness_status"], "current")
            self.assertEqual(record["source_tree_fingerprint_status"], "current")
            self.assertEqual(record["source_revision_status"], "stale")
            self.assertEqual(record["currentness_status"], "stale")
            self.assertIn("source_revision_mismatch", record["issues"])
            self.assertEqual(record["gate_effect"], "claim_blocker")
            self.assertEqual(report["gate_effect"], "claim_blocker")
            self.assertFalse(record["safe_to_backfill"])
            self.assertEqual(record["recommended_next_action"], "regenerate_canonical_report")
            self.assertEqual(report["stale_routing"]["classification"], "source_identity_only")
            self.assertEqual(
                report["stale_routing"]["recommended_lane"],
                "freshness-source-identity-converge",
            )
            self.assertEqual(report["stale_routing"]["source_identity_only_artifact_count"], 1)
            self.assertEqual(report["stale_routing"]["source_identity_only_issue_count"], 1)
            self.assertEqual(
                report["stale_routing"]["source_identity_owner_routes"][0]["recommended_targets"],
                ["public-check-summary-current-or-refresh"],
            )

    def test_learning_readiness_signoff_source_identity_drift_points_to_refresh_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            current_source_tree = release_source_tree_fingerprint(vault)
            self.assertNotEqual(current_source_tree, "stale-source-tree")
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "learning-readiness-signoff.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/learning-readiness-signoff.schema.json",
                        "artifact_kind": "learning_readiness_signoff",
                        "generated_at": "2999-01-01T00:00:00Z",
                        "producer": "tests.learning_readiness_signoff",
                        "source_command": "operator signoff fixture",
                        "source_revision": "old-revision",
                        "source_tree_fingerprint": "stale-source-tree",
                        "input_fingerprints": {"operator_acceptance": "abc"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2999-01-01T00:00:00Z",
                        },
                        "vault": ".",
                        "policy": {
                            "path": "ops/policies/wiki-maintainer-policy.yaml",
                            "version": 1,
                        },
                        "linked_blocker_id": "learning_blocked_by_review_required",
                        "accepted_by": "operator@example.test",
                        "accepted_at": "2999-01-01T00:00:00Z",
                        "expires_at": "2999-01-08T00:00:00Z",
                        "risk_owner": "runtime-maintainer",
                        "revalidation_condition": "rerun release evidence closeout before release",
                        "rollback_trigger": "learning telemetry regresses",
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            record = next(
                item
                for item in report["artifact_records"]
                if item["path"] == "ops/reports/learning-readiness-signoff.json"
            )

            self.assertEqual(record["schema_validation_status"], "pass")
            self.assertEqual(record["gate_effect"], "claim_blocker")
            self.assertIn("source_tree_fingerprint_mismatch", record["issues"])
            self.assertIn("source_revision_mismatch", record["issues"])
            self.assertEqual(record["recommended_next_action"], "refresh_learning_readiness_signoff")
            self.assertEqual(report["stale_routing"]["classification"], "source_identity_only")
            self.assertEqual(
                report["stale_routing"]["recommended_lane"],
                "freshness-source-identity-converge",
            )

    def test_finality_attestation_is_finality_owned_not_freshness_debt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            finality_path = vault / "ops" / "reports" / "release-closeout-finality-attestation.json"
            finality_path.parent.mkdir(parents=True, exist_ok=True)
            finality_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/release-closeout-finality-attestation.schema.json",
                        "artifact_kind": "release_closeout_finality_attestation",
                        "generated_at": "2000-01-01T00:00:00Z",
                        "producer": "ops.scripts.release_closeout_finality_attestation",
                        "source_command": "python -m ops.scripts.release_closeout_finality_attestation --vault .",
                        "source_revision": "old-revision",
                        "source_tree_fingerprint": "old-source-tree",
                        "input_fingerprints": {},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2000-01-01T00:00:00Z",
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            schema = load_schema(REPORT_SCHEMA_PATH)

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["stale_routing"]["classification"], "clean")
            self.assertNotIn(
                "ops/reports/release-closeout-finality-attestation.json",
                {record["path"] for record in report["artifact_records"]},
            )

    def test_active_run_auxiliary_json_is_not_canonical_release_debt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = vault / "runs" / "run-active"
            run_dir.mkdir(parents=True)
            (run_dir / "worker-executor-report.json").write_text(
                json.dumps({"$schema": "ops/schemas/executor-report.schema.json"}),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            record = next(
                item for item in report["artifact_records"] if item["path"] == "runs/run-active/worker-executor-report.json"
            )

            self.assertEqual(record["schema_contract"]["classification"], "noncanonical_archived_run_note")
            self.assertEqual(record["schema_validation_status"], "not_applicable")
            self.assertEqual(record["issues"], [])
            self.assertNotIn("missing_artifact_envelope", record["stable_contract_issues"])

    def test_nested_ops_report_history_is_not_live_source_tree_currentness_debt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            nested_path = vault / "ops/reports/auto-improve-sessions/history.json"
            nested_path.parent.mkdir(parents=True)
            nested_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "historical_session_report",
                        "generated_at": "2999-01-01T00:00:00Z",
                        "producer": "test",
                        "source_command": "pytest",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "historical-source-tree",
                        "input_fingerprints": {"policy": "abc"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2999-01-01T00:00:00Z",
                        },
                        "answer": "ok",
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            record = next(
                item
                for item in report["artifact_records"]
                if item["path"] == "ops/reports/auto-improve-sessions/history.json"
            )

            self.assertEqual(record["source_tree_fingerprint_status"], "not_applicable")
            self.assertEqual(record["currentness_status"], "current")
            self.assertNotIn("source_tree_fingerprint_mismatch", record["issues"])

    def test_archived_artifacts_with_archive_retention_do_not_accumulate_mtime_drift_debt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "archived-report.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "example_report",
                        "generated_at": "2026-04-01T00:00:00Z",
                        "producer": "test",
                        "source_command": "python -m example",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "abc",
                        "input_fingerprints": {"policy": "abc"},
                        "schema_version": 1,
                        "artifact_status": "archived",
                        "retention_policy": "archive",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2026-04-24T12:00:00Z",
                        },
                        "answer": "ok",
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/archived-report.json"
            )

            self.assertEqual(record["artifact_status"], "archived")
            self.assertEqual(record["retention_policy"], "archive")
            self.assertEqual(record["mtime_status"], "current")
            self.assertEqual(record["schema_validation_status"], "pass")
            self.assertNotIn("generated_at_older_than_file_mtime", record["issues"])
            self.assertEqual(record["mtime_sensitive_issues"], [])

    def test_report_records_artifact_schema_validation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "invalid-report.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "example_report",
                        "generated_at": "2026-04-24T12:00:00Z",
                        "producer": "test",
                        "source_command": "pytest",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "abc",
                        "input_fingerprints": {"policy": "abc"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2026-04-24T12:00:00Z",
                        },
                        "answer": 1,
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            schema = load_schema(REPORT_SCHEMA_PATH)
            record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/invalid-report.json"
            )

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["schema_invalid_artifact_count"], 1)
            self.assertEqual(report["recommended_next_action"], "regenerate_schema_invalid_artifacts")
            self.assertEqual(record["schema_validation_status"], "fail")
            self.assertEqual(record["gate_effect"], "blocks_execution")
            self.assertEqual(report["gate_effect"], "blocks_execution")
            self.assertFalse(record["safe_to_backfill"])
            self.assertIn("schema_validation_failed", record["issues"])
            self.assertTrue(any("expected string" in error for error in record["schema_validation_errors"]))

    def test_historical_run_schema_drift_is_advisory_contract_debt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            run_report = vault / "runs" / "legacy-run" / "historical-schema-drift.json"
            run_report.parent.mkdir(parents=True, exist_ok=True)
            run_report.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "artifact_freshness_report",
                        "generated_at": "2026-04-24T12:00:00Z",
                        "producer": "ops.scripts.artifact_freshness_runtime",
                        "source_command": "make artifact-freshness-check",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "historical",
                        "input_fingerprints": {"policy": "historical"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2026-04-24T12:00:00Z",
                        },
                        "answer": 1,
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context(), mtime_source="embedded_currentness")
            schema = load_schema(REPORT_SCHEMA_PATH)
            record = next(
                item
                for item in report["artifact_records"]
                if item["path"].endswith("historical-schema-drift.json")
            )
            schema_debt = next(item for item in report["top_debt"] if item["issue"] == "schema_validation_failed")
            queues = {item["queue"]: item for item in report["debt_queues"]}

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["summary"]["schema_invalid_artifact_count"], 0)
            self.assertEqual(record["schema_validation_status"], "historical_schema_drift")
            self.assertEqual(record["schema_contract"]["classification"], "historical_run_schema_drift")
            self.assertEqual(record["contract_issue_class"], "stable_contract_debt")
            self.assertEqual(record["gate_effect"], "advisory")
            self.assertEqual(schema_debt["gate_effect"], "advisory")
            self.assertEqual(schema_debt["recommended_next_action"], "archive_or_classify_historical_run_artifact")
            self.assertEqual(queues["runs_historical_archive"]["gate_effect"], "advisory")
            self.assertEqual(report["gate_effect"], "advisory")
            self.assertIn(report["status"], {"pass", "attention"})

    def test_repo_health_freshness_snapshots_are_noncanonical_run_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "example.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["answer"],
                        "properties": {"answer": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            run_report = vault / "runs" / "legacy-run" / "repo-health-artifact-freshness-report-check.json"
            run_report.parent.mkdir(parents=True, exist_ok=True)
            run_report.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/example.schema.json",
                        "artifact_kind": "artifact_freshness_report",
                        "generated_at": "2026-04-24T12:00:00Z",
                        "producer": "ops.scripts.artifact_freshness_runtime",
                        "source_command": "make artifact-freshness-check",
                        "source_revision": "unknown",
                        "source_tree_fingerprint": "historical",
                        "input_fingerprints": {"policy": "historical"},
                        "schema_version": 1,
                        "artifact_status": "current",
                        "retention_policy": "canonical_report",
                        "encoding": "utf-8",
                        "currentness": {
                            "status": "current",
                            "checked_at": "2026-04-24T12:00:00Z",
                        },
                        "answer": 1,
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context(), mtime_source="embedded_currentness")
            record = next(
                item
                for item in report["artifact_records"]
                if item["path"].endswith("repo-health-artifact-freshness-report-check.json")
            )

            self.assertEqual(record["schema_validation_status"], "not_applicable")
            self.assertEqual(record["schema_contract"]["classification"], "noncanonical_archived_run_note")
            self.assertEqual(record["contract_issue_class"], "clean")
            self.assertEqual(record["gate_effect"], "none")
            self.assertEqual(record["stable_contract_issues"], [])
            self.assertEqual(record["issues"], [])

    def test_report_normalizes_missing_generated_at_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "schemas" / "legacy.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                    }
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "legacy-no-generated-at.json").write_text(
                json.dumps({"$schema": "ops/schemas/legacy.schema.json"}),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            missing_generated_at = next(
                item for item in report["top_debt"] if item["issue"] == "missing_generated_at"
            )

            self.assertEqual(
                missing_generated_at["recommended_next_action"],
                "backfill_generated_at_or_mark_legacy_noncanonical",
            )

    def test_report_resolves_bundled_alias_for_cyclonedx_uri_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "cyclonedx-bom.json").write_text(
                json.dumps(
                    {
                        "$schema": CYCLONEDX_16_SCHEMA_URI,
                        "bomFormat": "CycloneDX",
                        "specVersion": "1.6",
                        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000001",
                        "version": 1,
                        "metadata": {
                            "timestamp": "2999-01-01T00:00:00Z",
                            "component": {
                                "type": "application",
                                "bom-ref": "pkg:generic/sample@0.1.0",
                                "name": "sample",
                                "version": "0.1.0",
                                "purl": "pkg:generic/sample@0.1.0",
                            },
                            "tools": {"components": []},
                            "properties": [],
                        },
                        "components": [],
                        "dependencies": [],
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/cyclonedx-bom.json"
            )

            self.assertEqual(record["schema_validation_status"], "pass")
            self.assertNotIn("schema_unavailable", record["issues"])
            self.assertEqual(report["summary"]["schema_unavailable_artifact_count"], 0)

    def test_report_accepts_cyclonedx_embedded_artifact_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "cyclonedx-bom.json").write_text(
                json.dumps(
                    {
                        "$schema": CYCLONEDX_16_SCHEMA_URI,
                        "bomFormat": "CycloneDX",
                        "specVersion": "1.6",
                        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000001",
                        "version": 1,
                        "metadata": {
                            "timestamp": "2026-04-24T12:00:00Z",
                            "component": {
                                "type": "application",
                                "bom-ref": "pkg:generic/sample@0.1.0",
                                "name": "sample",
                                "version": "0.1.0",
                                "purl": "pkg:generic/sample@0.1.0",
                            },
                            "tools": {"components": []},
                            "properties": [
                                {
                                    "name": "urn:openai:artifact-envelope",
                                    "value": json.dumps(
                                        {
                                            "$schema": CYCLONEDX_16_SCHEMA_URI,
                                            "artifact_kind": "cyclonedx_sbom",
                                            "generated_at": "2999-01-01T00:00:00Z",
                                            "producer": "ops.scripts.cyclonedx_sbom",
                                            "source_command": "python -m ops.scripts.supply_chain.cyclonedx_sbom",
                                            "source_revision": "source_package_without_git",
                                            "source_tree_fingerprint": release_source_tree_fingerprint(vault),
                                            "input_fingerprints": {"policy": "abc"},
                                            "schema_version": 1,
                                            "artifact_status": "current",
                                            "retention_policy": "canonical_report",
                                            "encoding": "utf-8",
                                            "currentness": {
                                                "status": "current",
                                                "checked_at": "2999-01-01T00:00:00Z",
                                            },
                                        },
                                        ensure_ascii=False,
                                        sort_keys=True,
                                    ),
                                }
                            ],
                        },
                        "components": [],
                        "dependencies": [],
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            record = next(
                item for item in report["artifact_records"] if item["path"] == "ops/reports/cyclonedx-bom.json"
            )

            self.assertEqual(record["artifact_kind"], "cyclonedx_sbom")
            self.assertTrue(record["has_generated_at"])
            self.assertTrue(record["has_artifact_envelope"])
            self.assertEqual(record["currentness_status"], "current")
            self.assertEqual(record["schema_validation_status"], "pass")
            self.assertEqual(record["issues"], [])

    def test_freshness_write_report_validates_schema_and_stays_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report, "reports/freshness/report.json")

            self.assertEqual(destination, (vault / "reports" / "freshness" / "report.json").resolve())
            self.assertTrue(destination.exists())


if __name__ == "__main__":
    unittest.main()
