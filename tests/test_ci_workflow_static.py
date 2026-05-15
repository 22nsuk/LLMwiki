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


CI_WORKFLOW = Path(".github/workflows/ci.yml")

pytestmark = pytest.mark.report_contract


def _workflow() -> dict[str, object]:
    payload = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


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
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("uv.lock", text)
        self.assertEqual(text.count("            uv.lock"), 5)
        self.assertEqual(text.count("uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"), 5)
        self.assertEqual(
            text.count("uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt"),
            5,
        )
        self.assertEqual(text.count("python -m pip install -r tmp/locked-requirements.ci.txt"), 5)
        self.assertNotIn("python -m pip install -r requirements-dev.txt build", text)

    def test_ci_tier_commands_match_registry_contract(self) -> None:
        registry = load_registry(Path("."))
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        for tier, mapped_id in compatibility_map(registry, "ci_tier").items():
            with self.subTest(tier=tier, mapped_id=mapped_id):
                steps = (
                    pack_ci_steps(registry, mapped_id)
                    if mapped_id in pack_by_id(registry)
                    else lane_ci_steps(registry, mapped_id)
                )
                self.assertTrue(steps)
                for step in steps:
                    self.assertIn(step, text)

    def test_ci_workflow_has_windows_release_smoke_job(self) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("windows-release-smoke:", text)
        self.assertIn("name: windows-release-smoke / py3.12", text)
        self.assertIn("runs-on: windows-latest", text)
        self.assertIn('PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"', text)
        self.assertIn('python-version: "3.12"', text)
        self.assertIn("Install dependencies from lock", text)
        self.assertIn(
            "python -m ops.scripts.release.release_smoke --vault . --profile full --out ops/reports/release-smoke-report-windows.json",
            text,
        )
        self.assertIn(
            "python -m pytest -q tests/test_command_runtime.py",
            text,
        )
        self.assertIn(
            "python .\\tools\\ruff_strict_preview.py --vault . --allowlist ops/ruff-strict-preview-allowlist.txt --select B,SIM,UP,I",
            text,
        )
        self.assertIn(
            "python -m mypy --config-file pyproject.toml --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs @ops/mypy-strict-preview-allowlist.txt",
            text,
        )
        self.assertIn(
            "python -m pytest -q tests/test_ci_workflow_static.py tests/test_makefile_static_gates.py tests/test_report_schema_sample_regeneration.py tests/test_report_schemas.py tests/test_ruff_strict_preview.py",
            text,
        )
        self.assertIn("name: windows-release-smoke-report", text)
        self.assertIn("path: ops/reports/release-smoke-report-windows.json", text)

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
        self.assertIn("tmp/release-workflow-order-guard.json", text)
        self.assertIn(
            "tmp/release-closeout-sealed-dry-run/LLMwiki-source.zip", text
        )
        self.assertIn(
            "tmp/release-closeout-sealed-dry-run/release-closeout-batch-manifest.json",
            text,
        )
        self.assertIn(
            "tmp/release-closeout-sealed-dry-run/external-report-reference-manifest.json",
            text,
        )
        self.assertIn(
            "tmp/release-closeout-sealed-dry-run/release-closeout-sealed-rehearsal-check.json",
            text,
        )
        self.assertIn("tmp/release-closeout-post-check-finalizer.json", text)
        self.assertIn(
            "tmp/release-closeout-post-check-finalizer-recommended-targets.txt", text
        )
        self.assertIn("tmp/release-closeout-post-check-finalizer-plan.json", text)

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
