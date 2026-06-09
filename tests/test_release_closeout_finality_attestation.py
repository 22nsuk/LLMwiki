from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any

import pytest
from ops.scripts.release_closeout_finality_attestation import (
    BATCH_MANIFEST_PATH,
    DEFAULT_OUT,
    EXTERNAL_REPORT_MANIFEST_PATH,
    FIXED_POINT_REPORT_PATH,
    SELF_CHECK_PATH,
    build_report,
    main,
    verify_attestation,
    verify_attestation_report,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-closeout-finality-attestation.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 9, 12, 0, tzinfo=dt.UTC),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReleaseCloseoutFinalityAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (self.vault / "external-reports").mkdir(parents=True, exist_ok=True)
        self._copy_support_file("ops/schemas/release-closeout-finality-attestation.schema.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def _seed_finality_inputs(self) -> dict[str, str]:
        generated_path = "ops/reports/generated-artifact-index.json"
        self._write_json(generated_path, {"artifact_kind": "generated_artifact_index", "status": "pass"})
        self._write_json(
            BATCH_MANIFEST_PATH,
            {
                "status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "finality": {
                    "finality_required": True,
                    "finality_attestation_path": DEFAULT_OUT,
                    "binding_authority": "release-closeout-finality-attestation",
                    "summary": "finality attestation owns digest binding",
                },
            },
        )
        batch_digest = _sha256(self.vault / BATCH_MANIFEST_PATH)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {"batch_manifest_fingerprint": batch_digest},
            },
        )
        self._write_json(
            EXTERNAL_REPORT_MANIFEST_PATH,
            {
                "artifact_kind": "external_report_reference_manifest",
                "distribution_provenance": {
                    "mode": "strict_review_release",
                    "status": "basis_current_match",
                },
            },
        )
        digest_map = {
            generated_path: _sha256(self.vault / generated_path),
            BATCH_MANIFEST_PATH: batch_digest,
            SELF_CHECK_PATH: _sha256(self.vault / SELF_CHECK_PATH),
        }
        self._write_json(
            FIXED_POINT_REPORT_PATH,
            {
                "status": "pass",
                "converged": True,
                "converged_iteration": 2,
                "tracked_artifacts": [{"path": path} for path in sorted(digest_map)],
                "final_digest_map": digest_map,
            },
        )
        return digest_map

    def test_finality_attestation_binds_fixed_point_batch_self_check_and_tracked_map(self) -> None:
        digest_map = self._seed_finality_inputs()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["finality_status"], "pass")
        self.assertEqual(report["finality_failures"], [])
        self.assertEqual(report["fixed_point_report"]["digest"], _sha256(self.vault / FIXED_POINT_REPORT_PATH))
        self.assertEqual(report["batch_manifest"]["digest"], _sha256(self.vault / BATCH_MANIFEST_PATH))
        self.assertEqual(report["self_check"]["digest"], _sha256(self.vault / SELF_CHECK_PATH))
        self.assertEqual(report["tracked_digest_map"], digest_map)
        self.assertEqual(sorted(report["tracked_semantic_digest_map"]), sorted(digest_map))
        self.assertEqual(sorted(report["tracked_semantic_digest_modes"]), sorted(digest_map))
        self.assertTrue(report["matches_fixed_point_digest_map"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

        write_report(self.vault, report)
        ok, failures = verify_attestation(self.vault)
        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])

    def test_finality_verify_allows_envelope_only_tracked_digest_drift(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {
                "artifact_kind": "generated_artifact_index",
                "generated_at": "2026-05-09T12:01:00Z",
                "input_fingerprints": {"clock": "changed"},
                "status": "pass",
            },
        )

        ok, failures = verify_attestation(self.vault)

        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])
        diagnostics = verify_attestation_report(self.vault)
        self.assertEqual(diagnostics["status"], "pass")
        self.assertTrue(diagnostics["semantic_fallback_used"])
        self.assertEqual(
            [
                item["path"]
                for item in diagnostics["raw_digest_mismatches_covered_by_semantic_digest"]
            ],
            ["ops/reports/generated-artifact-index.json"],
        )

    def test_finality_verify_fails_after_nested_provenance_drift(self) -> None:
        self._seed_finality_inputs()
        generated_path = "ops/reports/generated-artifact-index.json"
        self._write_json(
            generated_path,
            {
                "artifact_kind": "generated_artifact_index",
                "details": {"input_fingerprints": {"clock": "before"}},
                "status": "pass",
            },
        )
        fixed_point = json.loads((self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8"))
        fixed_point["final_digest_map"][generated_path] = _sha256(self.vault / generated_path)
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        self._write_json(
            generated_path,
            {
                "artifact_kind": "generated_artifact_index",
                "details": {"input_fingerprints": {"clock": "after"}},
                "status": "pass",
            },
        )

        ok, failures = verify_attestation(self.vault)

        self.assertFalse(ok)
        self.assertIn("tracked_digest_map_current_mismatch", failures)
        self.assertIn("fixed_point_digest_map_current_mismatch", failures)
        diagnostics = verify_attestation_report(self.vault)
        self.assertFalse(diagnostics["semantic_fallback_used"])
        self.assertEqual(
            [item["path"] for item in diagnostics["raw_digest_mismatches"]],
            [generated_path],
        )

    def test_finality_attestation_prefers_batch_status_v2_axes(self) -> None:
        self._seed_finality_inputs()
        generated_path = "ops/reports/generated-artifact-index.json"
        batch_payload = json.loads((self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8"))
        batch_payload.update(
            {
                "status": "fail",
                "release_authority_status": "blocked",
                "semantic_release_status": "blocked",
                "sealed_release_status": "unsealed_release_blocked",
                "status_v2": {
                    "schema_version": 2,
                    "compatibility_status_value": "pass",
                    "status_axes": {
                        "release_authority_status": "clean_pass",
                        "semantic_release_status": "clean_pass",
                        "sealed_release_status": "sealed_clean_pass",
                    },
                    "blocker_reason_ids": [],
                },
            }
        )
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)
        batch_digest = _sha256(self.vault / BATCH_MANIFEST_PATH)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {"batch_manifest_fingerprint": batch_digest},
            },
        )
        digest_map = {
            generated_path: _sha256(self.vault / generated_path),
            BATCH_MANIFEST_PATH: batch_digest,
            SELF_CHECK_PATH: _sha256(self.vault / SELF_CHECK_PATH),
        }
        self._write_json(
            FIXED_POINT_REPORT_PATH,
            {
                "status": "pass",
                "converged": True,
                "converged_iteration": 2,
                "tracked_artifacts": [{"path": path} for path in sorted(digest_map)],
                "final_digest_map": digest_map,
            },
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["finality_status"], "pass")
        self.assertEqual(report["batch_manifest"]["status"], "pass")
        self.assertEqual(report["batch_manifest"]["release_authority_status"], "clean_pass")
        self.assertEqual(report["batch_manifest"]["semantic_release_status"], "clean_pass")
        self.assertEqual(report["batch_manifest"]["sealed_release_status"], "sealed_clean_pass")

    def test_finality_verify_fails_after_tracked_digest_drift(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {"artifact_kind": "generated_artifact_index", "status": "changed_after_finality"},
        )

        ok, failures = verify_attestation(self.vault)

        self.assertFalse(ok)
        self.assertIn("tracked_digest_map_current_mismatch", failures)
        self.assertIn("fixed_point_digest_map_current_mismatch", failures)

    def test_verify_no_fail_writes_ci_diagnostic_for_missing_attestation(self) -> None:
        verify_out = "tmp/release-closeout-finality-verify-ci.json"

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [
                    "--vault",
                    str(self.vault),
                    "--verify",
                    "--verify-out",
                    verify_out,
                    "--no-fail",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"status": "fail"', stderr.getvalue())
        payload = json.loads((self.vault / verify_out).read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "fail")
        self.assertIn("attestation_load_status:missing", payload["failures"])


if __name__ == "__main__":
    unittest.main()
