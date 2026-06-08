from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.raw_registry_cross_environment_evidence_bundle import (
    DEFAULT_EXPECTED_PROFILES,
    build_evidence_bundle,
    main as evidence_bundle_main,
    write_report as write_evidence_bundle,
)
from ops.scripts.raw_registry_cross_environment_matrix import (
    build_matrix_report,
    write_report as write_matrix_report,
)
from ops.scripts.raw_registry_preflight import (
    preflight,
    write_report as write_preflight_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.report_contract


REPO_ROOT = Path(__file__).resolve().parents[1]


def fixed_context(hour: int = 0) -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 29, hour, 0, tzinfo=dt.UTC),
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


def _prepare_vault(vault: Path) -> None:
    seed_minimal_vault(vault)
    _write_ci_workflow(vault)
    live_report = preflight(vault, context=fixed_context())
    write_preflight_report(vault, live_report, None)


def _write_profile_matrix(vault: Path, profile: str) -> Path:
    report = build_matrix_report(vault, profile=profile, context=fixed_context())
    return write_matrix_report(
        vault,
        report,
        f"ops/reports/raw-registry-cross-environment-matrix-{profile}.json",
    )


class RawRegistryCrossEnvironmentEvidenceBundleTest(unittest.TestCase):
    def test_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            _prepare_vault(vault)
            for profile in DEFAULT_EXPECTED_PROFILES:
                _write_profile_matrix(vault, profile)

            completed = invoke_cli_main(
                evidence_bundle_main,
                [
                    "--vault",
                    str(vault),
                    "--reports-dir",
                    "ops/reports",
                    "--out",
                    "reports/raw-registry/cross-environment-evidence-bundle.json",
                ],
                cwd=launcher,
            )
            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)

            report_path = vault / "reports" / "raw-registry" / "cross-environment-evidence-bundle.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["$schema"],
                RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH,
            )
            self.assertEqual(payload["status"], "pass")

    def test_complete_bundle_collects_profiles_and_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _prepare_vault(vault)
            for profile in DEFAULT_EXPECTED_PROFILES:
                _write_profile_matrix(vault, profile)

            report = build_evidence_bundle(vault, context=fixed_context())
            schema = load_schema(REPO_ROOT / RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH)
            evidence_by_profile = {item["profile"]: item for item in report["evidence"]}

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["artifact_kind"], "raw_registry_cross_environment_evidence_bundle")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["valid_report_count"], 3)
            self.assertEqual(report["diagnostics"], [])
            self.assertEqual(set(evidence_by_profile), set(DEFAULT_EXPECTED_PROFILES))
            self.assertEqual(evidence_by_profile["linux-c-utf8"]["runner_os"], "ubuntu-latest")
            self.assertEqual(evidence_by_profile["windows-utf8"]["runner_os"], "windows-latest")
            self.assertEqual(evidence_by_profile["macos-utf8"]["runner_os"], "macos-latest")
            for profile, item in evidence_by_profile.items():
                self.assertEqual(item["semantic_compare_status"], "pass")
                self.assertEqual(item["uploaded_artifact_name"], f"raw-registry-cross-environment-{profile}")
                self.assertTrue(item["report_path"].startswith("ops/reports/"))
                self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")

            destination = write_evidence_bundle(vault, report, None)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)

    def test_missing_and_invalid_reports_are_diagnosed_without_schema_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _prepare_vault(vault)
            _write_profile_matrix(vault, "linux-c-utf8")
            invalid_path = vault / "ops" / "reports" / "raw-registry-cross-environment-matrix-windows-utf8.json"
            invalid_path.write_text("{not json", encoding="utf-8")

            report = build_evidence_bundle(vault, context=fixed_context())
            schema = load_schema(REPO_ROOT / RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH)
            evidence_by_profile = {item["profile"]: item for item in report["evidence"]}
            diagnostic_codes = {item["code"] for item in report["diagnostics"]}

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["missing_report_count"], 1)
            self.assertEqual(report["summary"]["invalid_report_count"], 1)
            self.assertEqual(evidence_by_profile["linux-c-utf8"]["load_status"], "ok")
            self.assertEqual(evidence_by_profile["windows-utf8"]["load_status"], "decode_error")
            self.assertEqual(evidence_by_profile["macos-utf8"]["load_status"], "missing")
            self.assertIn("report_decode_error", diagnostic_codes)
            self.assertIn("missing_report", diagnostic_codes)
            self.assertEqual(
                {item["code"] for item in report["failure_causes"]},
                {"report_decode_error", "missing_report"},
            )

    def test_semantic_compare_missing_is_a_top_level_failure_cause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _prepare_vault(vault)
            for profile in DEFAULT_EXPECTED_PROFILES:
                _write_profile_matrix(vault, profile)
            linux_path = (
                vault
                / "ops"
                / "reports"
                / "raw-registry-cross-environment-matrix-linux-c-utf8.json"
            )
            payload = json.loads(linux_path.read_text(encoding="utf-8"))
            for row in payload["matrix"]:
                if row.get("profile") == "linux-c-utf8":
                    row["checks"] = [
                        check
                        for check in row.get("checks", [])
                        if check.get("check") != "stored_live_semantic_match"
                    ]
            linux_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            report = build_evidence_bundle(vault, context=fixed_context())
            schema = load_schema(REPO_ROOT / RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH)
            evidence_by_profile = {item["profile"]: item for item in report["evidence"]}

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "fail")
            self.assertEqual(
                evidence_by_profile["linux-c-utf8"]["semantic_compare_status"],
                "missing",
            )
            self.assertIn(
                "semantic_compare_missing",
                {item["code"] for item in evidence_by_profile["linux-c-utf8"]["diagnostics"]},
            )
            self.assertEqual(
                [item["code"] for item in report["failure_causes"]],
                ["semantic_compare_missing"],
            )

    def test_single_matrix_fallback_is_reported_separately_from_missing_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _prepare_vault(vault)
            single_matrix = build_matrix_report(vault, profile="linux-c-utf8", context=fixed_context())
            write_matrix_report(
                vault,
                single_matrix,
                "ops/reports/raw-registry-cross-environment-matrix.json",
            )

            report = build_evidence_bundle(vault, context=fixed_context())
            schema = load_schema(REPO_ROOT / RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_SCHEMA_PATH)
            fallback_diagnostics = [
                item for item in report["diagnostics"] if item["code"] == "single_matrix_fallback_present"
            ]

            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["missing_report_count"], 3)
            self.assertEqual(len(fallback_diagnostics), 1)
            self.assertEqual(fallback_diagnostics[0]["severity"], "info")
            self.assertEqual(
                fallback_diagnostics[0]["path"],
                "ops/reports/raw-registry-cross-environment-matrix.json",
            )

    def test_digest_fields_are_deterministic_for_explicit_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _prepare_vault(vault)
            linux_path = _write_profile_matrix(vault, "linux-c-utf8")
            macos_path = _write_profile_matrix(vault, "macos-utf8")
            report_args = [
                "ops/reports/raw-registry-cross-environment-matrix-macos-utf8.json",
                "ops/reports/raw-registry-cross-environment-matrix-linux-c-utf8.json",
            ]

            first = build_evidence_bundle(vault, reports=report_args, context=fixed_context(1))
            second = build_evidence_bundle(vault, reports=report_args, context=fixed_context(2))
            first_by_profile = {item["profile"]: item for item in first["evidence"]}
            second_by_profile = {item["profile"]: item for item in second["evidence"]}
            linux_sha = hashlib.sha256(linux_path.read_bytes()).hexdigest()
            macos_sha = hashlib.sha256(macos_path.read_bytes()).hexdigest()

            self.assertEqual([item["profile"] for item in first["evidence"]], ["linux-c-utf8", "macos-utf8"])
            self.assertEqual(first_by_profile["linux-c-utf8"]["sha256"], linux_sha)
            self.assertEqual(first_by_profile["macos-utf8"]["sha256"], macos_sha)
            self.assertEqual(first_by_profile["linux-c-utf8"]["sha256"], second_by_profile["linux-c-utf8"]["sha256"])
            self.assertEqual(first["input_fingerprints"]["report_linux-c-utf8"], linux_sha)
            self.assertEqual(first["input_fingerprints"]["report_macos-utf8"], macos_sha)


if __name__ == "__main__":
    unittest.main()
