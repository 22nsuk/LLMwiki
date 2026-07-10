from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ops.scripts.core.artifact_binding_runtime import (
    CONTENT_BINDING_MODE,
    REVISION_BINDING_MODE,
    binding_file_digest,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.source_revision_runtime import (
    SourceRevision,
    resolve_source_revision,
)
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
from ops.scripts.release.release_closeout_fixed_point import (
    build_report as build_fixed_point_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-closeout-finality-attestation.schema.json"
FIXED_POINT_POLICY_PATH = "ops/policies/release-closeout-fixed-point.json"
FIXED_POINT_SCHEMA_PATH = "ops/schemas/release-closeout-fixed-point.schema.json"


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
    @staticmethod
    def _fixed_point_writer_specs() -> list[dict[str, Any]]:
        return [
            {
                "name": "generated-artifact-index",
                "target": "generated-artifact-index-body",
                "binding_mode": CONTENT_BINDING_MODE,
                "produces": ["ops/reports/generated-artifact-index.json"],
                "depends_on": [],
                "expensive_prerequisites": ["declared-prerequisite"],
            },
            {
                "name": "release-closeout-batch-manifest",
                "target": "release-closeout-batch-manifest-promote",
                "binding_mode": REVISION_BINDING_MODE,
                "produces": [BATCH_MANIFEST_PATH],
                "depends_on": ["generated-artifact-index-body"],
                "expensive_prerequisites": [],
            },
            {
                "name": "release-evidence-closeout-self-check",
                "target": "release-evidence-closeout-self-check",
                "binding_mode": CONTENT_BINDING_MODE,
                "produces": [SELF_CHECK_PATH],
                "depends_on": ["release-closeout-batch-manifest-promote"],
                "expensive_prerequisites": [],
            },
        ]

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (self.vault / "external-reports").mkdir(parents=True, exist_ok=True)
        self._copy_support_file("ops/schemas/release-closeout-finality-attestation.schema.json")
        self._copy_support_file(FIXED_POINT_SCHEMA_PATH)
        self._write_json(
            FIXED_POINT_POLICY_PATH,
            {"version": 1, "writers": self._fixed_point_writer_specs()},
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_json(self, rel_path: str, payload: Any) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _successful_fixed_point_runner(
        command: list[str],
        _cwd: Path,
        timeout_seconds: int,
        _runtime_env: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "command": command,
            "returncode": 0,
            "timed_out": False,
            "timeout_seconds": timeout_seconds,
            "termination_reason": "completed",
            "duration_ms": 1,
            "stdout_tail": "",
            "stderr_tail": "",
            "status": "pass",
        }

    def _seed_finality_inputs(self) -> dict[str, str]:
        current_revision = resolve_source_revision(self.vault).revision
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
                "source_revision": current_revision,
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
        fixed_point = build_fixed_point_report(
            self.vault,
            timeout_seconds=30,
            python_executable="python",
            context=fixed_context(),
            command_runner=self._successful_fixed_point_runner,
        )
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)
        return fixed_point["raw_digest_map"]

    def _rebind_fixed_point_to_current_batch_and_self_check(self) -> None:
        fixed_point = json.loads((self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8"))
        raw_digest_map = fixed_point.get("raw_digest_map")
        raw_digest_map = raw_digest_map if isinstance(raw_digest_map, dict) else {}
        raw_digest_map[BATCH_MANIFEST_PATH] = _sha256(self.vault / BATCH_MANIFEST_PATH)
        raw_digest_map[SELF_CHECK_PATH] = _sha256(self.vault / SELF_CHECK_PATH)
        fixed_point["raw_digest_map"] = raw_digest_map
        binding_mode_map = fixed_point["binding_mode_map"]
        name_by_path = {
            str(path): str(writer["name"])
            for writer in self._fixed_point_writer_specs()
            for path in writer["produces"]
        }
        fixed_point["tracked_artifacts"] = [
            {
                "name": name_by_path[path],
                "path": path,
                "binding_mode": binding_mode_map[path],
            }
            for path in raw_digest_map
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

    def _set_fixed_point_execution(
        self,
        fixed_point: dict[str, Any],
        *,
        selected_targets: list[str],
        result_targets: list[str],
    ) -> None:
        results_by_target = {
            str(item["target"]): item
            for item in fixed_point["execution"]["command_results"]
        }
        fixed_point["execution"]["selected_targets"] = selected_targets
        fixed_point["execution"]["command_results"] = [
            copy.deepcopy(results_by_target[target]) for target in result_targets
        ]
        selected_set = set(selected_targets)
        for writer_cost in fixed_point["duration_summary"]["writer_costs"]:
            selected = str(writer_cost["target"]) in selected_set
            writer_cost.update(
                {
                    "selected": selected,
                    "run_count": 1 if selected else 0,
                    "total_duration_ms": 1 if selected else 0,
                    "average_duration_ms": 1 if selected else 0,
                    "max_duration_ms": 1 if selected else 0,
                }
            )
        duration_summary = fixed_point["duration_summary"]
        duration_summary["command_run_count"] = len(result_targets)
        duration_summary["total_duration_ms"] = len(result_targets)
        expensive = duration_summary["expensive_prerequisites"]
        observed_expensive = [
            target for target in result_targets if target in set(expensive["targets"])
        ]
        expensive.update(
            {
                "observed_target_count": len(set(observed_expensive)),
                "run_count": len(observed_expensive),
                "total_duration_ms": len(observed_expensive),
                "summary": f"{len(observed_expensive)} prerequisite commands ran",
            }
        )

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

    def test_finality_build_rejects_duplicate_writer_execution_authority(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        fixed_point["duration_summary"]["writer_costs"][0]["run_count"] = 2
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["fixed_point_authority_status"],
            "invalid_single_pass_execution",
        )
        self.assertEqual(report["finality_status"], "fail")
        self.assertIn(
            "fixed_point_authority_status:invalid_single_pass_execution",
            report["finality_failures"],
        )

    def test_finality_build_rejects_unexpected_command_result(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        fixed_point["execution"]["command_results"].append(
            {
                "target": "undeclared-prerequisite",
                "status": "pass",
                "returncode": 0,
            }
        )
        fixed_point["duration_summary"]["command_run_count"] += 1
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["fixed_point_authority_status"],
            "invalid_single_pass_execution",
        )
        self.assertEqual(report["finality_status"], "fail")

    def test_finality_build_accepts_downstream_closed_partial_execution(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        selected_targets = fixed_point["command_sequence"][1:]
        self._set_fixed_point_execution(
            fixed_point,
            selected_targets=selected_targets,
            result_targets=selected_targets,
        )
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            validate_with_schema(
                fixed_point,
                load_schema(REPO_ROOT / FIXED_POINT_SCHEMA_PATH),
            ),
            [],
        )
        self.assertEqual(report["fixed_point_authority_status"], "ok")
        self.assertEqual(report["finality_status"], "pass")

    def test_finality_build_rejects_non_closed_partial_execution(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        first_target = fixed_point["command_sequence"][0]
        self._set_fixed_point_execution(
            fixed_point,
            selected_targets=[first_target],
            result_targets=["declared-prerequisite", first_target],
        )
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            validate_with_schema(
                fixed_point,
                load_schema(REPO_ROOT / FIXED_POINT_SCHEMA_PATH),
            ),
            [],
        )
        self.assertEqual(
            report["fixed_point_authority_status"],
            "invalid_single_pass_execution",
        )
        self.assertEqual(report["finality_status"], "fail")

    def test_finality_build_rejects_zero_execution_authority(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        self._set_fixed_point_execution(
            fixed_point,
            selected_targets=[],
            result_targets=[],
        )
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())
        schema_errors = validate_with_schema(
            fixed_point,
            load_schema(REPO_ROOT / FIXED_POINT_SCHEMA_PATH),
        )

        self.assertTrue(schema_errors)
        self.assertEqual(
            report["fixed_point_authority_status"],
            "invalid_single_pass_execution",
        )
        self.assertEqual(report["finality_status"], "fail")

    def test_finality_build_rejects_pass_execution_failure_signals(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        command_result = fixed_point["execution"]["command_results"][0]
        command_result["timed_out"] = True
        command_result["undeclared_tracked_writes"] = [BATCH_MANIFEST_PATH]
        command_result["issues"] = ["undeclared_tracked_write"]
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())
        schema_errors = validate_with_schema(
            fixed_point,
            load_schema(REPO_ROOT / FIXED_POINT_SCHEMA_PATH),
        )

        self.assertTrue(schema_errors)
        self.assertEqual(
            report["fixed_point_authority_status"],
            "invalid_single_pass_execution",
        )
        self.assertEqual(report["finality_status"], "fail")

    def test_finality_build_rejects_pass_execution_failure_reason(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        fixed_point["execution"]["reason"] = "command_failed"
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["fixed_point_authority_status"],
            "invalid_single_pass_execution",
        )
        self.assertEqual(report["finality_status"], "fail")

    def test_finality_build_rejects_policy_binding_mode_downgrade(self) -> None:
        self._seed_finality_inputs()
        batch_payload = json.loads(
            (self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8")
        )
        batch_payload["source_revision"] = "stale-revision"
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {
                    "batch_manifest_fingerprint": _sha256(
                        self.vault / BATCH_MANIFEST_PATH
                    )
                },
            },
        )
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        fixed_point["binding_mode_map"][BATCH_MANIFEST_PATH] = CONTENT_BINDING_MODE
        for item in fixed_point["tracked_artifacts"]:
            if item["path"] == BATCH_MANIFEST_PATH:
                item["binding_mode"] = CONTENT_BINDING_MODE
        self._write_json(FIXED_POINT_REPORT_PATH, fixed_point)
        self._rebind_fixed_point_to_current_batch_and_self_check()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(
            report["fixed_point_authority_status"],
            "policy_binding_contract_mismatch",
        )
        self.assertEqual(report["finality_status"], "fail")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_finality_build_rejects_writer_produces_contract_drift(self) -> None:
        self._seed_finality_inputs()
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        generated_path = "ops/reports/generated-artifact-index.json"
        cases = {
            "replaced": ["ops/reports/replaced.json"],
            "missing": [],
            "added": [generated_path, "ops/reports/extra.json"],
        }

        for case, produces in cases.items():
            with self.subTest(case=case):
                mutated = copy.deepcopy(fixed_point)
                mutated["duration_summary"]["writer_costs"][0]["produces"] = produces
                self._write_json(FIXED_POINT_REPORT_PATH, mutated)

                report = build_report(self.vault, context=fixed_context())

                self.assertEqual(
                    report["fixed_point_authority_status"],
                    "invalid_single_pass_execution",
                )
                self.assertEqual(report["finality_status"], "fail")

    def test_invalid_writer_policy_is_a_structured_finality_failure(self) -> None:
        self._seed_finality_inputs()
        valid_report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, valid_report)
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        fixed_point_revision = fixed_point["source_revision"]
        self._write_json(FIXED_POINT_POLICY_PATH, {"version": 1, "writers": []})

        with patch(
            "ops.scripts.release.release_closeout_finality_attestation.resolve_source_revision",
            return_value=SourceRevision(fixed_point_revision, "source_package_without_git"),
        ):
            report = build_report(self.vault, context=fixed_context())
            diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(report["fixed_point_authority_status"], "invalid_writer_policy")
        self.assertEqual(report["finality_status"], "fail")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertEqual(diagnostics["status"], "fail")
        self.assertIn(
            "fixed_point_authority_status:invalid_writer_policy",
            diagnostics["failures"],
        )

    def test_non_object_writer_policy_is_a_structured_finality_failure(self) -> None:
        self._seed_finality_inputs()
        valid_report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, valid_report)
        fixed_point = json.loads(
            (self.vault / FIXED_POINT_REPORT_PATH).read_text(encoding="utf-8")
        )
        source_revision = fixed_point["source_revision"]

        for case, policy in (("array", []), ("string", "invalid"), ("null", None)):
            with self.subTest(case=case):
                self._write_json(FIXED_POINT_POLICY_PATH, policy)
                with patch(
                    "ops.scripts.release.release_closeout_finality_attestation.resolve_source_revision",
                    return_value=SourceRevision(
                        source_revision,
                        "source_package_without_git",
                    ),
                ):
                    report = build_report(self.vault, context=fixed_context())
                    diagnostics = verify_attestation_report(self.vault)

                self.assertEqual(
                    report["fixed_point_authority_status"],
                    "invalid_writer_policy",
                )
                self.assertEqual(diagnostics["status"], "fail")
                self.assertIn(
                    "fixed_point_authority_status:invalid_writer_policy",
                    diagnostics["failures"],
                )

    def test_finality_verify_rejects_revision_only_head_transition(self) -> None:
        self._seed_finality_inputs()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)

        with patch(
            "ops.scripts.release.release_closeout_finality_attestation.resolve_source_revision",
            return_value=SourceRevision("next-revision", "git_head"),
        ):
            diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        self.assertIn(
            "attestation_source_revision_mismatch",
            diagnostics["failures"],
        )
        self.assertIn(
            "fixed_point_authority_status:source_revision_mismatch",
            diagnostics["failures"],
        )
        classification = diagnostics["failure_classification"]
        self.assertEqual(
            classification["classes"],
            ["fixed_point_authority_failure"],
        )
        self.assertEqual(
            classification["recommended_lane"],
            "release-closeout-fixed-point",
        )
        self.assertEqual(
            classification["recommended_targets"],
            ["release-closeout-fixed-point", "release-closeout-finality-verify"],
        )
        self.assertEqual(diagnostics["binding_digest_mismatches"], [])
        self.assertEqual(diagnostics["fixed_point_binding_mismatches"], [])

    def test_rebuilding_attestation_does_not_rebind_stale_fixed_point_revision(
        self,
    ) -> None:
        self._seed_finality_inputs()
        with patch(
            "ops.scripts.release.release_closeout_finality_attestation.resolve_source_revision",
            return_value=SourceRevision("next-revision", "git_head"),
        ), patch(
            "ops.scripts.core.artifact_envelope_runtime.resolve_source_revision",
            return_value=SourceRevision("next-revision", "git_head"),
        ):
            report = build_report(self.vault, context=fixed_context())
            write_report(self.vault, report)
            diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(report["source_revision"], "next-revision")
        self.assertEqual(
            report["fixed_point_authority_status"],
            "source_revision_mismatch",
        )
        self.assertEqual(report["finality_status"], "fail")
        self.assertNotIn(
            "attestation_source_revision_mismatch",
            diagnostics["failures"],
        )
        self.assertIn(
            "fixed_point_authority_status:source_revision_mismatch",
            diagnostics["failures"],
        )

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
        classification = diagnostics["failure_classification"]
        self.assertEqual(
            classification["classes"],
            ["terminal_component_raw_binding_mismatch"],
        )
        self.assertEqual(
            classification["recommended_lane"],
            "release-closeout-finality-attestation",
        )
        self.assertEqual(
            classification["recommended_targets"],
            [
                "release-closeout-finality-attestation",
                "release-closeout-finality-verify",
            ],
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

    def test_finality_build_rejects_non_integer_batch_schema_version(self) -> None:
        for schema_version in ("2", True):
            with self.subTest(schema_version=schema_version):
                self._seed_finality_inputs()
                batch_payload = json.loads(
                    (self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8")
                )
                batch_payload["schema_version"] = schema_version
                self._write_json(BATCH_MANIFEST_PATH, batch_payload)
                self._write_json(
                    SELF_CHECK_PATH,
                    {
                        "status": {"result": "pass"},
                        "closeout_inputs": {
                            "batch_manifest_fingerprint": _sha256(
                                self.vault / BATCH_MANIFEST_PATH
                            )
                        },
                    },
                )
                self._rebind_fixed_point_to_current_batch_and_self_check()

                report = build_report(self.vault, context=fixed_context())

                self.assertEqual(report["batch_manifest"]["schema_version"], 0)
                self.assertEqual(report["finality_status"], "fail")
                self.assertIn(
                    "batch_manifest_unsupported_schema_version",
                    report["finality_failures"],
                )

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

    def test_finality_verify_routes_unowned_batch_binding_drift_to_resettle(
        self,
    ) -> None:
        self._seed_finality_inputs()
        artifact_path = "ops/reports/release-smoke-report.json"
        self._write_json(
            artifact_path,
            {"artifact_kind": "release_smoke_report", "status": "pass"},
        )
        batch_payload = json.loads(
            (self.vault / BATCH_MANIFEST_PATH).read_text(encoding="utf-8")
        )
        batch_payload["artifacts"] = [
            self._batch_artifact(artifact_path, role="primary_evidence")
        ]
        self._write_json(BATCH_MANIFEST_PATH, batch_payload)
        self._write_json(
            SELF_CHECK_PATH,
            {
                "status": {"result": "pass"},
                "closeout_inputs": {
                    "batch_manifest_fingerprint": _sha256(
                        self.vault / BATCH_MANIFEST_PATH
                    )
                },
            },
        )
        self._rebind_fixed_point_to_current_batch_and_self_check()
        report = build_report(self.vault, context=fixed_context())
        write_report(self.vault, report)
        self._write_json(
            artifact_path,
            {"artifact_kind": "release_smoke_report", "status": "changed"},
        )

        diagnostics = verify_attestation_report(self.vault)

        self.assertEqual(diagnostics["status"], "fail")
        classification = diagnostics["failure_classification"]
        self.assertEqual(
            classification["classes"],
            ["batch_manifest_artifact_binding_mismatch"],
        )
        self.assertEqual(
            classification["recommended_lane"],
            "release-finality-resettle-current-or-refresh",
        )
        self.assertEqual(
            classification["recommended_targets"],
            ["release-finality-resettle-current-or-refresh"],
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
