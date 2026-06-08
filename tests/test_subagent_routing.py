from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.artifact_freshness_payload_runtime import (
    ENVELOPE_REQUIRED_FIELDS,
    has_artifact_envelope,
)
from ops.scripts.schema_runtime import load_schema, validate_or_raise

from ops.scripts.core.select_subagent_rung import main as select_subagent_rung_main
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault, seed_subagent_profiles


class SubagentRoutingTest(unittest.TestCase):
    def assert_manual_dispatch_matches_routing(self, report: dict) -> None:
        routing_decision = report["routing_decision"]
        manual_dispatch = report["manual_dispatch"]
        launch_parameters = manual_dispatch["launch_parameters"]
        fixed_reasoning_surface = manual_dispatch["fixed_reasoning_surface"]

        self.assertEqual(report["source_command"], "python -m ops.scripts.core.select_subagent_rung")
        self.assertEqual(manual_dispatch["source"], "subagent_routing_selector")
        self.assertEqual(manual_dispatch["role"], report["role"])
        self.assertEqual(manual_dispatch["selected_rung"], routing_decision["selected_rung"])
        self.assertEqual(launch_parameters["profile_path"], report["profile_path"])
        self.assertEqual(launch_parameters["model"], routing_decision["model"])
        self.assertEqual(
            launch_parameters["model_reasoning_effort"],
            routing_decision["reasoning_effort"],
        )
        self.assertEqual(launch_parameters["sandbox_mode"], routing_decision["sandbox_mode"])
        self.assertEqual(
            fixed_reasoning_surface["compatibility_rule"],
            "exact_model_and_reasoning_effort_match_required",
        )
        self.assertEqual(fixed_reasoning_surface["required_model"], routing_decision["model"])
        self.assertEqual(
            fixed_reasoning_surface["required_model_reasoning_effort"],
            routing_decision["reasoning_effort"],
        )
        self.assertEqual(
            fixed_reasoning_surface["required_selected_rung"],
            routing_decision["selected_rung"],
        )
        self.assertEqual(
            fixed_reasoning_surface["allowed_when"],
            "fixed_values_match_required_model_and_reasoning_effort",
        )
        self.assertEqual(
            fixed_reasoning_surface["mismatch_action"],
            "use_controllable_launch_parameters",
        )
        self.assertEqual(
            fixed_reasoning_surface["controllable_launch_surface"],
            manual_dispatch["dispatch_surfaces"]["ladder_compliant_surface"],
        )

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
        self.assert_manual_dispatch_matches_routing(report)
        return report

    def test_explorer_defaults_to_lowest_rung_for_empty_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["explorer"])

            report = self.run_selector(vault, "--role", "explorer")

            self.assertTrue(has_artifact_envelope(report))
            self.assertTrue(all(field in report for field in ENVELOPE_REQUIRED_FIELDS))
            self.assertEqual(report["artifact_kind"], "subagent_routing_report")
            self.assertEqual(report["artifact_status"], "current")
            self.assertEqual(report["retention_policy"], "canonical_report")
            self.assertEqual(report["currentness"]["status"], "current")
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
            self.assertEqual(report["manual_dispatch"]["contract"], "manual_subagent_dispatch_v1")
            self.assertEqual(report["manual_dispatch"]["selected_rung"], 1)
            self.assertEqual(report["manual_dispatch"]["toml_fallback_role"], "instruction_surface_only")
            self.assertEqual(
                report["manual_dispatch"]["launch_parameters"],
                {
                    "profile_path": ".codex/agents/worker.toml",
                    "model": "gpt-5.5",
                    "model_reasoning_effort": "medium",
                    "sandbox_mode": "workspace-write",
                },
            )
            self.assertEqual(
                report["manual_dispatch"]["dispatch_surfaces"]["ladder_compliant_surface"],
                "controllable_launch_parameters",
            )
            self.assertEqual(
                report["manual_dispatch"]["fixed_reasoning_surface"],
                {
                    "compatibility_rule": "exact_model_and_reasoning_effort_match_required",
                    "required_model": "gpt-5.5",
                    "required_model_reasoning_effort": "medium",
                    "required_selected_rung": 1,
                    "allowed_when": "fixed_values_match_required_model_and_reasoning_effort",
                    "mismatch_action": "use_controllable_launch_parameters",
                    "controllable_launch_surface": "controllable_launch_parameters",
                },
            )
            self.assertIn(
                "codex_exec",
                report["manual_dispatch"]["dispatch_surfaces"]["controllable_launch"],
            )
            self.assertIn(
                "fixed-reasoning",
                report["manual_dispatch"]["dispatch_surfaces"]["platform_named_role"],
            )
            self.assertIn("platform named roles may ignore", report["manual_dispatch"]["operator_action"])
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
            self.assertEqual(report["routing_decision"]["sandbox_mode"], "workspace-write")
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
            self.assertEqual(report["routing_decision"]["sandbox_mode"], "workspace-write")
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
            self.assertEqual(report["manual_dispatch"]["selected_rung"], 2)
            self.assertEqual(report["manual_dispatch"]["launch_parameters"]["model_reasoning_effort"], "high")
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

    def test_scope_gate_reviewer_defaults_to_read_only_high_rung(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["scope-gate-reviewer"])

            report = self.run_selector(vault, "--role", "scope-gate-reviewer")

            self.assertEqual(report["routing_decision"]["allowed_rungs"], [2, 3])
            self.assertEqual(report["routing_decision"]["selected_rung"], 2)
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "high")
            self.assertEqual(report["routing_decision"]["sandbox_mode"], "read-only")

    def test_release_authority_auditor_stays_on_fixed_xhigh_rung(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["release-authority-auditor"])

            report = self.run_selector(vault, "--role", "release-authority-auditor")

            self.assertEqual(report["routing_decision"]["allowed_rungs"], [3])
            self.assertEqual(report["routing_decision"]["selected_rung"], 3)
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "xhigh")
            self.assertEqual(report["routing_decision"]["sandbox_mode"], "read-only")

    def test_goal_runtime_triage_auditor_stays_on_fixed_xhigh_rung(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["goal-runtime-triage-auditor"])

            report = self.run_selector(vault, "--role", "goal-runtime-triage-auditor")

            self.assertEqual(report["routing_decision"]["allowed_rungs"], [3])
            self.assertEqual(report["routing_decision"]["selected_rung"], 3)
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "xhigh")
            self.assertEqual(report["routing_decision"]["sandbox_mode"], "read-only")

    def test_external_report_action_auditor_defaults_to_read_only_high_rung(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["external-report-action-auditor"])

            report = self.run_selector(vault, "--role", "external-report-action-auditor")

            self.assertEqual(report["routing_decision"]["allowed_rungs"], [2, 3])
            self.assertEqual(report["routing_decision"]["selected_rung"], 2)
            self.assertEqual(report["routing_decision"]["reasoning_effort"], "high")
            self.assertEqual(report["routing_decision"]["sandbox_mode"], "read-only")


if __name__ == "__main__":
    unittest.main()
