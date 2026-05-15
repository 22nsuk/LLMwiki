"""Contract tests: release evidence closeout self-check artifact generation.

Verifies that the self-check artifact correctly captures batch, cohort, and
digest state at closeout time for drift detection across runs.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.release_evidence_closeout_self_check import build_report, main, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.release_sealing]

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-evidence-closeout-self-check.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 4, 9, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseEvidenceCloseoutSelfCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, rel_path: str, payload: dict[str, object]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _digest(self, rel_path: str) -> str:
        return hashlib.sha256((self.vault / rel_path).read_bytes()).hexdigest()

    def _write_closeout_inputs(
        self,
        *,
        batch_overrides: dict[str, object] | None = None,
        cohort_overrides: dict[str, object] | None = None,
    ) -> None:
        batch_manifest: dict[str, object] = {
            "summary": {"artifact_count": 10},
            "artifacts": [],
            "input_fingerprints": {"release_smoke": "a" * 64},
            "release_authority_status": "clean_pass",
            "sealed_release_status": "sealed_clean_pass",
            "distribution_package": {"status": "materialized"},
        }
        if batch_overrides:
            batch_manifest.update(batch_overrides)

        cohort: dict[str, object] = {
            "components": [{"name": "release_smoke"}],
            "input_fingerprints": {"release_smoke": "a" * 64},
            "clean_lane_contract": {"status": "pass"},
            "summary": {"accepted_risk_family_count": 0},
        }
        if cohort_overrides:
            cohort.update(cohort_overrides)

        self._write_json("ops/reports/release-closeout-batch-manifest.json", batch_manifest)
        self._write_json("ops/reports/release-evidence-cohort.json", cohort)

    def test_build_report_creates_valid_artifact(self) -> None:
        """Self-check artifact validates against schema."""
        context = fixed_context()
        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            context,
        )

        self.assertIsInstance(report, dict)
        self.assertEqual(
            report["$schema"],
            "ops/schemas/release-evidence-closeout-self-check.schema.json",
        )
        self.assertEqual(report["artifact_kind"], "release_evidence_closeout_self_check")
        self.assertEqual(report["schema_version"], 1)
        self.assertIsInstance(report["input_fingerprints"], dict)
        self.assertIn("batch_manifest", report["input_fingerprints"])
        self.assertIn("evidence_cohort", report["input_fingerprints"])

    def test_self_check_captures_input_paths(self) -> None:
        """Closeout inputs section records source paths."""
        context = fixed_context()
        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            context,
        )

        inputs = report["closeout_inputs"]
        self.assertEqual(inputs["batch_manifest_path"], "ops/reports/release-closeout-batch-manifest.json")
        self.assertEqual(inputs["evidence_cohort_path"], "ops/reports/release-evidence-cohort.json")

    def test_self_check_has_drift_watch_list(self) -> None:
        """Drift watch list captures key fields for cross-run comparison."""
        context = fixed_context()
        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            context,
        )

        watch_list = report["drift_watch_list"]
        self.assertIsInstance(watch_list, list)
        self.assertGreater(len(watch_list), 0)

        # Each watch item has required fields
        for item in watch_list:
            self.assertIn("field_path", item)
            self.assertIn("snapshot_value", item)
            self.assertIn("check_description", item)

    def test_self_check_capture_schema_valid(self) -> None:
        """Snapshot section captures digest fields for comparison."""
        context = fixed_context()
        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            context,
        )

        snapshot = report["closeout_snapshot"]
        self.assertIn("batch_manifest_component_count", snapshot)
        self.assertIn("cohort_component_count", snapshot)
        self.assertIn("batch_manifest_input_digest", snapshot)
        self.assertIn("cohort_input_digest", snapshot)
        self.assertIn("clean_lane_contract_status", snapshot)

    def test_write_report_validates_and_writes(self) -> None:
        """Written artifact passes schema validation."""
        context = fixed_context()
        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            context,
        )

        out_path = write_report(self.vault, report, "ops/reports/release-evidence-closeout-self-check.json")
        self.assertTrue(out_path.exists())

        # Reload and validate
        written = json.loads(out_path.read_text())
        schema = load_schema(SCHEMA_PATH)
        errors = validate_with_schema(written, schema)
        self.assertEqual(errors, [], f"Schema validation failed: {errors}")

    def test_main_cli_entry(self) -> None:
        """CLI entry point creates self-check artifact."""
        exit_code = main(
            [
                "--vault",
                self.vault.as_posix(),
                "--batch-manifest",
                "ops/reports/release-closeout-batch-manifest.json",
                "--evidence-cohort",
                "ops/reports/release-evidence-cohort.json",
                "--out",
                "ops/reports/test-self-check.json",
            ]
        )

        self.assertEqual(exit_code, 0)
        destination = self.vault / "ops" / "reports" / "test-self-check.json"
        self.assertTrue(destination.exists())

    def test_drift_watch_captures_release_authority_status(self) -> None:
        """Drift watch list includes release_authority_status snapshot."""
        self._write_closeout_inputs()
        context = fixed_context()
        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            context,
        )

        watch_list = report["drift_watch_list"]
        paths = [item["field_path"] for item in watch_list]
        self.assertIn("batch_manifest.release_authority_status", paths)
        self.assertIn("batch_manifest.sealed_release_status", paths)
        self.assertIn("batch_manifest.distribution_package.status", paths)
        snapshot_by_path = {item["field_path"]: item["snapshot_value"] for item in watch_list}
        self.assertEqual(snapshot_by_path["batch_manifest.release_authority_status"], "clean_pass")
        self.assertEqual(snapshot_by_path["batch_manifest.sealed_release_status"], "sealed_clean_pass")
        self.assertEqual(snapshot_by_path["batch_manifest.distribution_package.status"], "materialized")
        self.assertIsNotNone(snapshot_by_path["batch_manifest.release_authority_status"])
        self.assertNotIn("batch_manifest.summary.release_authority_status", paths)

    def test_missing_required_dotted_watch_path_fails_status(self) -> None:
        """Missing required dotted watch paths fail the self-check."""
        self._write_closeout_inputs(batch_overrides={"release_authority_status": None})
        batch_path = self.vault / "ops" / "reports" / "release-closeout-batch-manifest.json"
        batch_manifest = json.loads(batch_path.read_text(encoding="utf-8"))
        batch_manifest.pop("release_authority_status")
        batch_path.write_text(json.dumps(batch_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            fixed_context(),
        )

        self.assertEqual(report["status"]["result"], "fail")
        self.assertIn(
            "batch_manifest.release_authority_status",
            report["status"]["missing_required_watch_paths"],
        )
        snapshot_by_path = {item["field_path"]: item["snapshot_value"] for item in report["drift_watch_list"]}
        self.assertIsNone(snapshot_by_path["batch_manifest.release_authority_status"])

    def test_batch_manifest_component_count_uses_summary_artifact_count(self) -> None:
        """Batch manifest component count comes from summary.artifact_count."""
        self._write_closeout_inputs(batch_overrides={"summary": {"artifact_count": 10}, "artifacts": []})

        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            fixed_context(),
        )

        self.assertEqual(report["closeout_snapshot"]["batch_manifest_component_count"], 10)

    def test_batch_artifact_digest_watch_fails_after_sealed_artifact_drift(self) -> None:
        artifact_path = "ops/reports/release-evidence-dashboard.json"
        self._write_json(artifact_path, {"artifact_kind": "release_evidence_dashboard", "status": "pass"})
        sealed_digest = self._digest(artifact_path)
        self._write_closeout_inputs(
            batch_overrides={
                "summary": {"artifact_count": 1},
                "artifacts": [{"path": artifact_path, "digest": sealed_digest}],
            }
        )

        report = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            fixed_context(),
        )

        self.assertEqual(report["status"]["result"], "pass")
        self.assertEqual(report["batch_artifact_digest_watch"]["status"], "match")
        self.assertEqual(report["batch_artifact_digest_watch"]["mismatch_count"], 0)

        self._write_json(artifact_path, {"artifact_kind": "release_evidence_dashboard", "status": "attention"})

        drifted = build_report(
            self.vault,
            "ops/reports/release-closeout-batch-manifest.json",
            "ops/reports/release-evidence-cohort.json",
            fixed_context(),
        )

        watch = drifted["batch_artifact_digest_watch"]
        self.assertEqual(drifted["status"]["result"], "fail")
        self.assertEqual(watch["status"], "mismatch")
        self.assertEqual(watch["artifact_count"], 1)
        self.assertEqual(watch["mismatch_count"], 1)
        self.assertEqual(watch["artifacts"][0]["path"], artifact_path)
        self.assertEqual(watch["artifacts"][0]["expected_digest"], sealed_digest)
        self.assertNotEqual(watch["artifacts"][0]["actual_digest"], sealed_digest)
        self.assertEqual(validate_with_schema(drifted, load_schema(SCHEMA_PATH)), [])

    def test_missing_input_documents_handled_gracefully(self) -> None:
        """Self-check handles missing input documents without error."""
        context = fixed_context()
        # Use paths that don't exist
        report = build_report(
            self.vault,
            "ops/reports/nonexistent-batch.json",
            "ops/reports/nonexistent-cohort.json",
            context,
        )

        self.assertIsNotNone(report)
        self.assertEqual(report["artifact_kind"], "release_evidence_closeout_self_check")
        # Component counts should be 0 for missing docs
        self.assertEqual(report["closeout_snapshot"]["batch_manifest_component_count"], 0)
        self.assertEqual(report["closeout_snapshot"]["cohort_component_count"], 0)
        self.assertEqual(report["status"]["result"], "fail")
