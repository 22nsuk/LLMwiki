from __future__ import annotations

import unittest
from pathlib import Path

import pytest
import yaml

from ops.scripts.test.test_lane_registry_runtime import (
    compatibility_names,
    load_registry,
)
from tests.workflow_static_helpers import (
    PINNED_CHECKOUT_ACTION,
    PINNED_DEPENDENCY_REVIEW_ACTION,
    PINNED_DOWNLOAD_ARTIFACT_ACTION,
    PINNED_UPLOAD_ARTIFACT_ACTION,
    assert_workflow_uses_are_sha_pinned,
    load_workflow,
    workflow_job as _job,
    workflow_jobs as _jobs,
    workflow_mapping,
    workflow_matrix,
    workflow_matrix_include,
    workflow_matrix_values,
    workflow_on,
    workflow_path_entries as _path_entries,
    workflow_run_text as _run_text,
    workflow_step as _step_by_name,
    workflow_steps as _steps,
)

CI_WORKFLOW = Path(".github/workflows/ci.yml")
RELEASE_WORKFLOW = Path(".github/workflows/release.yml")
CODEQL_WORKFLOW = Path(".github/workflows/codeql.yml")
DEPENDENCY_REVIEW_WORKFLOW = Path(".github/workflows/dependency-review.yml")
DEPENDABOT_CONFIG = Path(".github/dependabot.yml")

pytestmark = pytest.mark.report_contract


def _workflow() -> dict[str, object]:
    return load_workflow(CI_WORKFLOW)


def _assert_locked_dependency_steps(case: unittest.TestCase, job: dict[str, object]) -> None:
    setup = _step_by_name(job, "Setup Python and uv")
    install_steps = [
        step
        for step in _steps(job)
        if str(step.get("name", "")).startswith("Install dependencies")
    ]

    case.assertEqual(setup.get("uses"), "./.github/actions/setup-python-uv")
    with_config = workflow_mapping(
        setup.get("with", {}),
        "setup-python-uv with section must be a mapping",
    )
    python_version = with_config.get("python-version")
    if python_version is not None:
        case.assertIsInstance(python_version, str)
    if install_steps:
        run_text = _run_text(install_steps[0])
        case.assertIn("make uv-lock-check", run_text)
        case.assertIn(
            "uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt",
            run_text,
        )
        case.assertIn("python -m pip install -r tmp/locked-requirements.ci.txt", run_text)
        case.assertLess(
            run_text.index("make uv-lock-check"),
            run_text.index("uv export --frozen"),
        )
        case.assertNotIn("python -m pip install -r requirements-dev.txt build", run_text)


