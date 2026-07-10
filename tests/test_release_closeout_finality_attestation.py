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

from ops.scripts.core.artifact_binding_runtime import (
    CONTENT_BINDING_MODE,
    REVISION_BINDING_MODE,
    binding_file_digest,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_closeout_finality_attestation import (
    BATCH_MANIFEST_PATH,
    DEFAULT_OUT,
    EXTERNAL_REPORT_MANIFEST_PATH,
    FIXED_POINT_REPORT_PATH,
    SEALED_PREFLIGHT_PATH,
    SELF_CHECK_PATH,
    build_report,
    main,
    verify_attestation,
    verify_attestation_report,
    write_report,
)
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


def _binding_digest(path: Path, binding_mode: str = CONTENT_BINDING_MODE) -> str:
    return binding_file_digest(
        path,
        binding_mode=binding_mode,
    )[1]


class ReleaseCloseoutFinalityAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (self.vault / "external-reports").mkdir(parents=True, exist_ok=True)
        self._copy_support_file("ops/schemas/release-closeout-finality-attestation.schema.json")
        self._copy_support_file("ops/policies/release-closeout-fixed-point.json")

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
        self._write_json(
            generated_path,
            {
                "artifact_kind": "generated_artifact_index",
                "generated_at": "2026-05-09T12:00:00Z",
                "source_revision": "before",
                "currentness": {"checked_at": "2026-05-09T12:00:00Z"},
                "status": "pass",
            },
        )
        self._write_json(
            BATCH_MANIFEST_PATH,
            {
                "schema_version": 2,
                "artifact_kind": "release_closeout_batch_manifest",
                "producer": "ops.scripts.release_closeout_batch_manifest",
                "status": "pass",
                "release_authority_status": "clean_pass",
                "semantic_release_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "artifacts": [],
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
        binding_mode_map = {
            generated_path: CONTENT_BINDING_MODE,
            BATCH_MANIFEST_PATH: REVISION_BINDING_MODE,
            SELF_CHECK_PATH: CONTENT_BINDING_MODE,
        }
        binding_map = {
            path: _binding_digest(self.vault / path, binding_mode_map[path])
            for path in digest_map
        }
        self._write_json(
            FIXED_POINT_REPORT_PATH,
            {
                "schema_version": 2,
                "artifact_kind": "release_closeout_fixed_point_report",
                "producer": "ops.scripts.release_closeout_fixed_point",
                "status": "pass",
                "artifact_status": "current",
                "currentness": {"status": "current"},
                "execution_pass_count": 1,
                "tracked_artifacts": [
                    {"path": path, "binding_mode": binding_mode_map[path]}
                    for path in sorted(digest_map)
                ],
                "raw_digest_map": digest_map,
                "binding_digest_map": binding_map,
                "binding_mode_map": binding_mode_map,
                "execution": {
                    "status": "pass",
                    "raw_digest_map": digest_map,
                    "binding_digest_map": binding_map,
                    "binding_mode_map": binding_mode_map,
                },
            },
        )
        return digest_map

    def _rebind_fixed_point_to_current_batch_and_self_check(self) -> None:
        fixed_point = json.loads((self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8"))
        raw_digest_map = fixed_point.get("raw_digest_map")
        raw_digest_map = raw_digest_map if isinstance(raw_digest_map, dict) else {}
        raw_digest_map[BATCH_MANIFEST_PATH] = _sha256(self.vault / BATCH_MANIFEST_PATH)
        raw_digest_map[SELF_CHECK_PATH] = _sha256(self.vault / SELF_CHECK_PATH)
        fixed_point["raw_digest_map"] = raw_digest_map
        binding_mode_map = fixed_point["binding_mode_map"]
        fixed_point["tracked_artifacts"] = [
            {"path": path, "binding_mode": binding_mode_map[path]}
            for path in sorted(raw_digest_map)
        ]
        fixed_point["binding_digest_map"] = {
            path: _binding_digest(self.vault / path, binding_mode_map[path])
            for path in sorted(raw_digest_map)
        }
        fixed_point["execution"].update(
            {
                "raw_digest_map": fixed_point["raw_digest_map"],
                "binding_digest_map": fixed_point["binding_digest_map"],
                "binding_mode_map": fixed_point["binding_mode_map"],
            }
        )
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

    def _batch_artifact(self, rel_path: str, *, role: str) -> dict[str, str]:
        raw_digest = _sha256(self.vault / rel_path)
        return {
            "path": rel_path,
            "raw_digest": raw_digest,
            "binding_digest": _binding_digest(self.vault / rel_path),
            "binding_mode": CONTENT_BINDING_MODE,
            "role": role,
        }

    def test_finality_attestation_binds_fixed_point_batch_self_check_and_tracked_map(self) -> None:
        digest_map = self._seed_finality_inputs()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["finality_status"], "pass")
        self.assertEqual(report["finality_failures"], [])
        self.assertEqual(report["fixed_point_report"]["raw_digest"], _sha256(self.vault / FIXED_POINT_REPORT_PATH))
        self.assertEqual(report["batch_manifest"]["raw_digest"], _sha256(self.vault / BATCH_MANIFEST_PATH))
        self.assertEqual(report["self_check"]["raw_digest"], _sha256(self.vault / SELF_CHECK_PATH))
        self.assertEqual(report["tracked_raw_digest_map"], digest_map)
        self.assertEqual(sorted(report["tracked_binding_digest_map"]), sorted(digest_map))
        self.assertEqual(
            report["tracked_binding_mode_map"][BATCH_MANIFEST_PATH],
            "revision",
        )
        self.assertEqual(report["fixed_point_authority_status"], "ok")
        self.assertTrue(report["matches_fixed_point_binding_digest_map"])
        self.assertNotIn("tracked_digest_map", report)
        self.assertNotIn("matches_fixed_point_digest_map", report)
        self.assertNotIn("digest", report["fixed_point_report"])
        self.assertNotIn("digest", report["batch_manifest"])
        self.assertNotIn("digest", report["self_check"])
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

        write_report(self.vault, report)
        ok, failures = verify_attestation(self.vault)
        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])

    def test_finality_verify_ignores_raw_drift_for_content_bound_artifact(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {
                "artifact_kind": "generated_artifact_index",
                "generated_at": "2026-05-09T12:01:00Z",
                "source_revision": "raw-envelope-alias-only",
                "currentness": {"checked_at": "2026-05-09T12:01:00Z"},
                "status": "pass",
            },
        )

        ok, failures = verify_attestation(self.vault)

        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])
        diagnostics = verify_attestation_report(self.vault)
        self.assertEqual(diagnostics["status"], "pass")
        self.assertEqual(diagnostics["binding_digest_mismatches"], [])
        self.assertNotIn("raw_digest_mismatches", diagnostics)

    def test_finality_verify_uses_batch_artifact_binding_mode_only(self) -> None:
        self._seed_finality_inputs()
        generated_path = "ops/reports/generated-artifact-index.json"
        batch_payload = json.loads((self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8"))
        batch_payload["artifacts"] = [
            self._batch_artifact(generated_path, role="primary_evidence")
        ]
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)
        batch_digest = _sha256(self.vault / BATCH_MANIFEST_PATH)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {"batch_manifest_fingerprint": batch_digest},
            },
        )
        self._rebind_fixed_point_to_current_batch_and_self_check()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        self._write_json(
            generated_path,
            {
                "artifact_kind": "generated_artifact_index",
                "generated_at": "2026-05-09T12:01:00Z",
                "source_revision": "raw-envelope-alias-only",
                "currentness": {"checked_at": "2026-05-09T12:01:00Z"},
                "status": "pass",
            },
        )

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "pass")
        self.assertEqual(diagnostics["failures"], [])
        self.assertNotIn("batch_manifest_artifact_raw_digest_mismatches", diagnostics)
        self.assertEqual(
            diagnostics["batch_manifest_artifact_binding_mismatches"], []
        )

    def test_finality_verify_rejects_raw_batch_manifest_component_drift(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        batch_payload = json.loads((self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8"))
        batch_payload["generated_at"] = "2026-05-09T12:01:00Z"
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        self.assertEqual(
            diagnostics["failures"],
            ["batch_manifest_raw_binding_mismatch"],
        )
        self.assertEqual(
            [
                (item["field"], item["path"])
                for item in diagnostics["component_binding_mismatches"]
            ],
            [("batch_manifest", BATCH_MANIFEST_PATH)],
        )
        self.assertEqual(diagnostics["binding_digest_mismatches"], [])

    def test_finality_verify_rejects_v1_as_current_authority(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        report["schema_version"] = 1
        self._write_json(DEFAULT_OUT, report)

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        self.assertEqual(
            diagnostics["failures"],
            ["attestation_load_status:unsupported_schema_version"],
        )

    def test_finality_build_rejects_v1_fixed_point_as_current_authority(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        fixed_point["schema_version"] = 1
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["fixed_point_authority_status"], "unsupported_schema_version")
        self.assertEqual(report["finality_status"], "fail")
        self.assertIn("fixed_point_not_current_v2_authority", report["finality_failures"])

    def test_finality_verify_rejects_tampered_batch_manifest_component_raw_digest(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        attestation_payload = json.loads((self.vault / DEFAULT_OUT).read_text(encoding="utf-8"))
        attestation_payload["batch_manifest"]["raw_digest"] = "0" * 64
        self._write_json(DEFAULT_OUT, attestation_payload)

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        self.assertEqual(
            diagnostics["failures"],
            ["batch_manifest_raw_binding_mismatch"],
        )
        self.assertNotIn("raw_digest_mismatches", diagnostics)
        self.assertEqual(
            [
                item["field"]
                for item in diagnostics["component_binding_mismatches"]
            ],
            ["batch_manifest"],
        )

    def test_finality_verify_rejects_tampered_component_and_tracked_digest(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        attestation_payload = json.loads((self.vault / DEFAULT_OUT).read_text(encoding="utf-8"))
        bogus_digest = "0" * 64
        attestation_payload["batch_manifest"]["raw_digest"] = bogus_digest
        attestation_payload["tracked_raw_digest_map"][BATCH_MANIFEST_PATH] = bogus_digest
        self._write_json(DEFAULT_OUT, attestation_payload)

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        self.assertIn(
            "batch_manifest_raw_binding_mismatch",
            diagnostics["failures"],
        )
        self.assertNotIn("raw_digest_mismatches", diagnostics)

    def test_finality_verify_fails_after_batch_manifest_content_drift(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        batch_payload = json.loads((self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8"))
        batch_payload["semantic_release_status"] = "changed_after_finality"
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)

        ok, failures = verify_attestation(self.vault)

        self.assertFalse(ok)
        self.assertIn("batch_manifest_raw_binding_mismatch", failures)
        self.assertIn("tracked_binding_digest_map_current_mismatch", failures)
        self.assertIn("fixed_point_binding_digest_map_current_mismatch", failures)

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
        fixed_point["raw_digest_map"][generated_path] = _sha256(
            self.vault / generated_path
        )
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)
        self._rebind_fixed_point_to_current_batch_and_self_check()
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
        self.assertIn("tracked_binding_digest_map_current_mismatch", failures)
        self.assertIn("fixed_point_binding_digest_map_current_mismatch", failures)
        diagnostics = verify_attestation_report(self.vault)
        self.assertNotEqual(diagnostics["binding_digest_mismatches"], [])
        self.assertNotIn("raw_digest_mismatches", diagnostics)

    def test_finality_attestation_prefers_batch_status_v2_axes(self) -> None:
        self._seed_finality_inputs()
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
        self._rebind_fixed_point_to_current_batch_and_self_check()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["finality_status"], "pass")
        self.assertEqual(report["batch_manifest"]["status"], "pass")
        self.assertEqual(report["batch_manifest"]["release_authority_status"], "clean_pass")
        self.assertEqual(report["batch_manifest"]["semantic_release_status"], "clean_pass")
        self.assertEqual(report["batch_manifest"]["sealed_release_status"], "sealed_clean_pass")

    @pytest.mark.release_closeout_regression
    def test_finality_verify_fails_after_tracked_content_drift(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {"artifact_kind": "generated_artifact_index", "status": "changed_after_finality"},
        )

        ok, failures = verify_attestation(self.vault)

        self.assertFalse(ok)
        self.assertIn("tracked_binding_digest_map_current_mismatch", failures)
        self.assertIn("fixed_point_binding_digest_map_current_mismatch", failures)

    def test_finality_verify_classifies_batch_freshness_index_cohort_binding_drift(
        self,
    ) -> None:
        self._seed_finality_inputs()
        freshness_path = "ops/reports/artifact-freshness-report.json"
        self._write_json(
            freshness_path,
            {"artifact_kind": "artifact_freshness_report", "status": "old"},
        )
        batch_payload = json.loads((self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8"))
        batch_payload["artifacts"] = [
            self._batch_artifact(freshness_path, role="primary_evidence")
        ]
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)
        batch_digest = _sha256(self.vault / BATCH_MANIFEST_PATH)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {"batch_manifest_fingerprint": batch_digest},
            },
        )
        self._rebind_fixed_point_to_current_batch_and_self_check()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)
        self._write_json(
            "ops/reports/generated-artifact-index.json",
            {
                "artifact_kind": "generated_artifact_index",
                "generated_at": "2026-05-09T12:01:00Z",
                "source_revision": "raw-envelope-alias-only",
                "currentness": {"checked_at": "2026-05-09T12:01:00Z"},
                "status": "pass",
            },
        )
        self._write_json(
            freshness_path,
            {"artifact_kind": "artifact_freshness_report", "status": "new"},
        )

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        classification = diagnostics["failure_classification"]
        self.assertEqual(
            classification["primary_class"],
            "batch_manifest_freshness_index_cohort_binding_mismatch",
        )
        self.assertNotIn(
            "fixed_point_tracked_writer_binding_mismatch",
            classification["classes"],
        )
        self.assertEqual(
            classification["recommended_fixed_point_initial_targets"],
            ["artifact-freshness"],
        )
        self.assertIn("release-closeout-fixed-point", classification["recommended_targets"])
        self.assertIn(
            "batch_manifest_artifact_binding_current_mismatch",
            diagnostics["failures"],
        )

    def test_finality_verify_classifies_fixed_point_tracked_writer_drift(self) -> None:
        self._seed_finality_inputs()
        generated_path = "ops/reports/generated-artifact-index.json"
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        self._write_json(
            generated_path,
            {"artifact_kind": "generated_artifact_index", "status": "changed"},
        )

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        classification = diagnostics["failure_classification"]
        self.assertIn(
            "fixed_point_tracked_writer_binding_mismatch",
            classification["classes"],
        )
        self.assertIn(
            {
                "path": generated_path,
                "fixed_point_binding_digest": report["tracked_binding_digest_map"][
                    generated_path
                ],
                "current_binding_digest": _binding_digest(
                    self.vault / generated_path
                ),
                "binding_mode": "content",
                "writer_target": "generated-artifact-index-body",
            },
            classification["fixed_point_tracked_writer_binding_mismatches"],
        )
        self.assertIn(
            "generated-artifact-index-body",
            classification["recommended_fixed_point_initial_targets"],
        )

    def test_finality_verify_classifies_sealed_preflight_artifact_mismatch(self) -> None:
        self._seed_finality_inputs()
        self._write_json(
            SEALED_PREFLIGHT_PATH,
            {
                "artifact_kind": "release_closeout_sealed_rehearsal_check",
                "status": "pass",
                "preflight": {"preflight_status": "sealed_clean_pass"},
                "currentness": {"status": "current"},
            },
        )
        sealed_preflight_binding_digest = _binding_digest(
            self.vault / SEALED_PREFLIGHT_PATH
        )
        batch_payload = json.loads((self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8"))
        batch_payload["artifacts"] = [
            self._batch_artifact(SEALED_PREFLIGHT_PATH, role="sealed_preflight")
        ]
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)
        batch_digest = _sha256(self.vault / BATCH_MANIFEST_PATH)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {"batch_manifest_fingerprint": batch_digest},
            },
        )
        self._rebind_fixed_point_to_current_batch_and_self_check()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)
        self._write_json(
            SEALED_PREFLIGHT_PATH,
            {
                "artifact_kind": "release_closeout_sealed_rehearsal_check",
                "status": "pass",
                "preflight": {"preflight_status": "sealed_clean_pass"},
                "currentness": {"status": "current", "source_tree_fingerprint": "changed"},
            },
        )

        diagnostics = verify_attestation_report(self.vault)

        classification = diagnostics["failure_classification"]
        self.assertIn("sealed_preflight_artifact_mismatch", classification["classes"])
        self.assertIn(
            {
                "path": SEALED_PREFLIGHT_PATH,
                "role": "sealed_preflight",
                "batch_manifest_binding_digest": sealed_preflight_binding_digest,
                "current_binding_digest": _binding_digest(
                    self.vault / SEALED_PREFLIGHT_PATH
                ),
                "binding_mode": "content",
            },
            classification["sealed_preflight_artifact_binding_mismatches"],
        )
        self.assertIn(
            "release-authority-sealed-preflight",
            classification["recommended_targets"],
        )

    def test_finality_verify_classifies_stale_sealed_preflight_report(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)
        self._write_json(
            SEALED_PREFLIGHT_PATH,
            {
                "artifact_kind": "release_closeout_sealed_rehearsal_check",
                "status": "fail",
                "preflight": {"preflight_status": "binding_failed"},
                "currentness": {"status": "current"},
            },
        )

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        self.assertIn("sealed_preflight_not_current", diagnostics["failures"])
        classification = diagnostics["failure_classification"]
        self.assertEqual(
            classification["primary_class"],
            "sealed_preflight_artifact_mismatch",
        )
        self.assertEqual(
            classification["recommended_targets"],
            ["release-authority-sealed-preflight", "release-closeout-finality-verify"],
        )

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
