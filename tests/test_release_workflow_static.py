from __future__ import annotations

import unittest
from pathlib import Path

from tests.workflow_static_helpers import (
    PINNED_ATTEST_BUILD_PROVENANCE_ACTION,
    PINNED_DOWNLOAD_ARTIFACT_ACTION,
    PINNED_PYPI_PUBLISH_ACTION,
    load_workflow,
)
from tests.workflow_static_helpers import (
    assert_locked_install_shape as _assert_locked_install_shape,
)
from tests.workflow_static_helpers import (
    assert_workflow_run_contains as _assert_run_contains,
)
from tests.workflow_static_helpers import (
    assert_workflow_uses_are_sha_pinned as _assert_workflow_uses_are_sha_pinned,
)
from tests.workflow_static_helpers import (
    workflow_job as _job,
)
from tests.workflow_static_helpers import (
    workflow_jobs as _jobs,
)
from tests.workflow_static_helpers import (
    workflow_mapping as _mapping,
)
from tests.workflow_static_helpers import (
    workflow_on as _workflow_on,
)
from tests.workflow_static_helpers import (
    workflow_path_entries as _path_entries,
)
from tests.workflow_static_helpers import (
    workflow_run_text as _run_text,
)
from tests.workflow_static_helpers import (
    workflow_step as _step,
)
from tests.workflow_static_helpers import (
    workflow_steps as _steps,
)

RELEASE_WORKFLOW = Path(".github/workflows/release.yml")
CI_WORKFLOW = Path(".github/workflows/ci.yml")
CODEQL_WORKFLOW = Path(".github/workflows/codeql.yml")
DEPENDENCY_REVIEW_WORKFLOW = Path(".github/workflows/dependency-review.yml")
RELEASE_GOVERNANCE = Path(".github/release-governance.yml")


def _workflow() -> dict[str, object]:
    return load_workflow(RELEASE_WORKFLOW)


def _governance() -> dict[str, object]:
    return load_workflow(RELEASE_GOVERNANCE)


