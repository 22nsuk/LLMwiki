from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.schema_runtime import load_schema, validate_or_raise
from ops.scripts.select_subagent_rung import main as select_subagent_rung_main
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault, seed_subagent_profiles


class SubagentRoutingTest(unittest.TestCase):
    def run_selector(self, vault: Path, *args: str) -> dict:
        result = invoke_cli_main(
            select_subagent_rung_main,
            ["--vault", str(vault), *args],
            cwd=vault,
        )
        self.assertEqual(result.exit_code, 0, msg=result.stderr or result.stdout)
        report_path = vault / "ops" / "reports" / "subagent-routing-report.json"
        self.assertTrue(report_path.exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        schema = load_schema(vault / "ops" / "schemas" / "subagent-routing-report.schema.json")
        validate_or_raise(report, schema, context="subagent routing test schema validation failed")
        return report

    def test_explorer_defaults_to_lowest_rung_for_empty_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["explorer"])

            report = self.run_selector(vault, "--role", "explorer")

            self.assertEqual(report["inputs"]["primary_targets"], [])
            self.assertEqual(report["complexity_profile"]["complexity_score"], 0)
            self.assertEqual(report["routing_decision"]["score_band"], "low")
            self.assertEqual(report["routing_decision"]["selected_rung"], 1)
            self.assertEqual(report["routing_decision"]["model"], "gpt-5.5")
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "medium")
            self.assertEqual(
                report["routing_decision"]["effort_sufficiency"]["status"],
                "sufficient_for_complexity",
            )
            self.assertTrue(report["routing_decision"]["deescalation_reasons"])

    def test_worker_can_use_rung_one_for_docs_only_low_risk_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["worker"])
            doc_path = vault / "wiki" / "small-note.md"
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            doc_path.write_text("# Small note\n\nBounded docs-only edit surface.\n", encoding="utf-8")

            report = self.run_selector(
                vault,
                "--role",
                "worker",
                "--primary-target",
                "wiki/small-note.md",
            )

            self.assertEqual(report["routing_decision"]["score_band"], "low")
            self.assertEqual(report["routing_decision"]["allowed_rungs"], [1, 2, 3])
            self.assertEqual(report["routing_decision"]["selected_rung"], 1)
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "medium")
            self.assertEqual(
                report["routing_decision"]["effort_sufficiency"]["status"],
                "sufficient_for_complexity",
            )
            self.assertTrue(
                any(
                    reason["type"] == "higher_rung_not_required"
                    for reason in report["routing_decision"]["deescalation_reasons"]
                )
            )

    def test_worker_escalates_to_rung_three_for_policy_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["worker"])

            report = self.run_selector(
                vault,
                "--role",
                "worker",
                "--primary-target",
                "ops/policies/wiki-maintainer-policy.yaml",
            )

            self.assertIn(report["routing_decision"]["score_band"], {"high", "extreme"})
            self.assertEqual(report["routing_decision"]["selected_rung"], 3)
            self.assertEqual(report["routing_decision"]["model"], "gpt-5.5")
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "xhigh")
            self.assertEqual(
                report["routing_decision"]["effort_sufficiency"]["status"],
                "escalated_for_complexity",
            )
            self.assertGreaterEqual(report["complexity_profile"]["dimensions"]["dependency_impact"], 4)

    def test_reviewer_escalates_to_rung_three_for_policy_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["reviewer"])

            report = self.run_selector(
                vault,
                "--role",
                "reviewer",
                "--primary-target",
                "ops/policies/wiki-maintainer-policy.yaml",
            )

            self.assertEqual(report["routing_decision"]["selected_rung"], 3)
            self.assertEqual(report["routing_decision"]["model"], "gpt-5.5")
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "xhigh")
            self.assertTrue(
                any(reason["type"] == "score_band" for reason in report["routing_decision"]["escalation_reasons"])
            )

    def test_validator_stays_rung_two_for_low_risk_focused_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["validator"])
            doc_path = vault / "wiki" / "small-note.md"
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            doc_path.write_text("# Small note\n\nBounded docs-only validation surface.\n", encoding="utf-8")

            report = self.run_selector(
                vault,
                "--role",
                "validator",
                "--primary-target",
                "wiki/small-note.md",
            )

            self.assertEqual(report["routing_decision"]["allowed_rungs"], [2, 3])
            self.assertEqual(report["routing_decision"]["score_band"], "low")
            self.assertEqual(report["routing_decision"]["selected_rung"], 2)
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "high")
            self.assertEqual(
                report["routing_decision"]["effort_sufficiency"]["status"],
                "sufficient_for_complexity",
            )
            self.assertTrue(
                any(
                    reason["type"] == "higher_rung_not_required"
                    for reason in report["routing_decision"]["deescalation_reasons"]
                )
            )

    def test_validator_escalates_to_rung_three_for_schema_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["validator"])

            report = self.run_selector(
                vault,
                "--role",
                "validator",
                "--primary-target",
                "ops/schemas/subagent-routing-report.schema.json",
            )

            self.assertEqual(report["routing_decision"]["selected_rung"], 3)
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "xhigh")
            self.assertTrue(
                any(
                    reason["type"] == "pressure_override" and reason.get("dimension") == "dependency_impact"
                    for reason in report["routing_decision"]["escalation_reasons"]
                )
            )

    def test_manual_risk_flag_keeps_validator_on_rung_three(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["validator"])

            report = self.run_selector(
                vault,
                "--role",
                "validator",
                "--primary-target",
                "wiki/source--fake.md",
                "--manual-risk-flag",
                "migration",
            )

            self.assertEqual(report["complexity_profile"]["manual_risk_flags"], ["migration"])
            self.assertEqual(report["routing_decision"]["selected_rung"], 3)
            self.assertEqual(
                report["routing_decision"]["effort_sufficiency"]["status"],
                "escalated_for_complexity",
            )
            self.assertTrue(
                any(
                    reason["type"] == "pressure_override" and reason.get("dimension") == "environment_risk"
                    for reason in report["routing_decision"]["escalation_reasons"]
                )
            )

    def test_manual_requested_rung_cannot_escape_allowed_role_rungs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["explorer"])

            report = self.run_selector(vault, "--role", "explorer", "--requested-rung", "3")

            self.assertEqual(report["routing_decision"]["allowed_rungs"], [1, 2])
            self.assertEqual(report["routing_decision"]["requested_rung"], 3)
            self.assertEqual(report["routing_decision"]["selected_rung"], 2)
            self.assertTrue(
                any(
                    reason["type"] == "allowed_rung_clamp"
                    for reason in report["routing_decision"]["escalation_reasons"]
                )
            )

    def test_provenance_auditor_stays_on_fixed_xhigh_rung(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["provenance-auditor"])

            report = self.run_selector(vault, "--role", "provenance-auditor")

            self.assertEqual(report["routing_decision"]["allowed_rungs"], [3])
            self.assertEqual(report["routing_decision"]["requested_rung"], 3)
            self.assertEqual(report["routing_decision"]["selected_rung"], 3)
            self.assertEqual(report["routing_decision"]["sandbox_mode"], "read-only")
            self.assertEqual(
                report["routing_decision"]["effort_sufficiency"]["status"],
                "fixed_role_floor",
            )


if __name__ == "__main__":
    unittest.main()
