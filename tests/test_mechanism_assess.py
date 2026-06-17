from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.mechanism_assess import build_report, normalize_targets
from tests.minimal_vault_runtime import POLICY_PATH, SCHEMA_PATHS, set_policy_value

MECHANISM_SCHEMA_PATH = SCHEMA_PATHS["mechanism-assessment-report.schema.json"]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
    )


def seed_policy(vault: Path) -> None:
    (vault / "ops" / "policies").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "schemas" / "wiki-maintainer-policy.schema.json").write_text(
        SCHEMA_PATHS["wiki-maintainer-policy.schema.json"].read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "schemas" / "structural-complexity-budget-report.schema.json").write_text(
        SCHEMA_PATHS["structural-complexity-budget-report.schema.json"].read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )


class MechanismAssessTest(unittest.TestCase):
    def test_build_report_produces_deterministic_structural_metrics_and_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            module_path = vault / "ops" / "scripts" / "sample.py"
            notes_path = vault / "README.md"
            test_path = vault / "tests" / "test_sample.py"
            module_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.parent.mkdir(parents=True, exist_ok=True)

            module_path.write_text(
                "def alpha():\n"
                "    if True:\n"
                "        return 1\n"
                "    return 0\n"
                "\n"
                "async def beta():\n"
                "    with open('x', 'r') as handle:\n"
                "        return handle.read()\n",
                encoding="utf-8",
            )
            notes_path.write_text(
                "# Title\n"
                "\n"
                "## Overview\n"
                "text\n"
                "\n"
                "### Details\n"
                "more\n",
                encoding="utf-8",
            )
            test_path.write_text(
                "import unittest\n"
                "\n"
                "def test_standalone():\n"
                "    assert True\n"
                "\n"
                "class SampleTest(unittest.TestCase):\n"
                "    def test_case(self):\n"
                "        self.assertTrue(True)\n"
                "\n"
                "    def helper(self):\n"
                "        return None\n",
                encoding="utf-8",
            )

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["ops/scripts/sample.py", "README.md"]),
                normalize_targets(vault, ["README.md"]),
                normalize_targets(vault, ["tests/test_sample.py"]),
                context=fixed_context(),
            )

            schema = load_schema(MECHANISM_SCHEMA_PATH)
            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["vault"], ".")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(
                report["diagnostics"],
                {
                    "unreadable_targets": [],
                    "python_parse_failures": [],
                },
            )
            self.assertEqual(
                report["structural_metrics"],
                {
                    "nonempty_line_count_total": 12,
                    "python_function_count": 2,
                    "python_branch_node_count": 2,
                    "markdown_heading_count": 2,
                    "test_file_count": 1,
                    "test_case_count": 2,
                },
            )
            self.assertEqual(
                report["total_structural_metrics"],
                {
                    "nonempty_line_count_total": 12,
                    "python_function_count": 2,
                    "python_branch_node_count": 2,
                    "markdown_heading_count": 2,
                    "test_file_count": 1,
                    "test_case_count": 2,
                },
            )
            self.assertEqual(
                report["complexity_profile"]["dimensions"],
                {
                    "change_surface": 1,
                    "dependency_impact": 3,
                    "verification_cost": 2,
                    "artifact_heterogeneity": 1,
                    "environment_risk": 0,
                },
            )
            self.assertEqual(report["complexity_profile"]["complexity_score"], 27)

    def test_total_structural_metrics_include_supporting_targets_without_double_counting_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            primary_path = vault / "ops" / "scripts" / "sample.py"
            supporting_path = vault / "ops" / "scripts" / "helper_runtime.py"
            test_path = vault / "tests" / "test_sample.py"
            primary_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.parent.mkdir(parents=True, exist_ok=True)

            primary_path.write_text(
                "def alpha(flag):\n"
                "    if flag:\n"
                "        return 1\n"
                "    return 0\n",
                encoding="utf-8",
            )
            supporting_path.write_text(
                "def beta(value):\n"
                "    if value > 0:\n"
                "        return 1\n"
                "    if value == 0:\n"
                "        return 0\n"
                "    return -1\n",
                encoding="utf-8",
            )
            test_path.write_text(
                "def test_alpha():\n"
                "    assert True\n",
                encoding="utf-8",
            )

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["ops/scripts/sample.py"]),
                normalize_targets(
                    vault,
                    ["ops/scripts/helper_runtime.py", "ops/scripts/sample.py"],
                ),
                normalize_targets(vault, ["tests/test_sample.py"]),
            )

            self.assertEqual(
                report["structural_metrics"],
                {
                    "nonempty_line_count_total": 4,
                    "python_function_count": 1,
                    "python_branch_node_count": 1,
                    "markdown_heading_count": 0,
                    "test_file_count": 1,
                    "test_case_count": 1,
                },
            )
            self.assertEqual(
                report["total_structural_metrics"],
                {
                    "nonempty_line_count_total": 10,
                    "python_function_count": 2,
                    "python_branch_node_count": 3,
                    "markdown_heading_count": 0,
                    "test_file_count": 1,
                    "test_case_count": 1,
                },
            )

    def test_risk_flags_follow_path_and_content_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            targets = {
                "ops/schemas/example.schema.json": "{}\n",
                "pyproject.toml": "[project]\nname = 'sample'\n",
                "uv.lock": "version = 1\n",
                "migrations/001_init.py": "print('migration')\n",
                "system/security-check.md": "# Security\n",
                "ops/scripts/danger.py": "rm -rf /tmp/cache\n",
            }
            for rel_path, content in targets.items():
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["ops/scripts/danger.py"]),
                normalize_targets(
                    vault,
                    [
                        "ops/schemas/example.schema.json",
                        "pyproject.toml",
                        "uv.lock",
                        "migrations/001_init.py",
                        "system/security-check.md",
                    ],
                ),
                [],
            )

            self.assertEqual(
                report["complexity_profile"]["risk_flags"],
                [
                    "dependency_change",
                    "destructive_command",
                    "migration",
                    "schema_change",
                    "security_surface",
                ],
            )
            self.assertEqual(
                report["complexity_profile"]["dimensions"]["environment_risk"],
                5,
            )

    def test_build_report_records_unreadable_and_python_parse_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            unreadable_path = vault / "ops" / "scripts" / "binary.py"
            invalid_python_path = vault / "ops" / "scripts" / "broken.py"
            unreadable_path.parent.mkdir(parents=True, exist_ok=True)

            unreadable_path.write_bytes(b"\xff\xfe\x00\x01")
            invalid_python_path.write_text("def broken(:\n    pass\n", encoding="utf-8")

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["ops/scripts/binary.py", "ops/scripts/broken.py"]),
                [],
                [],
            )

            schema = load_schema(MECHANISM_SCHEMA_PATH)
            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(
                report["diagnostics"]["unreadable_targets"],
                [
                    {
                        "path": "ops/scripts/binary.py",
                        "reason": "unicode_decode_error",
                    }
                ],
            )
            self.assertEqual(
                report["diagnostics"]["python_parse_failures"],
                [
                    {
                        "path": "ops/scripts/broken.py",
                        "reason": "syntax_error",
                        "detail": "line 1: invalid syntax",
                    }
                ],
            )
            self.assertEqual(report["structural_metrics"]["python_function_count"], 0)

    def test_risk_flags_follow_policy_selected_high_risk_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            set_policy_value(
                vault,
                ("complexity_policy", "risk_overrides", "high_risk_flags"),
                ["schema_change", "destructive_command"],
            )

            targets = {
                "ops/schemas/example.schema.json": "{}\n",
                "pyproject.toml": "[project]\nname = 'sample'\n",
                "migrations/001_init.py": "print('migration')\n",
                "system/security-check.md": "# Security\n",
                "ops/scripts/danger.py": "rm -rf /tmp/cache\n",
            }
            for rel_path, content in targets.items():
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["ops/scripts/danger.py"]),
                normalize_targets(
                    vault,
                    [
                        "ops/schemas/example.schema.json",
                        "pyproject.toml",
                        "migrations/001_init.py",
                        "system/security-check.md",
                    ],
                ),
                [],
            )

            self.assertEqual(
                report["complexity_profile"]["risk_flags"],
                [
                    "destructive_command",
                    "schema_change",
                ],
            )
            self.assertEqual(
                report["complexity_profile"]["dimensions"]["environment_risk"],
                5,
            )

    def test_large_coarse_target_is_not_scored_as_max_change_surface_by_size_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            doc_path = vault / "wiki" / "large-note.md"
            doc_path.parent.mkdir(parents=True, exist_ok=True)
            doc_path.write_text("\n".join(f"line {index}" for index in range(800)), encoding="utf-8")

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["wiki/large-note.md"]),
                [],
                [],
            )

            evidence = report["complexity_profile"]["dimension_evidence"]["change_surface"]
            self.assertEqual(evidence["whole_file_volume_score"], 5)
            self.assertLess(evidence["selected_score"], evidence["whole_file_volume_score"])
            self.assertTrue(evidence["coarse_target_bias_mitigated"])
            self.assertEqual(report["complexity_profile"]["dimensions"]["change_surface"], evidence["selected_score"])

    def test_security_surface_can_be_detected_from_content_not_only_path_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            target = vault / "ops" / "scripts" / "client.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "import os\n"
                "API_KEY = os.environ['SERVICE_API_KEY']\n"
                "def build_headers():\n"
                "    return {'Authorization': f'Bearer {API_KEY}'}\n",
                encoding="utf-8",
            )

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["ops/scripts/client.py"]),
                [],
                [],
            )

            self.assertIn("security_surface", report["complexity_profile"]["risk_flags"])
            self.assertTrue(
                any(
                    entry["flag"] == "security_surface" and entry["reason"] == "security_content_token"
                    for entry in report["complexity_profile"]["risk_flag_evidence"]
                )
            )

    def test_verification_cost_uses_case_density_not_only_test_file_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            target = vault / "wiki" / "source.md"
            test_path = vault / "tests" / "test_dense.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            test_path.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Source\n", encoding="utf-8")
            test_path.write_text(
                "\n".join(f"def test_case_{index}():\n    assert True" for index in range(25)),
                encoding="utf-8",
            )

            policy, resolved_policy_path = load_policy(vault)
            report = build_report(
                vault,
                policy,
                resolved_policy_path,
                normalize_targets(vault, ["wiki/source.md"]),
                [],
                normalize_targets(vault, ["tests/test_dense.py"]),
            )

            evidence = report["complexity_profile"]["dimension_evidence"]["verification_cost"]
            self.assertEqual(evidence["test_file_count"], 1)
            self.assertEqual(evidence["test_case_count"], 25)
            self.assertEqual(evidence["verification_scope"], "broad_single_file")
            self.assertEqual(report["complexity_profile"]["dimensions"]["verification_cost"], 4)


if __name__ == "__main__":
    unittest.main()