class ReleaseWorkflowStaticTests(unittest.TestCase):
    def test_release_workflow_enables_trusted_publishing_and_attestations(self) -> None:
        workflow = _workflow()
        on_section = _workflow_on(workflow)
        verify = _job(workflow, "verify-clean-release")
        publish = _job(workflow, "publish")

        self.assertEqual(workflow.get("name"), "Release")
        release_event = on_section.get("release", {})
        self.assertIsInstance(release_event, dict)
        self.assertEqual(release_event.get("types"), ["published"])
        workflow_dispatch = on_section.get("workflow_dispatch", {})
        self.assertIsInstance(workflow_dispatch, dict)
        inputs = workflow_dispatch.get("inputs", {})
        self.assertIsInstance(inputs, dict)
        self.assertIn("upload_post_check_finalizer_artifact", inputs)
        self.assertEqual(workflow.get("env"), {"REVIEW_ARCHIVE_PROFILE": "clean"})
        self.assertEqual(verify.get("timeout-minutes"), 60)
        self.assertEqual(publish.get("timeout-minutes"), 30)
        self.assertEqual(
            publish.get("permissions"),
            {"contents": "read", "id-token": "write", "attestations": "write"},
        )
        _assert_locked_install_shape(self, workflow, expected_job_count=2)
        _assert_workflow_uses_are_sha_pinned(self, workflow)
        _assert_run_contains(
            self,
            _step(publish, "Generate supply-chain artifacts"),
            ("make openvex-draft-cached", "make supply-chain-benchmark"),
        )
        self.assertEqual(
            _step(publish, "Attest build provenance").get("uses"),
            PINNED_ATTEST_BUILD_PROVENANCE_ACTION,
        )
        self.assertEqual(
            _step(publish, "Publish to PyPI").get("uses"),
            PINNED_PYPI_PUBLISH_ACTION,
        )
        publish_runs = "\n".join(_run_text(step) for step in _steps(publish))
        self.assertNotIn("python -m pip install -r requirements-dev.txt build", publish_runs)

    def test_release_governance_policy_matches_remote_visible_workflows(self) -> None:
        governance = _governance()
        ci = load_workflow(CI_WORKFLOW)
        codeql = load_workflow(CODEQL_WORKFLOW)
        dependency_review = load_workflow(DEPENDENCY_REVIEW_WORKFLOW)
        release = _workflow()

        self.assertEqual(governance.get("version"), 1)
        branch_protection = _mapping(
            governance.get("branch_protection", {}),
            "branch protection must be a mapping",
        )
        self.assertEqual(branch_protection.get("main_direct_push"), "forbidden")
        self.assertFalse(branch_protection.get("allow_force_pushes"))
        self.assertTrue(branch_protection.get("require_required_status_checks"))

        required = _mapping(
            governance.get("required_status_checks", {}),
            "required status checks must be a mapping",
        )
        ci_matrix = _mapping(
            required.get("ci_matrix", {}),
            "ci matrix must be a mapping",
        )
        workflow_strategy = _mapping(
            _job(ci, "test-tier").get("strategy", {}),
            "workflow strategy must be a mapping",
        )
        workflow_matrix = _mapping(
            workflow_strategy.get("matrix", {}),
            "workflow matrix must be a mapping",
        )
        self.assertEqual(ci_matrix.get("python_versions"), workflow_matrix["python-version"])
        self.assertEqual(ci_matrix.get("tiers"), workflow_matrix["tier"])

        singleton_checks_value = required.get("singleton_checks", [])
        self.assertIsInstance(singleton_checks_value, list)
        singleton_checks = {str(check) for check in singleton_checks_value}
        self.assertIn(_job(ci, "windows-release-smoke")["name"], singleton_checks)
        self.assertIn(_job(ci, "raw-registry-cross-environment-evidence")["name"], singleton_checks)
        self.assertIn(_job(ci, "supply-chain-gate")["name"], singleton_checks)
        codeql_name = str(_job(codeql, "analyze")["name"]).replace(
            "${{ matrix.language }}", "python"
        )
        self.assertIn(codeql_name, singleton_checks)
        self.assertIn(_job(dependency_review, "dependency-review")["name"], singleton_checks)

        remote_sync = _mapping(
            governance.get("remote_sync", {}),
            "remote sync must be a mapping",
        )
        attachment = _mapping(
            remote_sync.get("workflow_attachment", {}),
            "workflow attachment must be a mapping",
        )
        self.assertFalse(attachment.get("attachment_failure_blocks_push"))
        self.assertEqual(
            attachment.get("error_field"),
            "remote_sync.workflow_attachment.workflow_attachment_error",
        )

        release_evidence = _mapping(
            governance.get("release_evidence", {}),
            "release evidence must be a mapping",
        )
        release_assets_value = release_evidence.get("release_assets", [])
        self.assertIsInstance(release_assets_value, list)
        release_assets = {str(asset) for asset in release_assets_value}
        verify = _job(release, "verify-clean-release")
        for step_name in (
            "Upload verified source zip",
            "Upload verified evidence bundle",
            "Upload verified release attestation",
        ):
            upload = _step(verify, step_name)
            with_section = _mapping(
                upload.get("with", {}),
                "upload step with section must be a mapping",
            )
            self.assertIn(with_section.get("name"), release_assets)

    def test_publish_consumes_verify_job_live_release_artifacts(self) -> None:
        workflow = _workflow()
        verify = _job(workflow, "verify-clean-release")
        publish = _job(workflow, "publish")

        _assert_run_contains(
            self,
            _step(verify, "Materialize verified source zip"),
            (
                "make release-distribution-zip",
                "RELEASE_DISTRIBUTION_ZIP_OUT=build/release/live-source.zip",
            ),
        )
        _assert_run_contains(
            self,
            _step(verify, "Bind strict external report manifest"),
            (
                "make external-report-reference-manifest-release-check",
                "EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH=build/release/live-source.zip",
            ),
        )
        _assert_run_contains(
            self,
            _step(verify, "Run provenance clean gate"),
            (
                "make release-provenance-clean",
                "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=build/release/live-source.zip",
                "RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA=build/release/live-source.zip",
            ),
        )
        _assert_run_contains(
            self,
            _step(verify, "Materialize post-check finalizer diagnostics"),
            ("make release-closeout-post-check-finalizer-ci-artifact",),
        )
        upload_post_check = _step(verify, "Upload post-check finalizer diagnostics")
        upload_post_check_with = upload_post_check.get("with", {})
        self.assertIsInstance(upload_post_check_with, dict)
        self.assertEqual(upload_post_check_with.get("name"), "post-check-finalizer-diagnostics")
        for path in (
            "tmp/release-closeout-post-check-finalizer.json",
            "tmp/release-closeout-post-check-finalizer-recommended-targets.txt",
            "tmp/release-closeout-post-check-finalizer-plan.json",
        ):
            self.assertIn(path, _path_entries(upload_post_check))
        _assert_run_contains(
            self,
            _step(verify, "Materialize post-seal release sidecar"),
            (
                "make release-post-seal-attestation",
                "RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP=build/release/live-source.zip",
            ),
        )
        _assert_run_contains(
            self,
            _step(verify, "Materialize verified evidence bundle"),
            (
                "make release-audit-pack",
                "RELEASE_AUDIT_PACK_OUT=build/release/release-evidence-bundle.zip",
            ),
        )
        _assert_run_contains(
            self,
            _step(verify, "Bind live release artifacts"),
            (
                "ops.scripts.release.release_live_artifact_attestation build",
                "--source-zip-path build/release/live-source.zip",
                "--evidence-bundle-path build/release/release-evidence-bundle.zip",
            ),
        )
        expected_uploads = {
            "Upload verified source zip": ("verified-source-zip", ("build/release/live-source.zip",)),
            "Upload verified evidence bundle": (
                "verified-evidence-bundle",
                (
                    "build/release/release-evidence-bundle.zip",
                    "ops/reports/release-closeout-summary.json",
                    "ops/reports/release-closeout-batch-manifest.json",
                    "ops/reports/release-evidence-closeout-self-check.json",
                    "ops/reports/release-closeout-finality-attestation.json",
                    "ops/operator/operator-release-summary.json",
                    "build/release/release-post-seal-attestation.json",
                ),
            ),
            "Upload verified release attestation": (
                "verified-release-attestation",
                ("build/release/release-live-attestation.json",),
            ),
        }
        for step_name, (artifact_name, paths) in expected_uploads.items():
            with self.subTest(step=step_name):
                step = _step(verify, step_name)
                with_section = step.get("with", {})
                self.assertIsInstance(with_section, dict)
                self.assertEqual(with_section.get("name"), artifact_name)
                for path in paths:
                    self.assertIn(path, _path_entries(step))
        for step_name, artifact_name, path in (
            ("Download verified source zip", "verified-source-zip", "tmp/live-release/source"),
            (
                "Download verified evidence bundle",
                "verified-evidence-bundle",
                "tmp/live-release/evidence",
            ),
            (
                "Download verified release attestation",
                "verified-release-attestation",
                "tmp/live-release/attestation",
            ),
        ):
            with self.subTest(step=step_name):
                step = _step(publish, step_name)
                with_section = step.get("with", {})
                self.assertIsInstance(with_section, dict)
                self.assertEqual(with_section.get("name"), artifact_name)
                self.assertEqual(with_section.get("path"), path)
                self.assertEqual(step.get("uses"), PINNED_DOWNLOAD_ARTIFACT_ACTION)
        _assert_run_contains(
            self,
            _step(publish, "Verify live release authority"),
            (
                "ops.scripts.release.release_live_artifact_attestation verify",
                '--source-zip-path "$SOURCE_ZIP"',
                '--evidence-bundle-path "$EVIDENCE_BUNDLE"',
                '--batch-manifest-path "$BATCH_MANIFEST"',
                '--self-check-path "$SELF_CHECK"',
            ),
        )
        all_runs = "\n".join(
            _run_text(step) for job in _jobs(workflow).values() if isinstance(job, dict) for step in _steps(job)
        )
        self.assertNotIn("tmp/live-review-archive-report.json", all_runs)
        self.assertNotIn("ops/reports/review-archive-report.json", all_runs)
        self.assertNotIn("json.load(open('ops/reports/release-closeout-summary.json'))", all_runs)


if __name__ == "__main__":
    unittest.main()
