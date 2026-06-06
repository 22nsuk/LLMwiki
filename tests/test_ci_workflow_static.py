from __future__ import annotations

import unittest
from pathlib import Path

import pytest
import yaml
from ops.scripts.test_lane_registry_runtime import (
    compatibility_map,
    compatibility_names,
    lane_ci_steps,
    load_registry,
    pack_by_id,
    pack_ci_steps,
)

from tests.workflow_static_helpers import (
    PINNED_CHECKOUT_ACTION,
    PINNED_DEPENDENCY_REVIEW_ACTION,
    PINNED_DOWNLOAD_ARTIFACT_ACTION,
    PINNED_SETUP_PYTHON_ACTION,
    PINNED_SETUP_UV_ACTION,
    PINNED_UPLOAD_ARTIFACT_ACTION,
    assert_workflow_uses_are_sha_pinned,
    load_workflow,
    workflow_job,
    workflow_jobs,
    workflow_mapping,
    workflow_matrix_tier_run_text,
    workflow_matrix_values,
    workflow_step,
)

CI_WORKFLOW = Path(".github/workflows/ci.yml")
RELEASE_WORKFLOW = Path(".github/workflows/release.yml")
CODEQL_WORKFLOW = Path(".github/workflows/codeql.yml")
DEPENDENCY_REVIEW_WORKFLOW = Path(".github/workflows/dependency-review.yml")
DEPENDABOT_CONFIG = Path(".github/dependabot.yml")

pytestmark = pytest.mark.report_contract


def _workflow() -> dict[str, object]:
    return load_workflow(CI_WORKFLOW)


def _jobs(workflow: dict[str, object]) -> dict[str, object]:
    return workflow_mapping(workflow.get("jobs", {}), "workflow jobs must be a mapping")


def _job(workflow: dict[str, object], name: str) -> dict[str, object]:
    return workflow_mapping(
        _jobs(workflow).get(name, {}),
        f"workflow job must be a mapping: {name}",
    )


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        raise AssertionError("workflow job steps must be a list")
    return [workflow_mapping(step, "workflow step must be a mapping") for step in steps if isinstance(step, dict)]


def _step_by_name(job: dict[str, object], name: str) -> dict[str, object]:
    for step in _steps(job):
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing workflow step: {name}")


def _run_text(step: dict[str, object]) -> str:
    return str(step.get("run", ""))


