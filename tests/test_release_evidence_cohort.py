from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.release_evidence_cohort import (
    ALLOWED_DIVERGENCE_WITH_EXPLICIT_RISK,
    BASE_COHORT_SOURCE_SPECS,
    DEFAULT_OUT,
    EMBEDDED_CURRENTNESS,
    FILESYSTEM_MTIME,
    STRICT_SAME_FINGERPRINT,
    ZIP_INFO,
    build_report,
    main,
    write_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_change_sample
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-evidence-cohort.schema.json"
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"
SCHEMA_BY_KIND = {
    "bootstrap_preflight_report": "ops/schemas/bootstrap-preflight-report.schema.json",
    "release_smoke_report": "ops/schemas/release-smoke-report.schema.json",
    "test_execution_summary": "ops/schemas/test-execution-summary.schema.json",
    "source_package_clean_extract": "ops/schemas/source-package-clean-extract.schema.json",
    "raw_registry_preflight_report": "ops/schemas/raw-registry-preflight-report.schema.json",
    "artifact_freshness_report": "ops/schemas/artifact-freshness-report.schema.json",
    "generated_artifact_index_report": "ops/schemas/generated-artifact-index.schema.json",
    "auto_improve_readiness_report": "ops/schemas/auto-improve-readiness-report.schema.json",
    "release_closeout_summary": "ops/schemas/release-closeout-summary.schema.json",
}


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 29, 9, 0, tzinfo=dt.timezone.utc),
    )


class ReleaseEvidenceCohortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self._normalize_release_surface_mtimes()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_source_report(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        *,
        source_tree_fingerprint: str | None = None,
        mtime: str = "2026-04-29T08:00:00Z",
    ) -> None:
        spec = next(spec for spec in BASE_COHORT_SOURCE_SPECS if spec.name == name)
        policy, resolved_policy_path = load_policy(self.vault, "ops/policies/wiki-maintainer-policy.yaml")
        generated_at = str((payload or {}).get("generated_at", "2026-04-29T08:00:00Z"))
        report = {
            **build_canonical_report_envelope(
                self.vault,
                generated_at=generated_at,
                artifact_kind=spec.artifact_kind,
                producer=f"tests.{name}",
                source_command=f"pytest {name}",
                resolved_policy_path=resolved_policy_path,
                schema_path=SCHEMA_BY_KIND[spec.artifact_kind],
                source_paths=[],
            ),
            "vault": report_path(self.vault, self.vault),
            "policy": {
                "path": report_path(self.vault, resolved_policy_path),
                "version": policy.get("version"),
            },
            "status": "pass",
            **(payload or {}),
        }
        if spec.artifact_kind == "bootstrap_preflight_report":
            report.update(
                {
                    "python": {"version": "3.14.3", "minimum": "3.12.0", "status": "pass"},
                    "include_dev": True,
                    "dependencies": [],
                    "summary": {
                        "dependency_count": 0,
                        "missing_dependency_count": 0,
                        "missing_packages": [],
                    },
                    "guidance": "Run make dev-install, then rerun make bootstrap-preflight.",
                }
            )
        if spec.artifact_kind == "test_execution_summary":
            report.setdefault("deselected_tests", [])
        if spec.artifact_kind == "release_closeout_summary":
            report.setdefault("accepted_risks", [])
            report.setdefault("release_readiness_state", "clean_pass")
            report.setdefault("machine_release_allowed", True)
        if source_tree_fingerprint is not None:
            report["source_tree_fingerprint"] = source_tree_fingerprint
        path = self.vault / spec.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        modified_at = dt.datetime.fromisoformat(mtime.replace("Z", "+00:00"))
        os.utime(path, (modified_at.timestamp(), modified_at.timestamp()))

    def _write_release_surface_file(self, rel_path: str, text: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _touch_release_surface_file(self, rel_path: str, when: str) -> None:
        path = self.vault / rel_path
        timestamp = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        os.utime(path, (timestamp, timestamp))

    def _normalize_release_surface_mtimes(self, when: str = "2026-04-29T07:59:59Z") -> None:
        timestamp = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        sample = release_source_tree_change_sample(
            self.vault,
            generated_at="1970-01-01T00:00:00Z",
            path_limit=100000,
        )
        for item in sample["changed_after_generated_at"]:
            path = self.vault / str(item["path"])
            os.utime(path, (timestamp, timestamp))

    def _write_happy_sources(self) -> None:
        for spec in BASE_COHORT_SOURCE_SPECS:
            self._write_source_report(spec.name)

    def test_build_report_passes_for_single_fingerprint_cohort(self) -> None:
        self._write_happy_sources()

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["cohort_policy"], ALLOWED_DIVERGENCE_WITH_EXPLICIT_RISK)
        self.assertEqual(report["provenance_mode"], EMBEDDED_CURRENTNESS)
        self.assertTrue(report["cohort"]["strict_same_fingerprint"])
        self.assertEqual(report["cohort"]["provenance_mode"], EMBEDDED_CURRENTNESS)
        self.assertEqual(report["summary"]["component_count"], 10)
        self.assertEqual(report["summary"]["loaded_component_count"], 10)
        self.assertEqual(report["summary"]["component_fingerprint_count"], 1)
        self.assertEqual(report["summary"]["evidence_artifact_count"], 0)
        self.assertEqual(report["summary"]["clean_lane_contract_status"], "pass")
        self.assertEqual(report["clean_lane_contract"]["status"], "pass")
        self.assertTrue(report["clean_lane_contract"]["zero_deselection"])
        self.assertTrue(report["clean_lane_contract"]["zero_accepted_risk_family"])
        self.assertTrue(report["clean_lane_contract"]["release_closeout_clean"])
        self.assertTrue(all(item["producer_input_fingerprint"] for item in report["components"]))
        self.assertTrue(all(item["provenance_mode"] == EMBEDDED_CURRENTNESS for item in report["components"]))
        self.assertTrue(all(item["report_mtime"] == "" for item in report["components"]))
        self.assertEqual(report["cohort"]["divergence_diagnostics"]["path_limit"], 10)
        self.assertEqual(report["cohort"]["divergence_diagnostics"]["components"], [])
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["cohort_risks"], [])
        self.assertEqual(
            [step["target"] for step in report["ordered_chain"]],
            [
                "bootstrap-preflight",
                "release-smoke-full",
                "registry-preflight",
                "test-execution-summary",
                "test-execution-summary-full",
                "auto-improve-readiness",
                "generated-artifact-index",
                "artifact-freshness",
                "release-closeout-summary",
            ],
        )
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])
        self.assertEqual(validate_with_schema(report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_cohort_carries_test_summary_forensic_artifact_digests(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "test_summary_full",
            {
                "evidence_artifacts": [
                    {
                        "kind": "junit_xml",
                        "path": "tmp/test-execution-summary-full.junit.xml",
                        "exists": True,
                        "size_bytes": 32,
                        "sha256": "a" * 64,
                        "source": "pytest_junit_xml",
                    },
                    {
                        "kind": "execution_log",
                        "path": "tmp/test-execution-summary-full.log",
                        "exists": True,
                        "size_bytes": 64,
                        "sha256": "b" * 64,
                        "source": "captured_pytest_stdout_stderr",
                    },
                    {
                        "kind": "failed_nodeids",
                        "path": "tmp/test-execution-summary-full.failed-nodeids.txt",
                        "exists": True,
                        "size_bytes": 12,
                        "sha256": "c" * 64,
                        "source": "pytest_failure_nodeids",
                    },
                ]
            },
        )

        report = build_report(self.vault, context=fixed_context())

        full_component = next(item for item in report["components"] if item["name"] == "test_summary_full")
        self.assertEqual(report["summary"]["evidence_artifact_count"], 3)
        self.assertEqual(full_component["evidence_artifact_count"], 3)
        self.assertEqual(
            {item["kind"] for item in full_component["evidence_artifacts"]},
            {"junit_xml", "execution_log", "failed_nodeids"},
        )
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_allowed_policy_keeps_fingerprint_drift_visible_as_attention(self) -> None:
        self._write_release_surface_file("ops/scripts/divergence_sample.py", "print('sample')\n")
        self._write_happy_sources()
        self._touch_release_surface_file("ops/scripts/divergence_sample.py", "2026-04-29T08:00:01Z")
        self._write_source_report(
            "generated_index",
            source_tree_fingerprint="different-release-tree-fingerprint",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "attention")
        self.assertFalse(report["cohort"]["strict_same_fingerprint"])
        self.assertEqual(report["summary"]["risk_count"], 1)
        self.assertEqual(report["cohort_risks"][0]["code"], "cohort_not_strict_same_fingerprint")
        self.assertEqual(report["cohort_risks"][0]["risk_acceptance"]["accepted_by"], "release_evidence_cohort_policy")
        self.assertEqual(report["cohort_risks"][0]["risk_acceptance"]["expires_at"], "2026-05-06T09:00:00Z")
        diagnostics = report["cohort"]["divergence_diagnostics"]
        self.assertEqual(diagnostics["path_limit"], 10)
        generated_index = next(item for item in diagnostics["components"] if item["name"] == "generated_index")
        self.assertFalse(generated_index["matches_current_source_tree_fingerprint"])
        self.assertFalse(generated_index["modified_after_generated_at"])
        self.assertEqual(generated_index["changed_after_generated_at_count"], 1)
        self.assertEqual(
            generated_index["changed_after_generated_at"],
            [{"path": "ops/scripts/divergence_sample.py", "mtime": "2026-04-29T08:00:01Z"}],
        )
        self.assertEqual(report["issues"], [])
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_strict_policy_fails_on_fingerprint_drift(self) -> None:
        self._write_release_surface_file("ops/scripts/divergence_sample.py", "print('sample')\n")
        self._write_happy_sources()
        self._touch_release_surface_file("ops/scripts/divergence_sample.py", "2026-04-29T08:00:01Z")
        self._write_source_report(
            "artifact_freshness",
            source_tree_fingerprint="different-release-tree-fingerprint",
        )

        report = build_report(
            self.vault,
            context=fixed_context(),
            cohort_policy=STRICT_SAME_FINGERPRINT,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["issue_count"], 1)
        self.assertEqual(report["issues"][0]["code"], "cohort_not_strict_same_fingerprint")
        diagnostics = report["cohort"]["divergence_diagnostics"]
        artifact_freshness = next(item for item in diagnostics["components"] if item["name"] == "artifact_freshness")
        self.assertFalse(artifact_freshness["matches_current_source_tree_fingerprint"])
        self.assertEqual(
            artifact_freshness["changed_after_generated_at"],
            [{"path": "ops/scripts/divergence_sample.py", "mtime": "2026-04-29T08:00:01Z"}],
        )
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_modified_after_generated_at_is_separate_cohort_risk(self) -> None:
        self._write_release_surface_file("ops/scripts/divergence_sample.py", "print('sample')\n")
        self._write_happy_sources()
        self._touch_release_surface_file("ops/scripts/divergence_sample.py", "2026-04-29T08:00:01Z")
        self._write_source_report(
            "generated_index",
            mtime="2026-04-29T08:00:01Z",
        )

        report = build_report(
            self.vault,
            context=fixed_context(),
            provenance_mode=FILESYSTEM_MTIME,
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["risk_count"], 1)
        self.assertEqual(report["summary"]["modified_after_generated_at_count"], 1)
        self.assertEqual(report["cohort_risks"][0]["code"], "cohort_modified_after_generated_at")
        self.assertIn("generated_index", report["cohort"]["modified_after_generated_at_components"])
        diagnostics = report["cohort"]["divergence_diagnostics"]
        generated_index = next(item for item in diagnostics["components"] if item["name"] == "generated_index")
        self.assertTrue(generated_index["matches_current_source_tree_fingerprint"])
        self.assertTrue(generated_index["modified_after_generated_at"])
        self.assertEqual(
            generated_index["changed_after_generated_at"],
            [{"path": "ops/scripts/divergence_sample.py", "mtime": "2026-04-29T08:00:01Z"}],
        )
        risk_acceptance = report["cohort_risks"][0]["risk_acceptance"]
        self.assertEqual(risk_acceptance["accepted_by"], "release_evidence_cohort_policy")
        self.assertEqual(risk_acceptance["risk_owner"], "runtime-maintainer")
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_strict_policy_splits_fingerprint_and_mtime_blockers(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "artifact_freshness",
            source_tree_fingerprint="different-release-tree-fingerprint",
            mtime="2026-04-29T08:00:01Z",
        )

        report = build_report(
            self.vault,
            context=fixed_context(),
            cohort_policy=STRICT_SAME_FINGERPRINT,
            provenance_mode=FILESYSTEM_MTIME,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            {item["code"] for item in report["issues"]},
            {"cohort_not_strict_same_fingerprint", "cohort_modified_after_generated_at"},
        )
        self.assertEqual(report["cohort_risks"], [])
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_embedded_currentness_mode_ignores_filesystem_mtime_drift(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "generated_index",
            mtime="2026-04-29T08:00:01Z",
        )

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["modified_after_generated_at_count"], 0)
        self.assertEqual(report["cohort_risks"], [])
        self.assertEqual(report["clean_lane_contract"]["status"], "pass")
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_zip_info_provenance_mode_uses_archive_member_mtimes(self) -> None:
        self._write_happy_sources()
        zip_path = self.vault / "tmp" / "release-evidence.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as archive:
            for spec in BASE_COHORT_SOURCE_SPECS:
                path = self.vault / spec.path
                info = zipfile.ZipInfo(spec.path)
                info.date_time = (2026, 4, 29, 8, 0, 0)
                if spec.name == "generated_index":
                    info.date_time = (2026, 4, 29, 8, 0, 2)
                archive.writestr(info, path.read_bytes())

        report = build_report(
            self.vault,
            context=fixed_context(),
            provenance_mode=ZIP_INFO,
            zip_metadata=zip_path.as_posix(),
        )

        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["provenance_mode"], ZIP_INFO)
        self.assertEqual(report["summary"]["modified_after_generated_at_count"], 1)
        self.assertIn("generated_index", report["cohort"]["modified_after_generated_at_components"])
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_clean_lane_contract_fails_when_summary_carries_deselections_or_accepted_risks(self) -> None:
        self._write_happy_sources()
        self._write_source_report(
            "test_summary",
            {
                "deselected_tests": [{"nodeid": "tests/example.py::test_self_reference"}],
            },
        )
        self._write_source_report(
            "release_closeout_summary",
            {
                "accepted_risks": [{"code": "source_tree_coherence_attention"}],
                "release_readiness_state": "conditional_pass",
                "machine_release_allowed": False,
            },
        )

        report = build_report(
            self.vault,
            context=fixed_context(),
            cohort_policy=STRICT_SAME_FINGERPRINT,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["clean_lane_contract"]["status"], "fail")
        self.assertFalse(report["clean_lane_contract"]["zero_deselection"])
        self.assertFalse(report["clean_lane_contract"]["zero_accepted_risk_family"])
        self.assertFalse(report["clean_lane_contract"]["release_closeout_clean"])
        self.assertEqual(report["summary"]["deselected_test_count"], 1)
        self.assertEqual(report["summary"]["accepted_risk_family_count"], 1)
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_operator_signoff_risk_does_not_block_clean_lane_contract(self) -> None:
        """T5: operator-signoff risks must not block zero_accepted_risk_family in clean lane.

        When a closeout summary carries only operator-signoff accepted risks (no policy risks),
        the clean_lane_contract.zero_accepted_risk_family must remain True so the clean
        lane is not blocked by the learning readiness reviewer signoff pathway.
        """
        self._write_happy_sources()
        # Closeout summary with 1 operator-signoff risk, 0 policy risks.
        # clean_lane_blocking_risk_family_count=0 → zero_accepted_risk_family must be True.
        self._write_source_report(
            "release_closeout_summary",
            {
                "accepted_risks": [
                    {
                        "code": "learning_blocked_by_review_required",
                        "risk_acceptance": {
                            "accepted_by": "operator@example.test",
                            "accepted_at": "2026-04-23T08:30:00Z",
                            "expires_at": "2026-04-30T08:30:00Z",
                            "acceptance_source": "ops/reports/learning-readiness-signoff.json",
                            "linked_blocker_id": "learning_blocked_by_review_required",
                        },
                    }
                ],
                "clean_lane_blocking_risk_family_count": 0,
                "release_readiness_state": "clean_pass",
                "machine_release_allowed": True,
            },
        )

        report = build_report(
            self.vault,
            context=fixed_context(),
            cohort_policy=STRICT_SAME_FINGERPRINT,
        )

        self.assertEqual(report["clean_lane_contract"]["total_accepted_risk_family_count"], 1)
        self.assertEqual(report["clean_lane_contract"]["clean_lane_blocking_family_count"], 0)
        self.assertTrue(report["clean_lane_contract"]["zero_accepted_risk_family"])
        # summary.accepted_risk_family_count reflects clean-lane-blocking count
        self.assertEqual(report["summary"]["accepted_risk_family_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])


    def test_missing_component_report_fails_and_names_required_evidence(self) -> None:
        self._write_source_report("release_smoke")

        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["loaded_component_count"], 1)
        self.assertIn("test_summary_report_missing", {item["code"] for item in report["issues"]})
        self.assertEqual(validate_with_schema(report, load_schema(REPORT_SCHEMA_PATH)), [])

    def test_write_report_validates_schema_and_main_status_codes(self) -> None:
        self._write_happy_sources()
        report = build_report(self.vault, context=fixed_context())
        output_path = write_report(self.vault, report, DEFAULT_OUT)

        self.assertTrue(output_path.exists())
        self.assertEqual(main(["--vault", self.vault.as_posix(), "--out", DEFAULT_OUT]), 0)

        self._write_source_report(
            "generated_index",
            source_tree_fingerprint="different-release-tree-fingerprint",
        )
        self.assertEqual(main(["--vault", self.vault.as_posix(), "--out", DEFAULT_OUT]), 0)
        self.assertEqual(
            main(["--vault", self.vault.as_posix(), "--out", DEFAULT_OUT, "--fail-on-attention"]),
            1,
        )
        self.assertEqual(
            main(["--vault", self.vault.as_posix(), "--out", DEFAULT_OUT, "--require-clean-lane"]),
            1,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
