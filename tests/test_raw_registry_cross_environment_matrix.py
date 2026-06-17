from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.registry.raw_registry_cross_environment_matrix import (
    build_matrix_report,
    main as matrix_main,
    write_report as write_matrix_report,
)
from ops.scripts.registry.raw_registry_preflight import (
    preflight,
    write_report as write_preflight_report,
)
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.report_contract


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 29, 0, 0, tzinfo=dt.UTC),
    )


def _write_ci_workflow(vault: Path) -> None:
    workflow = vault / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        """
raw-registry-cross-environment:
  name: raw-registry-cross-env / ${{ matrix.profile }}
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
      include:
        - os: ubuntu-latest
          profile: linux-c-utf8
        - os: windows-latest
          profile: windows-utf8
        - os: macos-latest
          profile: macos-utf8
  steps:
    - run: python -m ops.scripts.registry.raw_registry_cross_environment_matrix --profile "${{ matrix.profile }}"
    - uses: actions/upload-artifact@v4
      with:
        name: raw-registry-cross-environment-${{ matrix.profile }}
""",
        encoding="utf-8",
    )


def _remove_raw_inputs(vault: Path) -> None:
    raw_dir = vault / "raw"
    for path in raw_dir.iterdir():
        path.unlink()
    raw_dir.rmdir()


class RawRegistryCrossEnvironmentMatrixTest(unittest.TestCase):
    def test_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            _write_ci_workflow(vault)
            live_report = preflight(vault, context=fixed_context())
            write_preflight_report(vault, live_report, None)

            completed = invoke_cli_main(
                matrix_main,
                [
                    "--vault",
                    str(vault),
                    "--profile",
                    "linux-c-utf8",
                    "--stored-report",
                    "ops/reports/raw-registry-preflight-report.json",
                    "--out",
                    "reports/raw-registry/cross-environment-matrix.json",
                ],
                cwd=launcher,
            )
            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)

            report_path = vault / "reports" / "raw-registry" / "cross-environment-matrix.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH)
            self.assertEqual(payload["status"], "pass")

    def test_matrix_report_covers_live_fixture_and_ci_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            _write_ci_workflow(vault)
            live_report = preflight(vault, context=fixed_context())
            write_preflight_report(vault, live_report, None)

            report = build_matrix_report(
                vault,
                profile="linux-c-utf8",
                require_live=True,
                context=fixed_context(),
            )
            schema = load_schema(vault / RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH)
            rows = {item["profile"]: item for item in report["matrix"]}

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["artifact_kind"], "raw_registry_cross_environment_matrix")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(rows["linux-c-utf8"]["evidence_mode"], "live_preflight_and_ci_workflow")
            self.assertEqual(rows["windows-utf8"]["evidence_mode"], "ci_workflow")
            self.assertEqual(rows["macos-utf8"]["evidence_mode"], "ci_workflow")
            self.assertEqual(rows["path-separator-fixture"]["status"], "pass")
            self.assertEqual(rows["locale-utf8-fixture"]["status"], "pass")
            self.assertTrue(report["semantic_compare_fields"])

    def test_matrix_report_warns_when_public_checkout_skips_live_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            _write_ci_workflow(vault)
            live_report = preflight(vault, context=fixed_context())
            write_preflight_report(vault, live_report, None)
            _remove_raw_inputs(vault)

            report = build_matrix_report(
                vault,
                profile="linux-c-utf8",
                context=fixed_context(),
            )
            schema = load_schema(vault / RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH)
            live_row = next(item for item in report["matrix"] if item["profile"] == "linux-c-utf8")
            checks = {item["check"]: item for item in live_row["checks"]}

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "warn")
            self.assertEqual(live_row["status"], "skipped")
            self.assertEqual(checks["live_preflight_available"]["status"], "skipped")
            self.assertEqual(checks["stored_live_semantic_match"]["status"], "skipped")
            self.assertIn("full-vault inputs", checks["stored_live_semantic_match"]["detail"])

    def test_matrix_report_fails_when_live_full_vault_is_required_but_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            _write_ci_workflow(vault)
            live_report = preflight(vault, context=fixed_context())
            write_preflight_report(vault, live_report, None)
            _remove_raw_inputs(vault)

            report = build_matrix_report(
                vault,
                profile="linux-c-utf8",
                require_live=True,
                context=fixed_context(),
            )

            self.assertEqual(report["status"], "fail")
            live_row = next(item for item in report["matrix"] if item["profile"] == "linux-c-utf8")
            checks = {item["check"]: item for item in live_row["checks"]}
            self.assertEqual(live_row["status"], "fail")
            self.assertEqual(checks["live_preflight_available"]["status"], "fail")
            self.assertEqual(checks["stored_live_semantic_match"]["status"], "fail")

    def test_require_live_fails_when_stored_preflight_report_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            _write_ci_workflow(vault)

            report = build_matrix_report(
                vault,
                profile="linux-c-utf8",
                require_live=True,
                context=fixed_context(),
            )
            schema = load_schema(vault / RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_SCHEMA_PATH)
            live_row = next(item for item in report["matrix"] if item["profile"] == "linux-c-utf8")
            checks = {item["check"]: item for item in live_row["checks"]}

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "fail")
            self.assertEqual(checks["live_preflight_status"]["status"], "pass")
            self.assertEqual(checks["stored_live_semantic_match"]["status"], "fail")

    def test_write_matrix_report_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            _write_ci_workflow(vault)
            live_report = preflight(vault, context=fixed_context())
            write_preflight_report(vault, live_report, None)
            report = build_matrix_report(
                vault,
                profile="linux-c-utf8",
                context=fixed_context(),
            )

            destination = write_matrix_report(vault, report, None)

            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                report,
            )


if __name__ == "__main__":
    unittest.main()
