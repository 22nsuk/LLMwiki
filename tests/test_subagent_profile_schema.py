from __future__ import annotations

import datetime as dt
import tempfile
import tomllib
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.policy_runtime import load_policy, subagent_ladder_model_effort
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.core.subagent_profile_schema import build_report

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
AUDITOR_PROFILE_PATH = REPO_ROOT / ".codex" / "agents" / "external-report-action-auditor.toml"
AUDITOR_SKILL_PATH = REPO_ROOT / ".agents" / "skills" / "external-report-reconciliation" / "SKILL.md"
AGENT_README_PATH = REPO_ROOT / ".codex" / "agents" / "README.md"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 25, 12, 0, tzinfo=dt.UTC),
    )


def write_policy_matching_profiles(vault: Path) -> None:
    policy, _ = load_policy(REPO_ROOT, None)
    agents_dir = vault / ".codex" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for role, role_policy in policy["subagent_routing_policy"]["roles"].items():
        model, reasoning_effort = subagent_ladder_model_effort(
            policy,
            int(role_policy["default_rung"]),
        )
        (agents_dir / f"{role}.toml").write_text(
            "\n".join(
                [
                    f'name = "{role}"',
                    f'description = "Test fixture profile for {role}."',
                    f'model = "{model}"',
                    f'model_reasoning_effort = "{reasoning_effort}"',
                    f'sandbox_mode = "{role_policy["sandbox_mode"]}"',
                    'developer_instructions = """Stay within the assigned role and bounded scope."""',
                    "",
                ]
            ),
            encoding="utf-8",
        )


def replace_profile_line(path: Path, prefix: str, replacement: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise AssertionError(f"missing profile line with prefix {prefix!r}")


class SubagentProfileSchemaTests(unittest.TestCase):
    def test_external_report_auditor_is_a_thin_read_only_skill_wrapper(self) -> None:
        profile = tomllib.loads(AUDITOR_PROFILE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            set(profile),
            {
                "name",
                "description",
                "model",
                "model_reasoning_effort",
                "sandbox_mode",
                "developer_instructions",
            },
        )
        self.assertEqual(profile["model"], "gpt-5.6-sol")
        self.assertEqual(profile["model_reasoning_effort"], "high")
        self.assertEqual(profile["sandbox_mode"], "read-only")

        instructions = profile["developer_instructions"]
        self.assertIn(".agents/skills/external-report-reconciliation/SKILL.md", instructions)
        self.assertIn("Return:", instructions)
        self.assertLessEqual(len([line for line in instructions.splitlines() if line.strip()]), 10)
        for output_term in (
            "audited report/action scope",
            "status, lifecycle, evidence condition, and archive implication",
            "missing or stale evidence",
            "minimal next action and residual risk",
        ):
            self.assertIn(output_term, instructions)
        for duplicated_workflow_term in (
            "active_report_count",
            "external-report-reference-manifest-settle",
            "ops/reports/",
            "action current_status:",
        ):
            self.assertNotIn(duplicated_workflow_term, instructions)

        self.assertTrue(AUDITOR_SKILL_PATH.is_file())
        self.assertIn(
            "../../.agents/skills/external-report-reconciliation/SKILL.md",
            AGENT_README_PATH.read_text(encoding="utf-8"),
        )

    def test_profiles_match_policy_roles_and_schema(self) -> None:
        report = build_report(REPO_ROOT, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["missing_profile_count"], 0)
        self.assertEqual(report["summary"]["extra_profile_count"], 0)
        self.assertEqual(report["summary"]["incomplete_profile_count"], 0)
        self.assertEqual(report["summary"]["path_name_mismatch_count"], 0)
        self.assertEqual(report["summary"]["duplicate_profile_name_count"], 0)
        self.assertEqual(report["summary"]["default_mismatch_count"], 0)
        self.assertEqual(report["summary"]["sandbox_mismatch_count"], 0)
        self.assertEqual(report["path_name_mismatch_profiles"], [])
        self.assertEqual(report["duplicate_profile_names"], [])
        self.assertEqual(report["default_mismatch_profiles"], [])
        self.assertEqual(report["sandbox_mismatch_profiles"], [])
        for profile in report["profiles"]:
            self.assertTrue(profile["path_name_matches_role"], msg=profile["path"])
            self.assertTrue(profile["default_model_matches_policy"], msg=profile["path"])
            self.assertTrue(profile["default_reasoning_effort_matches_policy"], msg=profile["path"])
            self.assertTrue(profile["sandbox_mode_matches_policy"], msg=profile["path"])
        self.assertEqual(
            validate_with_schema(report, load_schema("ops/schemas/subagent-profile.schema.json")),
            [],
        )

    def test_profile_schema_fails_on_fallback_default_or_sandbox_drift(self) -> None:
        scenarios = [
            (
                "model",
                'model = "gpt-5.4"',
                "default_mismatch_profiles",
                "default_mismatch_count",
            ),
            (
                "model_reasoning_effort",
                'model_reasoning_effort = "medium"',
                "default_mismatch_profiles",
                "default_mismatch_count",
            ),
            (
                "sandbox_mode",
                'sandbox_mode = "read-only"',
                "sandbox_mismatch_profiles",
                "sandbox_mismatch_count",
            ),
        ]
        for line_prefix, replacement, mismatch_key, count_key in scenarios:
            with self.subTest(line_prefix=line_prefix), tempfile.TemporaryDirectory() as temp_dir:
                vault = Path(temp_dir) / "vault"
                vault.mkdir()
                write_policy_matching_profiles(vault)
                replace_profile_line(
                    vault / ".codex" / "agents" / "worker.toml",
                    f"{line_prefix} = ",
                    replacement,
                )

                report = build_report(
                    vault,
                    policy_path=str(POLICY_PATH),
                    context=fixed_context(),
                )

                self.assertEqual(report["status"], "fail")
                self.assertEqual(report["summary"][count_key], 1)
                self.assertIn(mismatch_key, report)
                self.assertEqual(report[mismatch_key], [".codex/agents/worker.toml"])
                self.assertEqual(
                    validate_with_schema(
                        report,
                        load_schema("ops/schemas/subagent-profile.schema.json"),
                    ),
                    [],
                )

    def test_profile_schema_fails_on_profile_name_path_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            write_policy_matching_profiles(vault)
            replace_profile_line(
                vault / ".codex" / "agents" / "reviewer.toml",
                "name = ",
                'name = "worker"',
            )

            report = build_report(
                vault,
                policy_path=str(POLICY_PATH),
                context=fixed_context(),
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["path_name_mismatch_count"], 1)
            self.assertEqual(report["summary"]["duplicate_profile_name_count"], 1)
            self.assertEqual(report["path_name_mismatch_profiles"], [".codex/agents/reviewer.toml"])
            self.assertEqual(report["duplicate_profile_names"], ["worker"])
            self.assertEqual(
                validate_with_schema(
                    report,
                    load_schema("ops/schemas/subagent-profile.schema.json"),
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