class CiWorkflowStaticTests(unittest.TestCase):
    def test_github_security_automation_surface_is_present_and_pinned(self) -> None:
        dependabot = yaml.safe_load(DEPENDABOT_CONFIG.read_text(encoding="utf-8"))
        self.assertIsInstance(dependabot, dict)
        self.assertEqual(dependabot.get("version"), 2)
        updates = dependabot.get("updates", [])
        self.assertIsInstance(updates, list)
        ecosystems = {item.get("package-ecosystem") for item in updates if isinstance(item, dict)}
        self.assertEqual(ecosystems, {"github-actions", "pip"})

        for workflow_path in (
            CI_WORKFLOW,
            RELEASE_WORKFLOW,
            CODEQL_WORKFLOW,
            DEPENDENCY_REVIEW_WORKFLOW,
        ):
            with self.subTest(workflow=str(workflow_path)):
                workflow = load_workflow(workflow_path)
                self.assertEqual(workflow.get("permissions"), {"contents": "read"})
                self.assertIn("concurrency", workflow)
                assert_workflow_uses_are_sha_pinned(self, workflow)
                for job_name, job in _jobs(workflow).items():
                    with self.subTest(workflow=str(workflow_path), job=job_name):
                        self.assertIsInstance(job, dict)
                        timeout_minutes = job.get("timeout-minutes")
                        self.assertIsInstance(timeout_minutes, int)
                        self.assertGreater(timeout_minutes, 0)

        codeql = load_workflow(CODEQL_WORKFLOW)
        codeql_job = _job(codeql, "analyze")
        self.assertEqual(
            codeql_job.get("permissions"),
            {"actions": "read", "contents": "read", "security-events": "write"},
        )
        self.assertEqual(_step_by_name(codeql_job, "Checkout").get("uses"), PINNED_CHECKOUT_ACTION)
        self.assertRegex(
            str(_step_by_name(codeql_job, "Initialize CodeQL").get("uses")),
            r"^github/codeql-action/init@[0-9a-f]{40}$",
        )
        self.assertRegex(
            str(_step_by_name(codeql_job, "Perform CodeQL Analysis").get("uses")),
            r"^github/codeql-action/analyze@[0-9a-f]{40}$",
        )

        dependency_review = load_workflow(DEPENDENCY_REVIEW_WORKFLOW)
        review_job = _job(dependency_review, "dependency-review")
        self.assertEqual(
            _step_by_name(review_job, "Dependency Review").get("uses"),
            PINNED_DEPENDENCY_REVIEW_ACTION,
        )
        self.assertEqual(
            workflow_mapping(
                _step_by_name(review_job, "Dependency Review").get("with", {}),
                "dependency review with section must be a mapping",
            ).get("fail-on-severity"),
            "moderate",
        )

    def test_ci_keeps_push_ci_for_release_refs_only(self) -> None:
        on_section = workflow_on(_workflow())
        push = workflow_mapping(
            on_section.get("push", {}),
            "CI push trigger must be a mapping",
        )

        self.assertEqual(push.get("branches"), ["release/**"])
        self.assertEqual(push.get("tags"), ["**"])
        self.assertNotIn("branches-ignore", push)
        self.assertIn("pull_request", on_section)
        self.assertIn("workflow_dispatch", on_section)

    def test_ci_matrix_tiers_match_registry_compatibility_contract(self) -> None:
        registry = load_registry(Path())
        workflow = _workflow()

        test_tier_job = _job(workflow, "test-tier")
        self.assertEqual(
            workflow_matrix_values(test_tier_job, "tier"),
            compatibility_names(registry, "ci_tier"),
        )

    def test_ci_matrix_covers_supported_python_minor_versions(self) -> None:
        workflow = _workflow()

        test_tier_job = _job(workflow, "test-tier")
        self.assertEqual(
            workflow_matrix_values(test_tier_job, "python-version"),
            ("3.12", "3.13", "3.14"),
        )

    def test_ci_matrix_keeps_multi_python_coverage_only_on_fast_tier(self) -> None:
        test_tier_job = _job(_workflow(), "test-tier")
        matrix = workflow_matrix(test_tier_job)
        tiers = workflow_matrix_values(test_tier_job, "tier")
        versions = workflow_matrix_values(test_tier_job, "python-version")
        exclude = matrix.get("exclude", [])
        self.assertIsInstance(exclude, list)
        excluded_pairs = {
            (str(item.get("tier")), str(item.get("python-version")))
            for item in exclude
            if isinstance(item, dict)
        }
        expected_excluded_pairs = {
            (tier, version)
            for tier in tiers
            if tier != "fast"
            for version in versions
            if version != "3.12"
        }

        self.assertEqual(excluded_pairs, expected_excluded_pairs)
        self.assertEqual(len(tiers) * len(versions) - len(excluded_pairs), 11)

    def test_ci_dependency_cache_tracks_canonical_lockfile(self) -> None:
        workflow = _workflow()

        for job_name in _jobs(workflow):
            with self.subTest(job_name=job_name):
                _assert_locked_dependency_steps(self, _job(workflow, job_name))

    def test_ci_workflow_has_windows_release_smoke_job(self) -> None:
        workflow = _workflow()
        job = _job(workflow, "windows-release-smoke")

        self.assertEqual(job.get("name"), "windows-release-smoke / py3.12")
        self.assertEqual(job.get("runs-on"), "windows-latest")
        env = workflow_mapping(job.get("env", {}), "windows release smoke env must be a mapping")
        self.assertEqual(env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD"), "1")
        setup_with = workflow_mapping(
            _step_by_name(job, "Setup Python and uv").get("with", {}),
            "windows setup-python-uv with section must be a mapping",
        )
        self.assertEqual(
            setup_with.get("python-version"),
            "3.12",
        )
        _assert_locked_dependency_steps(self, job)
        self.assertIn(
            "python -m ops.scripts.release.release_smoke --vault . --profile full --out ops/reports/release-smoke-report-windows.json",
            _run_text(_step_by_name(job, "Run Windows release smoke")),
        )
        self.assertIn(
            "python -m pytest -q tests/test_command_runtime.py",
            _run_text(_step_by_name(job, "Run Windows command runtime smoke")),
        )
        strict_preview_run = _run_text(_step_by_name(job, "Run Windows strict preview smoke"))
        self.assertIn(
            'python .\\tools\\strict_preview_audit.py --vault . --out tmp\\strict-preview-audit-windows.json --targets "ops/scripts tests tools" --ruff-select PTH201',
            strict_preview_run,
        )
        self.assertIn(
            '--mypy-flags "--check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs" --python python',
            strict_preview_run,
        )
        schema_static_smoke_run = _run_text(
            _step_by_name(job, "Run Windows schema static smoke tests")
        )
        self.assertEqual(schema_static_smoke_run, "make test-schema-static-smoke PYTHON=python")
        upload = _step_by_name(job, "Upload Windows smoke artifact")
        self.assertEqual(upload.get("uses"), PINNED_UPLOAD_ARTIFACT_ACTION)
        upload_with = workflow_mapping(
            upload.get("with", {}),
            "windows upload artifact with section must be a mapping",
        )
        self.assertEqual(upload_with.get("name"), "windows-release-smoke-report")
        self.assertEqual(
            upload_with.get("path"),
            "ops/reports/release-smoke-report-windows.json",
        )

    def test_fast_tier_runs_release_smoke_fast_when_full_vault_is_present(self) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            "if [ -f system/system-index.md ] && [ -f wiki/index.md ] && [ -d raw ]; then",
            text,
        )
        self.assertIn("          make test-selectors-sync-check", text)
        self.assertIn("            make check-finalized", text)
        self.assertIn("            make release-smoke-fast", text)

    def test_report_contract_tier_delegates_selection_to_make(self) -> None:
        job = _job(_workflow(), "test-tier")
        step = _step_by_name(job, "Run report-contract tier")

        self.assertEqual(step.get("if"), "matrix.tier == 'report-contract'")
        self.assertEqual(_run_text(step), "make ci-report-contract-tier")

    def test_release_closeout_regression_tier_uploads_diagnostics_without_masking_root_failure(
        self,
    ) -> None:
        job = _job(_workflow(), "test-tier")

        run_step = _step_by_name(job, "Run release closeout regression tier")
        self.assertEqual(run_step.get("id"), "release_closeout_regression")
        self.assertEqual(run_step.get("if"), "matrix.tier == 'release-closeout-regression'")
        run_text = _run_text(run_step)
        for command in (
            "make release-workflow-order-guard",
            "make release-closeout-regression-dry-run",
            "make release-closeout-post-check-finalizer-ci-artifact",
            "make release-closeout-cost-evidence-ci-artifact",
        ):
            with self.subTest(command=command):
                self.assertIn(command, run_text)

        authority_step = _step_by_name(job, "Run release authority diagnostics tier")
        self.assertEqual(authority_step.get("id"), "release_authority_diagnostics")
        self.assertEqual(
            authority_step.get("if"),
            "always() && matrix.tier == 'release-closeout-regression' && steps.release_closeout_regression.outcome != 'skipped'",
        )
        self.assertEqual(authority_step.get("env", {}).get("CI_PYTHON_VERSION"), "${{ matrix.python-version }}")
        authority_run_text = _run_text(authority_step)
        authority_commands = {line.strip() for line in authority_run_text.splitlines() if line.strip()}
        self.assertIn("set +e", authority_commands)
        self.assertIn("finality_status=0", authority_commands)
        self.assertIn("sealed_preflight_status=0", authority_commands)
        self.assertIn("make release-closeout-finality-verify-ci-artifact", authority_commands)
        self.assertNotIn("make release-closeout-finality-verify", authority_commands)
        self.assertIn("make release-authority-sealed-preflight", authority_commands)
        self.assertIn("finality_status=$?", authority_commands)
        self.assertIn("sealed_preflight_status=$?", authority_commands)
        self.assertIn(
            'if [ "$finality_status" -ne 0 ] || [ "$sealed_preflight_status" -ne 0 ]; then',
            authority_commands,
        )
        self.assertIn("exit 0", authority_commands)
        self.assertNotIn('exit "$sealed_preflight_status"', authority_commands)
        self.assertIn(
            'echo "sealed_preflight_status=${sealed_preflight_status}"',
            authority_commands,
        )
        self.assertIn(
            '} > "tmp/release-authority-blocked-preflight-upload-diagnostics-${CI_PYTHON_VERSION}.txt"',
            authority_commands,
        )

        diagnostics = _step_by_name(job, "Materialize release closeout upload diagnostics")
        self.assertEqual(
            diagnostics.get("if"),
            "always() && matrix.tier == 'release-closeout-regression' && (steps.release_closeout_regression.outcome != 'success' || steps.release_authority_diagnostics.outcome != 'success')",
        )
        diagnostics_run = _run_text(diagnostics)
        self.assertIn(
            "tmp/release-closeout-cost-evidence-upload-diagnostics-${CI_PYTHON_VERSION}.txt",
            diagnostics_run,
        )
        self.assertIn(
            "tmp/release-authority-blocked-preflight-upload-diagnostics-${CI_PYTHON_VERSION}.txt",
            diagnostics_run,
        )

        cost_upload = _step_by_name(job, "Upload release closeout cost evidence")
        self.assertEqual(cost_upload.get("uses"), PINNED_UPLOAD_ARTIFACT_ACTION)
        self.assertEqual(cost_upload.get("if"), "always() && matrix.tier == 'release-closeout-regression'")
        cost_paths = _path_entries(cost_upload)
        for path in (
            "tmp/release-closeout-fixed-point-cost-trend-ci.json",
            "ops/reports/release-closeout-fixed-point.json",
            "ops/reports/release-closeout-fixed-point-cost-trend.json",
            "ops/reports/release-evidence-dashboard.json",
            "ops/reports/release-workflow-order-guard.json",
            "tmp/release-closeout-post-check-finalizer.json",
            "tmp/release-closeout-post-check-finalizer-recommended-targets.txt",
            "tmp/release-closeout-post-check-finalizer-plan.json",
            "tmp/release-closeout-cost-evidence-upload-diagnostics-${{ matrix.python-version }}.txt",
        ):
            with self.subTest(path=path):
                self.assertIn(path, cost_paths)

        authority_upload = _step_by_name(job, "Upload release authority blocked preflight")
        self.assertEqual(authority_upload.get("uses"), PINNED_UPLOAD_ARTIFACT_ACTION)
        self.assertEqual(
            authority_upload.get("if"),
            "always() && matrix.tier == 'release-closeout-regression'",
        )
        authority_paths = _path_entries(authority_upload)
        for path in (
            "build/release/release-closeout-sealed-dry-run/LLMwiki-source.zip",
            "build/release/release-closeout-sealed-dry-run/release-closeout-batch-manifest.json",
            "build/release/release-closeout-sealed-dry-run/external-report-reference-manifest.json",
            "build/release/release-closeout-sealed-dry-run/release-closeout-sealed-rehearsal-check.json",
            "ops/reports/release-closeout-sealed-rehearsal-check.json",
            "tmp/release-closeout-finality-verify-ci.json",
            "tmp/release-authority-blocked-preflight-upload-diagnostics-${{ matrix.python-version }}.txt",
        ):
            with self.subTest(path=path):
                self.assertIn(path, authority_paths)

    def test_public_tier_uploads_candidate_summary_diagnostics(self) -> None:
        job = _job(_workflow(), "test-tier")

        public_run = _step_by_name(job, "Run public mirror tier")
        self.assertEqual(public_run.get("if"), "matrix.tier == 'public'")
        self.assertEqual(_run_text(public_run), "make ci-public-tier")

        upload = _step_by_name(job, "Upload public check summary diagnostics")
        self.assertEqual(upload.get("if"), "always() && matrix.tier == 'public'")
        self.assertEqual(upload.get("uses"), PINNED_UPLOAD_ARTIFACT_ACTION)
        upload_with = workflow_mapping(
            upload.get("with", {}),
            "public check summary upload with section must be a mapping",
        )
        self.assertEqual(upload_with.get("name"), "public-check-summary-${{ matrix.python-version }}")
        self.assertEqual(upload_with.get("if-no-files-found"), "warn")
        self.assertEqual(
            _path_entries(upload),
            (
                "tmp/public-check-summary.candidate.json",
                "tmp/public-check-summary-check.json",
            ),
        )

    def test_ci_artifact_transfer_actions_are_pinned(self) -> None:
        workflow = _workflow()
        for job_name, job in _jobs(workflow).items():
            if not isinstance(job, dict):
                continue
            for step in _steps(job):
                uses = str(step.get("uses", ""))
                if not uses:
                    continue
                with self.subTest(job=job_name, step=step.get("name", ""), uses=uses):
                    if "upload-artifact@" in uses:
                        self.assertEqual(uses, PINNED_UPLOAD_ARTIFACT_ACTION)
                    if "download-artifact@" in uses:
                        self.assertEqual(uses, PINNED_DOWNLOAD_ARTIFACT_ACTION)

    def test_windows_command_runtime_smoke_step_runs_between_release_and_preview(
        self,
    ) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        release_index = text.index("- name: Run Windows release smoke")
        command_runtime_index = text.index("- name: Run Windows command runtime smoke")
        strict_preview_index = text.index("- name: Run Windows strict preview smoke")

        self.assertLess(release_index, command_runtime_index)
        self.assertLess(command_runtime_index, strict_preview_index)
        self.assertIn(
            "      - name: Run Windows command runtime smoke\n        run: python -m pytest -q tests/test_command_runtime.py",
            text,
        )

    def test_raw_registry_cross_environment_matrix_job_covers_linux_windows_macos(
        self,
    ) -> None:
        job = _job(_workflow(), "raw-registry-cross-environment")

        self.assertEqual(job.get("name"), "raw-registry-cross-env / ${{ matrix.profile }}")
        self.assertEqual(
            {
                str(item.get("profile")): str(item.get("os"))
                for item in workflow_matrix_include(job)
            },
            {
                "linux-c-utf8": "ubuntu-latest",
                "windows-utf8": "windows-latest",
                "macos-utf8": "macos-latest",
            },
        )
        generate_run = _run_text(_step_by_name(job, "Generate raw registry cross-environment matrix"))
        self.assertIn(
            "python -m ops.scripts.registry.raw_registry_cross_environment_matrix \\",
            generate_run,
        )
        self.assertIn('--profile "${{ matrix.profile }}"', generate_run)
        self.assertIn(
            "ops/reports/raw-registry-cross-environment-matrix-${{ matrix.profile }}.json",
            generate_run,
        )
        upload_with = workflow_mapping(
            _step_by_name(job, "Upload raw registry cross-environment matrix").get("with", {}),
            "raw registry upload with section must be a mapping",
        )
        self.assertEqual(upload_with.get("name"), "raw-registry-cross-environment-${{ matrix.profile }}")

    def test_raw_registry_cross_environment_evidence_job_bundles_uploaded_matrices(
        self,
    ) -> None:
        job = _job(_workflow(), "raw-registry-cross-environment-evidence")

        self.assertEqual(job.get("name"), "raw-registry-cross-env evidence bundle / py3.12")
        self.assertEqual(job.get("needs"), "raw-registry-cross-environment")
        download_with = workflow_mapping(
            _step_by_name(job, "Download raw registry cross-environment matrices").get("with", {}),
            "raw registry download with section must be a mapping",
        )
        self.assertEqual(download_with.get("pattern"), "raw-registry-cross-environment-*")
        self.assertTrue(download_with.get("merge-multiple"))
        generate_step = _step_by_name(job, "Generate raw registry cross-environment evidence bundle")
        self.assertEqual(generate_step.get("id"), "raw_registry_cross_environment_evidence_bundle")
        generate_run = _run_text(generate_step)
        self.assertIn(
            "python -m ops.scripts.registry.raw_registry_cross_environment_evidence_bundle \\",
            generate_run,
        )
        self.assertIn("--reports-dir ops/reports", generate_run)
        self.assertIn(
            "ops/reports/raw-registry-cross-environment-evidence-bundle.json",
            generate_run,
        )
        diagnostics = _step_by_name(job, "Materialize raw registry evidence upload diagnostics")
        self.assertEqual(
            diagnostics.get("if"),
            "always() && steps.raw_registry_cross_environment_evidence_bundle.outcome != 'success'",
        )
        self.assertIn(
            "tmp/raw-registry-cross-environment-evidence-bundle-upload-diagnostics.txt",
            _run_text(diagnostics),
        )
        upload_with = workflow_mapping(
            _step_by_name(job, "Upload raw registry cross-environment evidence bundle").get("with", {}),
            "raw registry evidence upload with section must be a mapping",
        )
        self.assertEqual(upload_with.get("name"), "raw-registry-cross-environment-evidence-bundle")
        self.assertEqual(
            _path_entries(_step_by_name(job, "Upload raw registry cross-environment evidence bundle")),
            (
                "ops/reports/raw-registry-cross-environment-evidence-bundle.json",
                "tmp/raw-registry-cross-environment-evidence-bundle-upload-diagnostics.txt",
            ),
        )


if __name__ == "__main__":
    unittest.main()
