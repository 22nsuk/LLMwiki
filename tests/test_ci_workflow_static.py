from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from ops.scripts.test_lane_registry_runtime import (
    compatibility_map,
    compatibility_names,
    lane_ci_steps,
    load_registry,
    pack_by_id,
    pack_ci_steps,
)
from tests.workflow_static_helpers import (
    assert_locked_install_shape as _assert_locked_install_shape,
    assert_workflow_run_contains as _assert_run_contains,
    load_workflow,
    workflow_job as _job,
    workflow_path_entries as _path_entries,
    workflow_run_commands as _run_commands,
    workflow_run_text as _run_text,
    workflow_step as _step,
    workflow_steps as _steps,
)


CI_WORKFLOW = Path(".github/workflows/ci.yml")

pytestmark = pytest.mark.report_contract


def _workflow() -> dict[str, object]:
    return load_workflow(CI_WORKFLOW)


class CiWorkflowStaticTests(unittest.TestCase):
    def test_ci_matrix_tiers_match_registry_compatibility_contract(self) -> None:
        registry = load_registry(Path("."))
        workflow = _workflow()

        jobs = workflow.get("jobs", {})
        self.assertIsInstance(jobs, dict)
        test_tier_job = jobs.get("test-tier", {})
        self.assertIsInstance(test_tier_job, dict)
        strategy = test_tier_job.get("strategy", {})
        self.assertIsInstance(strategy, dict)
        matrix = strategy.get("matrix", {})
        self.assertIsInstance(matrix, dict)
        tiers = matrix.get("tier", [])
        self.assertIsInstance(tiers, list)
        self.assertEqual(tuple(tiers), compatibility_names(registry, "ci_tier"))

    def test_ci_matrix_covers_supported_python_minor_versions(self) -> None:
        workflow = _workflow()

        jobs = workflow.get("jobs", {})
        self.assertIsInstance(jobs, dict)
        test_tier_job = jobs.get("test-tier", {})
        self.assertIsInstance(test_tier_job, dict)
        strategy = test_tier_job.get("strategy", {})
        self.assertIsInstance(strategy, dict)
        matrix = strategy.get("matrix", {})
        self.assertIsInstance(matrix, dict)
        versions = matrix.get("python-version", [])
        self.assertIsInstance(versions, list)
        self.assertEqual(tuple(versions), ("3.12", "3.13", "3.14"))

    def test_ci_dependency_cache_tracks_canonical_lockfile(self) -> None:
        workflow = _workflow()

        _assert_locked_install_shape(self, workflow, expected_job_count=5)
        self.assertNotIn(
            "python -m pip install -r requirements-dev.txt build",
            _run_commands(_job(workflow, "test-tier")),
        )

    def test_ci_tier_commands_match_registry_contract(self) -> None:
        registry = load_registry(Path("."))
        workflow = _workflow()
        test_tier_run = _run_commands(_job(workflow, "test-tier"))

        for tier, mapped_id in compatibility_map(registry, "ci_tier").items():
            with self.subTest(tier=tier, mapped_id=mapped_id):
                steps = (
                    pack_ci_steps(registry, mapped_id)
                    if mapped_id in pack_by_id(registry)
                    else lane_ci_steps(registry, mapped_id)
                )
                self.assertTrue(steps)
                for step in steps:
                    self.assertIn(step, test_tier_run)

    def test_ci_workflow_has_windows_release_smoke_job(self) -> None:
        workflow = _workflow()
        job = _job(workflow, "windows-release-smoke")

        self.assertEqual(job.get("name"), "windows-release-smoke / py3.12")
        self.assertEqual(job.get("runs-on"), "windows-latest")
        self.assertEqual(job.get("env"), {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        setup_python = _step(job, "Setup Python")
        setup_python_with = setup_python.get("with", {})
        self.assertIsInstance(setup_python_with, dict)
        self.assertEqual(setup_python_with.get("python-version"), "3.12")
        _step(job, "Install dependencies from lock")
        _assert_run_contains(
            self,
            _step(job, "Run Windows release smoke"),
            (
                "python -m ops.scripts.release.release_smoke",
                "--vault .",
                "--profile full",
                "--out ops/reports/release-smoke-report-windows.json",
            ),
        )
        _assert_run_contains(
            self,
            _step(job, "Run Windows command runtime smoke"),
            ("python -m pytest -q tests/test_command_runtime.py",),
        )
        _assert_run_contains(
            self,
            _step(job, "Run Windows strict preview smoke"),
            (
                "python .\\tools\\ruff_strict_preview.py",
                "--allowlist ops/ruff-strict-preview-allowlist.txt",
                "python -m mypy",
                "@ops/mypy-strict-preview-allowlist.txt",
            ),
        )
        _assert_run_contains(
            self,
            _step(job, "Run Windows schema and allowlist smoke tests"),
            (
                "tests/test_ci_workflow_static.py",
                "tests/test_makefile_static_gates.py",
                "tests/test_report_schema_sample_regeneration.py",
                "tests/test_report_schemas.py",
                "tests/test_ruff_strict_preview.py",
            ),
        )
        upload = _step(job, "Upload Windows smoke artifact")
        upload_with = upload.get("with", {})
        self.assertIsInstance(upload_with, dict)
        self.assertEqual(upload_with.get("name"), "windows-release-smoke-report")
        self.assertEqual(
            upload_with.get("path"), "ops/reports/release-smoke-report-windows.json"
        )

    def test_fast_tier_runs_release_smoke_fast_when_full_vault_is_present(self) -> None:
        workflow = _workflow()
        run = _run_text(_step(_job(workflow, "test-tier"), "Run fast contract tier"))

        self.assertIn(
            "if [ -f system/system-index.md ] && [ -f wiki/index.md ] && [ -d raw ]; then",
            run,
        )
        self.assertIn("make check-finalized", run)
        self.assertIn("make release-smoke-fast", run)

    def test_release_closeout_regression_tier_uploads_cost_evidence(self) -> None:
        workflow = _workflow()
        job = _job(workflow, "test-tier")
        matrix = job.get("strategy", {}).get("matrix", {})
        self.assertIsInstance(matrix, dict)
        self.assertIn("release-closeout-regression", matrix.get("tier", []))
        _assert_run_contains(
            self,
            _step(job, "Run release closeout regression tier"),
            (
                "make release-workflow-order-guard",
                "make release-closeout-regression-dry-run",
                "make release-authority-sealed-preflight",
                "make release-closeout-post-check-finalizer-ci-artifact",
                "make release-closeout-cost-evidence-ci-artifact",
            ),
        )
        cost_upload = _step(job, "Upload release closeout cost evidence")
        cost_upload_with = cost_upload.get("with", {})
        self.assertIsInstance(cost_upload_with, dict)
        self.assertEqual(
            cost_upload_with.get("name"),
            "release-closeout-cost-evidence-${{ matrix.python-version }}",
        )
        for path in (
            "tmp/release-closeout-fixed-point-cost-trend-ci.json",
            "ops/reports/release-closeout-fixed-point.json",
            "ops/reports/release-closeout-fixed-point-cost-trend.json",
            "ops/reports/release-evidence-dashboard.json",
            "tmp/release-workflow-order-guard.json",
            "tmp/release-closeout-post-check-finalizer.json",
            "tmp/release-closeout-post-check-finalizer-recommended-targets.txt",
            "tmp/release-closeout-post-check-finalizer-plan.json",
        ):
            self.assertIn(path, _path_entries(cost_upload))
        blocked_upload = _step(job, "Upload release authority blocked preflight")
        blocked_upload_with = blocked_upload.get("with", {})
        self.assertIsInstance(blocked_upload_with, dict)
        self.assertEqual(
            blocked_upload_with.get("name"),
            "release-authority-blocked-preflight-${{ matrix.python-version }}",
        )
        for path in (
            "tmp/release-closeout-sealed-dry-run/LLMwiki-source.zip",
            "tmp/release-closeout-sealed-dry-run/release-closeout-batch-manifest.json",
            "tmp/release-closeout-sealed-dry-run/external-report-reference-manifest.json",
            "tmp/release-closeout-sealed-dry-run/release-closeout-sealed-rehearsal-check.json",
        ):
            self.assertIn(path, _path_entries(blocked_upload))

    def test_windows_command_runtime_smoke_step_runs_between_release_and_preview(
        self,
    ) -> None:
        workflow = _workflow()
        step_names = [str(step.get("name", "")) for step in _steps(_job(workflow, "windows-release-smoke"))]

        release_index = step_names.index("Run Windows release smoke")
        command_runtime_index = step_names.index("Run Windows command runtime smoke")
        strict_preview_index = step_names.index("Run Windows strict preview smoke")

        self.assertLess(release_index, command_runtime_index)
        self.assertLess(command_runtime_index, strict_preview_index)
        _assert_run_contains(
            self,
            _step(_job(workflow, "windows-release-smoke"), "Run Windows command runtime smoke"),
            ("python -m pytest -q tests/test_command_runtime.py",),
        )

    def test_raw_registry_cross_environment_matrix_job_covers_linux_windows_macos(
        self,
    ) -> None:
        workflow = _workflow()
        job = _job(workflow, "raw-registry-cross-environment")

        self.assertEqual(job.get("name"), "raw-registry-cross-env / ${{ matrix.profile }}")
        strategy = job.get("strategy", {})
        self.assertIsInstance(strategy, dict)
        matrix = strategy.get("matrix", {})
        self.assertIsInstance(matrix, dict)
        self.assertEqual(
            tuple(matrix.get("include", [])),
            (
                {"os": "ubuntu-latest", "profile": "linux-c-utf8"},
                {"os": "windows-latest", "profile": "windows-utf8"},
                {"os": "macos-latest", "profile": "macos-utf8"},
            ),
        )
        _assert_run_contains(
            self,
            _step(job, "Generate raw registry cross-environment matrix"),
            (
                "python -m ops.scripts.registry.raw_registry_cross_environment_matrix",
                '--profile "${{ matrix.profile }}"',
                'ops/reports/raw-registry-cross-environment-matrix-${{ matrix.profile }}.json',
            ),
        )
        upload = _step(job, "Upload raw registry cross-environment matrix")
        upload_with = upload.get("with", {})
        self.assertIsInstance(upload_with, dict)
        self.assertEqual(
            upload_with.get("name"),
            "raw-registry-cross-environment-${{ matrix.profile }}",
        )

    def test_raw_registry_cross_environment_evidence_job_bundles_uploaded_matrices(
        self,
    ) -> None:
        workflow = _workflow()
        job = _job(workflow, "raw-registry-cross-environment-evidence")

        self.assertEqual(job.get("name"), "raw-registry-cross-env evidence bundle / py3.12")
        self.assertEqual(job.get("needs"), "raw-registry-cross-environment")
        download = _step(job, "Download raw registry cross-environment matrices")
        download_with = download.get("with", {})
        self.assertIsInstance(download_with, dict)
        self.assertEqual(download_with.get("pattern"), "raw-registry-cross-environment-*")
        self.assertIs(download_with.get("merge-multiple"), True)
        _assert_run_contains(
            self,
            _step(job, "Generate raw registry cross-environment evidence bundle"),
            (
                "python -m ops.scripts.registry.raw_registry_cross_environment_evidence_bundle",
                "--reports-dir ops/reports",
                "ops/reports/raw-registry-cross-environment-evidence-bundle.json",
            ),
        )
        upload = _step(job, "Upload raw registry cross-environment evidence bundle")
        upload_with = upload.get("with", {})
        self.assertIsInstance(upload_with, dict)
        self.assertEqual(
            upload_with.get("name"), "raw-registry-cross-environment-evidence-bundle"
        )


if __name__ == "__main__":
    unittest.main()
