from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.supply_chain.supply_chain_provenance import build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.supply_chain_sample_runtime import (
    LOCKED_CI_INSTALL_SNIPPET,
    LOCKED_COMPOSITE_ACTION_SNIPPET,
    SOURCE_ZIP_SHA256,
    fixed_context,
    seed_dependency_inputs,
    seed_source_package_evidence,
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
      - run: make uv-lock-check
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
            self.assertEqual(input_by_path["pyproject.toml"]["authority_role"], "canonical")
            self.assertEqual(input_by_path["uv.lock"]["authority_role"], "canonical")
            self.assertEqual(input_by_path["requirements.txt"]["authority_role"], "compatibility")
            self.assertEqual(input_by_path["requirements-dev.txt"]["authority_role"], "compatibility")
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
            self.assertEqual(
                persisted["release_manifest"]["canonical_dependency_files"],
                ["pyproject.toml", "uv.lock"],
            )
            self.assertEqual(
                persisted["release_manifest"]["compatibility_dependency_files"],
                ["requirements.txt", "requirements-dev.txt"],
            )
            self.assertEqual(
                persisted["release_manifest"]["dependency_files"],
                ["pyproject.toml", "uv.lock"],
            )
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
            self.assertTrue(persisted["ci_install_proof"]["checks_uv_lock_freshness"])
            self.assertEqual(
                persisted["ci_install_proof"]["lock_check_commands"],
                ["- run: make uv-lock-check"],
            )
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
            self.assertEqual(persisted["lock_evidence"]["lock_check_status"], "enforced")
            self.assertEqual(persisted["lock_evidence"]["lock_check_command"], "uv lock --check")
            self.assertEqual(
                persisted["lock_evidence"]["canonical_lock_check_command"],
                'UV_DEFAULT_INDEX="https://pypi.org/simple" '
                'uv lock --check --default-index "https://pypi.org/simple"',
            )
            self.assertEqual(
                persisted["lock_evidence"]["baseline_environment_lock_check_status"],
                "not_evaluated",
            )
            self.assertEqual(
                persisted["lock_evidence"]["canonical_lock_policy_status"],
                "enforced",
            )
            self.assertEqual(
                persisted["lock_evidence"]["toolchain_alignment_status"],
                "canonical_policy_enforced",
            )
            self.assertEqual(
                persisted["lock_evidence"]["recommended_normalization_step"],
                "none",
            )
            self.assertTrue(persisted["lock_evidence"]["exists"])
            self.assertEqual(persisted["lock_evidence"]["sha256"], input_by_path["uv.lock"]["sha256"])
            self.assertEqual(persisted["source_package_evidence"]["status"], "pass")
            self.assertEqual(persisted["source_package_evidence"]["source_zip_sha256"], SOURCE_ZIP_SHA256)
            self.assertEqual(
                persisted["source_package_evidence"]["source_package_reproducibility_status"],
                "pass",
            )

    def test_build_report_reads_lock_install_proof_from_local_composite_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            (vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (vault / ".github" / "workflows" / "ci.yml").write_text(
                """
name: CI
jobs:
  test:
    steps:
      - uses: ./.github/actions/setup-python-uv
""".strip()
                + "\n",
                encoding="utf-8",
            )
            action_path = vault / ".github" / "actions" / "setup-python-uv" / "action.yml"
            action_path.parent.mkdir(parents=True, exist_ok=True)
            action_path.write_text(LOCKED_COMPOSITE_ACTION_SNIPPET + "\n", encoding="utf-8")

            report = build_report(vault, context=fixed_context())
            proof = report["ci_install_proof"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(proof["checks_uv_lock_freshness"])
            self.assertTrue(proof["exports_frozen_uv_lock"])
            self.assertTrue(proof["installs_locked_requirements"])
            self.assertEqual(proof["lock_check_commands"], ["make uv-lock-check"])
            self.assertEqual(proof["install_resolution_mode"], "canonical_lock_export")
            self.assertIn("python -m pip install --upgrade pip", proof["install_commands"])
            self.assertIn(
                "python -m pip install -r tmp/locked-requirements.ci.txt",
                proof["install_commands"],
            )

    def test_build_report_treats_missing_requirements_files_as_compatibility_not_canonical_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "pyproject.toml").write_text(
                '[project]\nname = "sample"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            (vault / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            (vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (vault / ".github" / "workflows" / "ci.yml").write_text(
                LOCKED_CI_INSTALL_SNIPPET,
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            input_by_path = {item["path"]: item for item in report["inputs"]}
            self.assertEqual(report["status"], "pass")
            self.assertFalse(input_by_path["requirements-dev.txt"]["exists"])
            self.assertEqual(input_by_path["requirements-dev.txt"]["authority_role"], "compatibility")
            self.assertEqual(input_by_path["requirements-dev.txt"]["parser_status"]["status"], "missing")
            envelope = json.loads(
                next(
                    item["value"]
                    for item in report["metadata"]["properties"]
                    if item["name"] == "urn:openai:artifact-envelope"
                )
            )
            self.assertNotIn("requirements-dev.txt", envelope["input_fingerprints"])
            self.assertNotIn("requirements.txt", envelope["input_fingerprints"])
            self.assertEqual(report["source_package_evidence"]["status"], "missing")

    def test_build_report_does_not_treat_plain_uv_lock_check_as_canonical_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_dependency_inputs(vault)
            (vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (vault / ".github" / "workflows" / "ci.yml").write_text(
                """
name: CI
jobs:
  test:
    steps:
      - run: uv lock --check
      - run: uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt
      - run: python -m pip install -r tmp/locked-requirements.ci.txt
""".strip()
                + "\n",
                encoding="utf-8",
            )

            report = build_report(vault, context=fixed_context())

            self.assertEqual(report["status"], "fail")
            self.assertFalse(report["ci_install_proof"]["checks_uv_lock_freshness"])
            self.assertEqual(report["ci_install_proof"]["lock_check_commands"], [])
            self.assertEqual(report["lock_evidence"]["lock_check_status"], "missing_ci_check")
            self.assertEqual(
                report["lock_evidence"]["canonical_lock_policy_status"],
                "missing_ci_check",
            )
            self.assertEqual(report["lock_evidence"]["canonical_lock_check_command"], "")

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
            self.assertEqual(report["lock_evidence"]["lock_check_status"], "missing_ci_check")
            self.assertEqual(report["lock_evidence"]["canonical_lock_check_command"], "")
            self.assertEqual(
                report["lock_evidence"]["baseline_environment_lock_check_status"],
                "not_evaluated",
            )
            self.assertEqual(
                report["lock_evidence"]["canonical_lock_policy_status"],
                "missing_ci_check",
            )
            self.assertEqual(
                report["lock_evidence"]["toolchain_alignment_status"],
                "canonical_policy_not_enforced",
            )
            self.assertEqual(
                report["lock_evidence"]["recommended_normalization_step"],
                "make uv-lock-check",
            )
            self.assertEqual(report["locked_packages"], [])


if __name__ == "__main__":
    unittest.main()