def _assert_locked_dependency_steps(case: unittest.TestCase, job: dict[str, object]) -> None:
    setup_python = _step_by_name(job, "Setup Python")
    setup_uv = _step_by_name(job, "Setup uv")
    install_steps = [
        step
        for step in _steps(job)
        if str(step.get("name", "")).startswith("Install dependencies")
    ]

    case.assertEqual(setup_python.get("uses"), PINNED_SETUP_PYTHON_ACTION)
    with_config = workflow_mapping(
        setup_python.get("with", {}),
        "setup-python with section must be a mapping",
    )
    case.assertIn("uv.lock", str(with_config.get("cache-dependency-path", "")))
    case.assertNotIn("requirements.txt", str(with_config.get("cache-dependency-path", "")))
    case.assertNotIn("requirements-dev.txt", str(with_config.get("cache-dependency-path", "")))
    case.assertEqual(
        setup_uv.get("uses"),
        PINNED_SETUP_UV_ACTION,
    )
    case.assertEqual(len(install_steps), 1)
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
                for job_name, job in workflow_jobs(workflow).items():
                    with self.subTest(workflow=str(workflow_path), job=job_name):
                        self.assertIsInstance(job, dict)
                        timeout_minutes = job.get("timeout-minutes")
                        self.assertIsInstance(timeout_minutes, int)
                        self.assertGreater(timeout_minutes, 0)

        codeql = load_workflow(CODEQL_WORKFLOW)
        codeql_job = workflow_job(codeql, "analyze")
        self.assertEqual(
            codeql_job.get("permissions"),
            {"actions": "read", "contents": "read", "security-events": "write"},
        )
        self.assertEqual(workflow_step(codeql_job, "Checkout").get("uses"), PINNED_CHECKOUT_ACTION)
        self.assertRegex(
            str(workflow_step(codeql_job, "Initialize CodeQL").get("uses")),
            r"^github/codeql-action/init@[0-9a-f]{40}$",
        )
        self.assertRegex(
            str(workflow_step(codeql_job, "Perform CodeQL Analysis").get("uses")),
            r"^github/codeql-action/analyze@[0-9a-f]{40}$",
        )

        dependency_review = load_workflow(DEPENDENCY_REVIEW_WORKFLOW)
        review_job = workflow_job(dependency_review, "dependency-review")
        self.assertEqual(
            workflow_step(review_job, "Dependency Review").get("uses"),
            PINNED_DEPENDENCY_REVIEW_ACTION,
        )
        self.assertEqual(
            workflow_mapping(
                workflow_step(review_job, "Dependency Review").get("with", {}),
                "dependency review with section must be a mapping",
            ).get("fail-on-severity"),
            "moderate",
        )

    def test_ci_matrix_tiers_match_registry_compatibility_contract(self) -> None:
        registry = load_registry(Path("."))
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

    def test_ci_dependency_cache_tracks_canonical_lockfile(self) -> None:
        workflow = _workflow()

        for job_name in _jobs(workflow):
            with self.subTest(job_name=job_name):
                _assert_locked_dependency_steps(self, _job(workflow, job_name))

    def test_ci_tier_commands_match_registry_contract(self) -> None:
        registry = load_registry(Path("."))
        workflow = _workflow()
        test_tier_job = _job(workflow, "test-tier")

        for tier, mapped_id in compatibility_map(registry, "ci_tier").items():
            with self.subTest(tier=tier, mapped_id=mapped_id):
                steps = (
                    pack_ci_steps(registry, mapped_id)
                    if mapped_id in pack_by_id(registry)
                    else lane_ci_steps(registry, mapped_id)
                )
                self.assertTrue(steps)
                tier_run_text = workflow_matrix_tier_run_text(test_tier_job, tier)
                self.assertTrue(
                    tier_run_text,
                    f"missing exact matrix.tier run step for {tier!r}",
                )
                for step in steps:
                    self.assertIn(step, tier_run_text)

        report_contract_run_text = workflow_matrix_tier_run_text(
            test_tier_job,
            "report-contract",
        )
        self.assertIn("make test-report-contract-all", report_contract_run_text)
        self.assertNotIn("make test-report-contract-core", report_contract_run_text)

    def test_ci_workflow_has_windows_release_smoke_job(self) -> None:
        workflow = _workflow()
        job = _job(workflow, "windows-release-smoke")
        steps = _steps(job)
        step_names = {str(step.get("name", "")) for step in steps}

        self.assertEqual(job.get("name"), "windows-release-smoke / py3.12")
        self.assertEqual(job.get("runs-on"), "windows-latest")
        env = workflow_mapping(job.get("env", {}), "windows release smoke env must be a mapping")
        self.assertEqual(env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD"), "1")
        setup_python_with = workflow_mapping(
            _step_by_name(job, "Setup Python").get("with", {}),
            "windows setup-python with section must be a mapping",
        )
        self.assertEqual(
            setup_python_with.get("python-version"),
            "3.12",
        )
        self.assertIn("Install dependencies from lock", step_names)
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
            _step_by_name(job, "Run Windows schema and strict-preview smoke tests")
        )
        self.assertIn("python -m pytest -q", schema_static_smoke_run)
        for test_path in (
            "tests/test_ci_workflow_static.py",
            "tests/test_makefile_static_gates.py",
            "tests/test_makefile_release_orchestration_static_gates.py",
            "tests/test_makefile_release_evidence_static_gates.py",
            "tests/test_makefile_release_smoke_static_gates.py",
            "tests/test_makefile_test_execution_summary_gates.py",
            "tests/test_makefile_auto_improve_goal_static_gates.py",
            "tests/test_makefile_public_registry_supply_chain_gates.py",
            "tests/test_report_schema_sample_regeneration.py",
            "tests/test_report_schemas.py",
            "tests/test_ruff_strict_preview.py",
            "tests/test_strict_preview_audit.py",
        ):
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, schema_static_smoke_run)
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
        self.assertIn("            make check-finalized", text)
        self.assertIn("            make release-smoke-fast", text)

    def test_release_closeout_regression_tier_uploads_cost_evidence(self) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("- release-closeout-regression", text)
        self.assertIn("make release-workflow-order-guard", text)
        self.assertIn("make release-closeout-regression-dry-run", text)
        self.assertIn("make release-authority-sealed-preflight", text)
        self.assertIn("make release-closeout-post-check-finalizer-ci-artifact", text)
        self.assertIn("make release-closeout-cost-evidence-ci-artifact", text)
        self.assertIn(
            "name: release-closeout-cost-evidence-${{ matrix.python-version }}", text
        )
        self.assertIn(
            "name: release-authority-blocked-preflight-${{ matrix.python-version }}",
            text,
        )
        self.assertIn("tmp/release-closeout-fixed-point-cost-trend-ci.json", text)
        self.assertIn("ops/reports/release-closeout-fixed-point.json", text)
        self.assertIn("ops/reports/release-closeout-fixed-point-cost-trend.json", text)
        self.assertIn("ops/reports/release-evidence-dashboard.json", text)
        self.assertIn("ops/reports/release-workflow-order-guard.json", text)
        self.assertIn(
            "build/release/release-closeout-sealed-dry-run/LLMwiki-source.zip", text
        )
        self.assertIn(
            "build/release/release-closeout-sealed-dry-run/release-closeout-batch-manifest.json",
            text,
        )
        self.assertIn(
            "build/release/release-closeout-sealed-dry-run/external-report-reference-manifest.json",
            text,
        )
        self.assertIn(
            "build/release/release-closeout-sealed-dry-run/release-closeout-sealed-rehearsal-check.json",
            text,
        )
        self.assertIn("ops/reports/release-closeout-sealed-rehearsal-check.json", text)
        self.assertIn("tmp/release-closeout-post-check-finalizer.json", text)
        self.assertIn(
            "tmp/release-closeout-post-check-finalizer-recommended-targets.txt", text
        )
        self.assertIn("tmp/release-closeout-post-check-finalizer-plan.json", text)

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
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("raw-registry-cross-environment:", text)
        self.assertIn("name: raw-registry-cross-env / ${{ matrix.profile }}", text)
        self.assertIn("profile: linux-c-utf8", text)
        self.assertIn("profile: windows-utf8", text)
        self.assertIn("profile: macos-utf8", text)
        self.assertIn("os: ubuntu-latest", text)
        self.assertIn("os: windows-latest", text)
        self.assertIn("os: macos-latest", text)
        self.assertIn(
            "python -m ops.scripts.registry.raw_registry_cross_environment_matrix \\",
            text,
        )
        self.assertIn('--profile "${{ matrix.profile }}"', text)
        self.assertIn(
            "ops/reports/raw-registry-cross-environment-matrix-${{ matrix.profile }}.json",
            text,
        )
        self.assertIn(
            "name: raw-registry-cross-environment-${{ matrix.profile }}", text
        )

    def test_raw_registry_cross_environment_evidence_job_bundles_uploaded_matrices(
        self,
    ) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("raw-registry-cross-environment-evidence:", text)
        self.assertIn("name: raw-registry-cross-env evidence bundle / py3.12", text)
        self.assertIn("needs: raw-registry-cross-environment", text)
        self.assertIn("pattern: raw-registry-cross-environment-*", text)
        self.assertIn("merge-multiple: true", text)
        self.assertIn(
            "python -m ops.scripts.registry.raw_registry_cross_environment_evidence_bundle \\",
            text,
        )
        self.assertIn("--reports-dir ops/reports", text)
        self.assertIn(
            "ops/reports/raw-registry-cross-environment-evidence-bundle.json", text
        )
        self.assertIn("name: raw-registry-cross-environment-evidence-bundle", text)


if __name__ == "__main__":
    unittest.main()
