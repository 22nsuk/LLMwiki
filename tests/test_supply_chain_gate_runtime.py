from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.supply_chain_gate_runtime import build_gate_report

from tests.minimal_vault_runtime import seed_minimal_vault


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 12, 0, tzinfo=dt.UTC),
    )


class SupplyChainGateRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)

        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        (self.vault / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (self.vault / ".github" / "workflows" / "ci.yml").write_text(
            "uv lock --check\n"
            "uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt\n"
            "python -m pip install -r tmp/locked-requirements.ci.txt\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_provenance(self, payload: dict) -> None:
        (self.vault / "ops" / "reports" / "supply-chain-provenance.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_gate_passes_when_all_checks_are_satisfied(self) -> None:
        self._write_provenance(
            {
                "inputs": [{"path": "pyproject.toml", "exists": True, "parser_status": {"status": "pass"}}],
                "lock_evidence": {
                    "path": "uv.lock",
                    "parser_status": {"status": "pass"},
                    "lock_check_status": "enforced",
                    "lock_check_command": "uv lock --check",
                },
                "ci_install_proof": {
                    "workflow_path": ".github/workflows/ci.yml",
                    "workflow_exists": True,
                    "checks_uv_lock_freshness": True,
                    "exports_frozen_uv_lock": True,
                    "installs_locked_requirements": True,
                    "install_resolution_mode": "canonical_lock_export",
                    "editable_install": True,
                },
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "pass")

    def test_gate_fails_when_required_input_missing(self) -> None:
        self._write_provenance(
            {
                "inputs": [{"path": "requirements-dev.txt", "exists": False, "parser_status": {"status": "missing"}}],
                "lock_evidence": {
                    "parser_status": {"status": "pass"},
                    "lock_check_status": "enforced",
                    "lock_check_command": "uv lock --check",
                },
                "ci_install_proof": {
                    "workflow_path": ".github/workflows/ci.yml",
                    "workflow_exists": True,
                    "checks_uv_lock_freshness": True,
                    "exports_frozen_uv_lock": True,
                    "installs_locked_requirements": True,
                    "install_resolution_mode": "canonical_lock_export",
                    "editable_install": True,
                },
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "all_required_inputs_exist"))

    def test_gate_fails_when_parser_error_present(self) -> None:
        self._write_provenance(
            {
                "inputs": [],
                "lock_evidence": {
                    "path": "uv.lock",
                    "parser_status": {"status": "error"},
                    "lock_check_status": "enforced",
                    "lock_check_command": "uv lock --check",
                },
                "ci_install_proof": {
                    "workflow_path": ".github/workflows/ci.yml",
                    "workflow_exists": True,
                    "checks_uv_lock_freshness": True,
                    "exports_frozen_uv_lock": True,
                    "installs_locked_requirements": True,
                    "install_resolution_mode": "canonical_lock_export",
                    "editable_install": True,
                },
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "no_parser_errors"))

    def test_gate_fails_when_ci_drift_detected(self) -> None:
        (self.vault / ".github" / "workflows" / "ci.yml").write_text("python -m pip install other\n", encoding="utf-8")
        self._write_provenance(
            {
                "inputs": [],
                "lock_evidence": {
                    "path": "uv.lock",
                    "parser_status": {"status": "pass"},
                    "lock_check_status": "enforced",
                    "lock_check_command": "uv lock --check",
                },
                "ci_install_proof": {
                    "workflow_path": ".github/workflows/ci.yml",
                    "workflow_exists": True,
                    "checks_uv_lock_freshness": True,
                    "exports_frozen_uv_lock": True,
                    "installs_locked_requirements": True,
                    "install_resolution_mode": "canonical_lock_export",
                    "editable_install": True,
                },
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "ci_install_note_drift"))

    def test_gate_fails_when_ci_proof_omits_required_install(self) -> None:
        self._write_provenance(
            {
                "inputs": [],
                "lock_evidence": {
                    "path": "uv.lock",
                    "parser_status": {"status": "pass"},
                    "lock_check_status": "enforced",
                    "lock_check_command": "uv lock --check",
                },
                "ci_install_proof": {
                    "workflow_path": ".github/workflows/ci.yml",
                    "workflow_exists": True,
                    "checks_uv_lock_freshness": True,
                    "exports_frozen_uv_lock": False,
                    "installs_locked_requirements": True,
                    "install_resolution_mode": "unknown",
                    "editable_install": True,
                },
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "ci_install_note_drift"))

    def test_gate_fails_when_uv_lock_check_is_not_enforced(self) -> None:
        self._write_provenance(
            {
                "inputs": [],
                "lock_evidence": {
                    "path": "uv.lock",
                    "parser_status": {"status": "pass"},
                    "lock_check_status": "missing_ci_check",
                    "lock_check_command": "",
                },
                "ci_install_proof": {
                    "workflow_path": ".github/workflows/ci.yml",
                    "workflow_exists": True,
                    "checks_uv_lock_freshness": False,
                    "exports_frozen_uv_lock": True,
                    "installs_locked_requirements": True,
                    "install_resolution_mode": "canonical_lock_export",
                    "editable_install": True,
                },
            }
        )

        report = build_gate_report(self.vault, context=fixed_context())
        self.assertEqual(report["status"], "fail")
        self.assertFalse(next(c["pass"] for c in report["checks"] if c["rule"] == "uv_lock_freshness_enforced"))


if __name__ == "__main__":
    unittest.main()
