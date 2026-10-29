from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from tests.workflow_static_helpers import (
    PINNED_ATTEST_BUILD_PROVENANCE_ACTION,
    PINNED_DOWNLOAD_ARTIFACT_ACTION,
    assert_locked_install_shape as _assert_locked_install_shape,
    assert_workflow_run_contains as _assert_run_contains,
    assert_workflow_uses_are_sha_pinned as _assert_workflow_uses_are_sha_pinned,
    load_workflow,
    workflow_job as _job,
    workflow_jobs as _jobs,
    workflow_mapping as _mapping,
    workflow_on as _workflow_on,
    workflow_path_entries as _path_entries,
    workflow_run_text as _run_text,
    workflow_step as _step,
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
    def test_package_metadata_prevents_pypi_upload(self) -> None:
        project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertIn("Private :: Do Not Upload", project["classifiers"])

    def test_workflows_do_not_publish_to_pypi(self) -> None:
        for path in sorted(Path(".github/workflows").glob("*.yml")):
            workflow = load_workflow(path)
            for job_name, job in _jobs(workflow).items():
                self.assertIsInstance(job, dict)
                for step in _steps(job):
                    with self.subTest(workflow=path.name, job=job_name, step=step.get("name")):
                        self.assertFalse(
                            str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")
                        )

    def test_release_workflow_builds_and_attests_release_artifacts(self) -> None:
        workflow = _workflow()
        on_section = _workflow_on(workflow)
        verify = _job(workflow, "verify-clean-release")
        artifacts = _job(workflow, "release-artifacts")

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
        self.assertEqual(artifacts.get("timeout-minutes"), 30)
        self.assertEqual(
            artifacts.get("permissions"),
            {"contents": "read", "id-token": "write", "attestations": "write"},
        )
        _assert_locked_install_shape(
            self,
            workflow,
            expected_job_count=4,
            jobs_requiring_setup=(
                "trusted-ci-full-suite-evidence",
                "verify-clean-release",
                "release-artifacts",
            ),
        )
        _assert_workflow_uses_are_sha_pinned(self, workflow)
        _assert_run_contains(
            self,
            _step(verify, "Run report-contract full sweep"),
            ("make test-report-contract-all",),
        )
        _assert_run_contains(
            self,
            _step(verify, "Run full public check"),
            ("make public-check-all",),
        )
        verify_step_names = [str(step.get("name", "")) for step in _steps(verify)]
        self.assertLess(
            verify_step_names.index("Run full public check"),
            verify_step_names.index("Materialize verified source zip"),
        )
        _assert_run_contains(
            self,
            _step(artifacts, "Generate supply-chain artifacts"),
            ("make openvex-draft-cached", "make supply-chain-benchmark"),
        )
        self.assertEqual(
            _step(artifacts, "Attest build provenance").get("uses"),
            PINNED_ATTEST_BUILD_PROVENANCE_ACTION,
        )
        _assert_run_contains(
            self,
            _step(verify, "Build wheel and sdist once"),
            ("python -m build --no-isolation --sdist --wheel",),
        )
        upload = _step(artifacts, "Upload release artifacts")
        self.assertIn("dist/*", _path_entries(upload))
        self.assertEqual(upload["with"]["name"], "release-artifacts")
        artifact_step_names = [str(step.get("name", "")) for step in _steps(artifacts)]
        for before, after in (
            ("Download verified distributions", "Verify live release authority"),
            ("Verify live release authority", "Upload release artifacts"),
            ("Upload release artifacts", "Attest build provenance"),
        ):
            self.assertLess(artifact_step_names.index(before), artifact_step_names.index(after))
        artifact_runs = "\n".join(_run_text(step) for step in _steps(artifacts))
        self.assertNotIn("python -m pip install -r requirements-dev.txt build", artifact_runs)
        self.assertNotIn("python -m build", artifact_runs)

    def test_distribution_build_is_unprivileged_and_bound_before_upload(self) -> None:
        workflow = _workflow()
        verify = _job(workflow, "verify-clean-release")
        permissions = verify.get("permissions", workflow.get("permissions"))
        self.assertEqual(permissions, {"contents": "read"})
        names = [str(step.get("name", "")) for step in _steps(verify)]
        order = (
            "Materialize verified source zip",
            "Materialize verified evidence bundle",
            "Clean extract verified source zip",
            "Resolve deterministic source epoch",
            "Build wheel and sdist once",
            "Verify installed wheel",
            "Bind live release artifacts",
            "Upload verified distributions",
        )
        self.assertEqual(sorted(order, key=names.index), list(order))
        build = _step(verify, "Build wheel and sdist once")
        self.assertEqual(
            build.get("env"),
            {"SOURCE_DATE_EPOCH": "${{ steps.source_epoch.outputs.value }}"},
        )
        self.assertIn('"${{ steps.extract.outputs.source-root }}"', _run_text(build))
        builds = [
            step
            for job in _jobs(workflow).values()
            if isinstance(job, dict)
            for step in _steps(job)
            if "python -m build" in _run_text(step)
        ]
        self.assertEqual(len(builds), 1)

    def test_trusted_ci_full_suite_attestation_is_additive_and_minimal(self) -> None:
        workflow = _workflow()
        evidence = _job(workflow, "trusted-ci-full-suite-evidence")
        attestation = _job(workflow, "attest-trusted-ci-full-suite-evidence")
        artifacts = _job(workflow, "release-artifacts")

        self.assertNotIn("permissions", evidence)
        self.assertEqual(evidence.get("runs-on"), "ubuntu-latest")
        _assert_run_contains(
            self,
            _step(evidence, "Run test-execution-summary-full once"),
            ("make test-execution-summary-full-body",),
        )
        _assert_run_contains(
            self,
            _step(evidence, "Materialize trusted CI full-suite evidence bundle"),
            ("make trusted-ci-evidence-bundle",),
        )
        upload = _step(evidence, "Upload trusted CI full-suite evidence bundle")
        self.assertEqual(
            _path_entries(upload),
            ("build/trusted-ci/test-execution-summary-full-evidence.zip",),
        )
        self.assertEqual(attestation.get("needs"), "trusted-ci-full-suite-evidence")
        self.assertEqual(
            attestation.get("permissions"),
            {"contents": "read", "id-token": "write", "attestations": "write"},
        )
        self.assertEqual(len(_steps(attestation)), 2)
        attest_step = _step(attestation, "Attest trusted CI full-suite evidence bundle")
        self.assertEqual(
            attest_step.get("uses"),
            PINNED_ATTEST_BUILD_PROVENANCE_ACTION,
        )
        self.assertEqual(
            attest_step.get("with"),
            {"subject-path": "tmp/trusted-ci/test-execution-summary-full-evidence.zip"},
        )
        self.assertEqual(artifacts.get("needs"), "verify-clean-release")

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
        self.assertEqual(ci_matrix.get("exclude"), workflow_matrix["exclude"])

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
            "Upload verified distributions",
            "Upload verified release attestation",
        ):
            upload = _step(verify, step_name)
            with_section = _mapping(
                upload.get("with", {}),
                "upload step with section must be a mapping",
            )
            self.assertIn(with_section.get("name"), release_assets)

    def test_release_artifacts_consumes_verify_job_live_release_artifacts(self) -> None:
        workflow = _workflow()
        verify = _job(workflow, "verify-clean-release")
        artifacts = _job(workflow, "release-artifacts")

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
                "--dist-dir dist",
                '--expected-source-revision "$GITHUB_SHA"',
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
            "Upload verified distributions": ("verified-distributions", ("dist/",)),
        }
        for step_name, (artifact_name, paths) in expected_uploads.items():
            with self.subTest(step=step_name):
                step = _step(verify, step_name)
                with_section = step.get("with", {})
                self.assertIsInstance(with_section, dict)
                self.assertEqual(with_section.get("name"), artifact_name)
                self.assertTrue(with_section.get("overwrite"))
                for path in paths:
                    self.assertIn(path, _path_entries(step))
        for step_name, artifact_name, path in (
            ("Download verified source zip", "verified-source-zip", "tmp/live-release/source"),
            ("Download verified distributions", "verified-distributions", "dist"),
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
                step = _step(artifacts, step_name)
                with_section = step.get("with", {})
                self.assertIsInstance(with_section, dict)
                self.assertEqual(with_section.get("name"), artifact_name)
                self.assertEqual(with_section.get("path"), path)
                self.assertEqual(step.get("uses"), PINNED_DOWNLOAD_ARTIFACT_ACTION)
        _assert_run_contains(
            self,
            _step(artifacts, "Verify live release authority"),
            (
                "ops.scripts.release.release_live_artifact_attestation verify",
                '--source-zip-path "$SOURCE_ZIP"',
                '--evidence-bundle-path "$EVIDENCE_BUNDLE"',
                '--batch-manifest-path "$BATCH_MANIFEST"',
                '--self-check-path "$SELF_CHECK"',
                "--dist-dir dist",
                '--expected-source-revision "$GITHUB_SHA"',
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
