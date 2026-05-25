from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.supply_chain_provenance import build_report, write_report

from tests.minimal_vault_runtime import seed_minimal_vault

LOCKED_CI_INSTALL_SNIPPET = (
    '- run: python -c "from pathlib import Path; Path(\'tmp\').mkdir(exist_ok=True)"\n'
    "- run: uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt\n"
    "- run: python -m pip install -r tmp/locked-requirements.ci.txt\n"
)
SOURCE_ZIP_SHA256 = "a" * 64


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 12, 0, tzinfo=dt.UTC),
    )


def seed_dependency_inputs(vault: Path) -> None:
    (vault / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"
dependencies = [
  "PyYAML>=6.0,<7",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (vault / "requirements.txt").write_text("PyYAML>=6.0,<7\n", encoding="utf-8")
    (vault / "requirements-dev.txt").write_text("-r requirements.txt\npytest>=8.3,<9\n", encoding="utf-8")
    (vault / "uv.lock").write_text(
        """
version = 1

[[package]]
name = "pyyaml"
version = "6.0.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [
  { name = "typing-extensions", marker = "python_version >= '3.12'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/pyyaml.tar.gz", hash = "sha256:abc", upload-time = "2026-01-01T00:00:00Z" }
wheels = [
  { url = "https://files.pythonhosted.org/packages/pyyaml.whl", hash = "sha256:def" },
]

[[package]]
name = "typing-extensions"
version = "4.15.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/typing_extensions.tar.gz", hash = "sha256:ghi", upload-time = "2026-01-01T00:00:00Z" }
wheels = [
  { url = "https://files.pythonhosted.org/packages/typing_extensions.whl", hash = "sha256:jkl" },
]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def seed_source_package_evidence(vault: Path, *, status: str = "pass") -> None:
    report_path = vault / "ops" / "reports" / "source-package-clean-extract.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "status": status,
                "source_zip": {
                    "path": "build/source-package-check/LLMwiki-source.zip",
                    "exists": True,
                    "sha256": SOURCE_ZIP_SHA256,
                },
                "source_package_reproducibility_status": status,
                "test_source_package_status": status,
                "zip_smoke_report": {
                    "status": status,
                    "archive_budget_pass": status == "pass",
                    "manifest_comparison_pass": status == "pass",
                },
            }
        ),
        encoding="utf-8",
    )


class SupplyChainProvenanceTests(unittest.TestCase):
    def test_build_report_hashes_inputs_and_parses_dependency_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            seed_source_package_evidence(vault)
            (vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (vault / ".github" / "workflows" / "ci.yml").write_text(
                """
name: CI
jobs:
  test:
    steps:
      - run: python -c "from pathlib import Path; Path('tmp').mkdir(exist_ok=True)"
      - run: uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt
      - run: python -m pip install -r tmp/locked-requirements.ci.txt
""".strip()
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())
            destination = write_report(vault, report, "ops/reports/supply-chain-provenance.json")
            persisted = json.loads(destination.read_text(encoding="utf-8"))

            input_by_path = {item["path"]: item for item in persisted["inputs"]}
            pyproject_bytes = (vault / "pyproject.toml").read_bytes()
            workflow_bytes = (vault / ".github" / "workflows" / "ci.yml").read_bytes()
            self.assertEqual(persisted["status"], "pass")
            self.assertEqual(input_by_path["pyproject.toml"]["sha256"], hashlib.sha256(pyproject_bytes).hexdigest())
            self.assertEqual(input_by_path["uv.lock"]["parser_status"]["status"], "pass")
            self.assertEqual(persisted["declared_dependencies"][0]["name"], "PyYAML")
            self.assertEqual(persisted["dev_dependencies"][0]["name"], "pytest")
            self.assertEqual(persisted["requirements"][0]["requirement"], "PyYAML>=6.0,<7")
            self.assertEqual(persisted["dev_requirements"][0]["kind"], "include")
            self.assertEqual(persisted["locked_packages"][0]["registry"], "https://pypi.org/simple")
            self.assertEqual(persisted["locked_packages"][0]["sdist"]["hash"], "sha256:abc")
            self.assertEqual(persisted["locked_packages"][0]["dependencies"][0]["name"], "typing-extensions")
            self.assertEqual(
                persisted["locked_packages"][0]["dependencies"][0]["marker"],
                "python_version >= '3.12'",
            )
            self.assertIn("uv.lock", persisted["release_manifest"]["dependency_files"])
            self.assertTrue(
                any("frozen locked-requirements install" in note for note in persisted["provenance_notes"])
            )
            self.assertIn("ci_install_proof", persisted)
            self.assertEqual(persisted["ci_install_proof"]["workflow_path"], ".github/workflows/ci.yml")
            self.assertEqual(
                persisted["ci_install_proof"]["workflow_sha256"],
                hashlib.sha256(workflow_bytes).hexdigest(),
            )
            self.assertTrue(persisted["ci_install_proof"]["exports_frozen_uv_lock"])
            self.assertTrue(persisted["ci_install_proof"]["installs_locked_requirements"])
            self.assertEqual(persisted["ci_install_proof"]["locked_requirements_path"], "tmp/locked-requirements.ci.txt")
            self.assertEqual(persisted["ci_install_proof"]["install_resolution_mode"], "canonical_lock_export")
            self.assertFalse(persisted["ci_install_proof"]["installs_requirements_dev"])
            self.assertTrue(persisted["ci_install_proof"]["editable_install"])
            self.assertTrue(persisted["ci_install_proof"]["includes_build_package"])
            self.assertIn(
                "python -m pip install -r tmp/locked-requirements.ci.txt",
                persisted["ci_install_proof"]["install_commands"],
            )
            self.assertIn("lock_evidence", persisted)
            self.assertEqual(persisted["lock_evidence"]["path"], "uv.lock")
            self.assertEqual(persisted["lock_evidence"]["parser_status"]["status"], "pass")
            self.assertTrue(persisted["lock_evidence"]["exists"])
            self.assertEqual(persisted["lock_evidence"]["sha256"], input_by_path["uv.lock"]["sha256"])
            self.assertEqual(persisted["source_package_evidence"]["status"], "pass")
            self.assertEqual(persisted["source_package_evidence"]["source_zip_sha256"], SOURCE_ZIP_SHA256)
            self.assertEqual(
                persisted["source_package_evidence"]["source_package_reproducibility_status"],
                "pass",
            )

    def test_build_report_records_missing_inputs_as_warn_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "pyproject.toml").write_text(
                '[project]\nname = "sample"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            input_by_path = {item["path"]: item for item in report["inputs"]}
            self.assertEqual(report["status"], "warn")
            self.assertFalse(input_by_path["requirements-dev.txt"]["exists"])
            self.assertEqual(input_by_path["requirements-dev.txt"]["parser_status"]["status"], "missing")
            self.assertEqual(report["source_package_evidence"]["status"], "missing")

    def test_build_report_records_malformed_uv_lock_as_parser_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            (vault / "uv.lock").write_text("[[package]\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())

            input_by_path = {item["path"]: item for item in report["inputs"]}
            self.assertEqual(report["status"], "fail")
            self.assertEqual(input_by_path["uv.lock"]["parser_status"]["status"], "error")
            self.assertEqual(report["lock_evidence"]["parser_status"]["status"], "error")
            self.assertEqual(report["locked_packages"], [])


if __name__ == "__main__":
    unittest.main()
