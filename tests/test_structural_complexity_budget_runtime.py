from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.eval.structural_complexity_budget_runtime import (
    DEFAULT_TARGET_PROFILES,
    build_report,
    target_paths_from_changed_files_manifest,
    touched_target_profiles,
)
from tests.runtime_test_context import frozen_context
from tests.test_mechanism_assess import seed_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT / "ops" / "schemas" / "structural-complexity-budget-report.schema.json"
)
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"


class StructuralComplexityBudgetRuntimeTests(unittest.TestCase):
    def test_build_report_uses_bundled_schema_when_vault_schema_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            (vault / "ops" / "schemas" / "structural-complexity-budget-report.schema.json").unlink()

            target = vault / "ops" / "scripts" / "sample_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("def sample_runtime():\n    return 1\n", encoding="utf-8")

            report = build_report(
                vault,
                context=frozen_context(),
                target_profiles={
                    "runtime_preview": {
                        "targets": ["ops/scripts/sample_runtime.py"],
                        "budgets": {
                            "nonempty_line_count_total": 10,
                            "python_function_count": 3,
                            "python_branch_node_count": 3,
                        },
                        "notes": ["Bundled schema fallback fixture"],
                    }
                },
                function_budget_config={
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                report["$schema"],
                "ops/schemas/structural-complexity-budget-report.schema.json",
            )
            self.assertEqual(validate_with_schema(report, load_schema(ENVELOPE_SCHEMA_PATH)), [])

    def test_build_report_prefers_vault_schema_override_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            (vault / "ops" / "schemas" / "structural-complexity-budget-report.schema.json").write_text(
                json.dumps({"type": "object", "required": ["override_marker"]}),
                encoding="utf-8",
            )

            target = vault / "ops" / "scripts" / "sample_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("def sample_runtime():\n    return 1\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "structural complexity budget report schema validation failed",
            ):
                build_report(
                    vault,
                    context=frozen_context(),
                    target_profiles={
                        "runtime_preview": {
                            "targets": ["ops/scripts/sample_runtime.py"],
                            "budgets": {
                                "nonempty_line_count_total": 10,
                                "python_function_count": 3,
                                "python_branch_node_count": 3,
                            },
                            "notes": ["Vault schema override fixture"],
                        }
                    },
                    function_budget_config={
                        "profiles": {
                            "runtime": {
                                "include_prefixes": ["ops/"],
                                "lines": 100,
                                "params": 100,
                                "branches": 100,
                            },
                            "tests": {
                                "include_prefixes": ["tests/"],
                                "lines": 100,
                                "params": 100,
                                "branches": 100,
                            },
                        }
                    },
                )

    def test_build_report_does_not_fallback_when_vault_schema_override_is_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            (vault / "ops" / "schemas" / "structural-complexity-budget-report.schema.json").write_text(
                "{not-json",
                encoding="utf-8",
            )

            target = vault / "ops" / "scripts" / "sample_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("def sample_runtime():\n    return 1\n", encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                build_report(
                    vault,
                    context=frozen_context(),
                    target_profiles={
                        "runtime_preview": {
                            "targets": ["ops/scripts/sample_runtime.py"],
                            "budgets": {
                                "nonempty_line_count_total": 10,
                                "python_function_count": 3,
                                "python_branch_node_count": 3,
                            },
                            "notes": ["Invalid vault schema override fixture"],
                        }
                    },
                    function_budget_config={
                        "profiles": {
                            "runtime": {
                                "include_prefixes": ["ops/"],
                                "lines": 100,
                                "params": 100,
                                "branches": 100,
                            },
                            "tests": {
                                "include_prefixes": ["tests/"],
                                "lines": 100,
                                "params": 100,
                                "branches": 100,
                            },
                        }
                    },
                )

    def test_build_report_marks_attention_for_over_budget_targets_and_function_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            target = vault / "ops" / "scripts" / "sample_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "def oversized_runtime(first, second, third):\n"
                "    if first:\n"
                "        if second:\n"
                "            return third\n"
                "    return first\n",
                encoding="utf-8",
            )

            report = build_report(
                vault,
                context=frozen_context(),
                target_profiles={
                    "runtime_preview": {
                        "targets": ["ops/scripts/sample_runtime.py"],
                        "budgets": {
                            "nonempty_line_count_total": 4,
                            "python_function_count": 1,
                            "python_branch_node_count": 1,
                        },
                        "notes": ["Preview test profile"],
                    }
                },
                function_budget_config={
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 3,
                            "params": 2,
                            "branches": 1,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["targets_with_attention_count"], 1)
            self.assertEqual(report["summary"]["targets_with_failure_count"], 0)
            self.assertEqual(report["summary"]["function_budget_candidate_count"], 1)
            self.assertEqual(report["targets"][0]["status"], "warn")
            self.assertEqual(
                report["targets"][0]["over_budget_metrics"],
                ["nonempty_line_count_total", "python_branch_node_count"],
            )
            self.assertEqual(report["targets"][0]["no_headroom_metrics"], ["python_function_count"])
            self.assertEqual(report["targets"][0]["low_headroom_metrics"], [])
            self.assertEqual(report["targets"][0]["function_budget_candidate_count"], 1)
            self.assertEqual(report["function_budget_candidates"][0]["page"], "ops/scripts/sample_runtime.py")
            self.assertEqual(
                report["diagnostics"]["function_budget_top_n"],
                {
                    "top_n": 10,
                    "total_candidate_count": 1,
                    "monitored_candidate_count": 1,
                    "unmonitored_candidate_count": 0,
                    "candidates": [
                        {
                            **report["function_budget_candidates"][0],
                            "monitored": True,
                        }
                    ],
                },
            )

            schema = load_schema(SCHEMA_PATH)
            self.assertEqual(validate_with_schema(report, schema), [])

    def test_build_report_marks_budget_edge_headroom_as_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            exact = vault / "ops" / "scripts" / "exact_runtime.py"
            low = vault / "ops" / "scripts" / "low_runtime.py"
            exact.parent.mkdir(parents=True, exist_ok=True)
            exact.write_text("def exact_runtime():\n    return 1\n", encoding="utf-8")
            low.write_text(
                "\n".join(f"value_{index} = {index}" for index in range(19)) + "\n",
                encoding="utf-8",
            )

            report = build_report(
                vault,
                context=frozen_context(),
                target_profiles={
                    "runtime_preview": {
                        "targets": [
                            "ops/scripts/exact_runtime.py",
                            "ops/scripts/low_runtime.py",
                        ],
                        "budgets": {
                            "nonempty_line_count_total": 20,
                            "python_function_count": 10,
                            "python_branch_node_count": 10,
                        },
                        "notes": ["Preview test profile"],
                    }
                },
                function_budget_config={
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            targets = {target["path"]: target for target in report["targets"]}
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["targets_with_attention_count"], 1)
            self.assertEqual(targets["ops/scripts/exact_runtime.py"]["status"], "pass")
            self.assertEqual(targets["ops/scripts/low_runtime.py"]["status"], "warn")
            self.assertEqual(targets["ops/scripts/low_runtime.py"]["over_budget_metrics"], [])
            self.assertEqual(targets["ops/scripts/low_runtime.py"]["no_headroom_metrics"], [])
            self.assertEqual(
                targets["ops/scripts/low_runtime.py"]["low_headroom_metrics"],
                ["nonempty_line_count_total"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_build_report_marks_exact_budget_headroom_as_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            target = vault / "ops" / "scripts" / "exact_runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("def exact_runtime():\n    return 1\n", encoding="utf-8")

            report = build_report(
                vault,
                context=frozen_context(),
                target_profiles={
                    "runtime_preview": {
                        "targets": ["ops/scripts/exact_runtime.py"],
                        "budgets": {
                            "nonempty_line_count_total": 2,
                            "python_function_count": 1,
                            "python_branch_node_count": 10,
                        },
                        "notes": ["Preview test profile"],
                    }
                },
                function_budget_config={
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            target_report = report["targets"][0]
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["targets_with_attention_count"], 1)
            self.assertEqual(target_report["status"], "warn")
            self.assertEqual(target_report["over_budget_metrics"], [])
            self.assertEqual(
                target_report["no_headroom_metrics"],
                ["nonempty_line_count_total", "python_function_count"],
            )
            self.assertEqual(target_report["low_headroom_metrics"], [])
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_default_profiles_include_high_complexity_helper_preview(self) -> None:
        profile = DEFAULT_TARGET_PROFILES["high_complexity_helpers"]

        self.assertIn("ops/scripts/eval/wiki_eval.py", profile["targets"])
        self.assertIn("ops/scripts/eval/structural_complexity_budget_runtime.py", profile["targets"])
        self.assertEqual(
            profile["notes"][-1],
            "Function-level hot spots are summarized separately in diagnostics.function_budget_top_n.",
        )

    def test_default_profiles_include_planned_report_builder_decomposition_targets(self) -> None:
        release_profile = DEFAULT_TARGET_PROFILES["release_report_builders"]
        learning_profile = DEFAULT_TARGET_PROFILES["learning_claim_report_builders"]

        self.assertEqual(
            release_profile["targets"],
            [
                "ops/scripts/release/release_closeout_batch_manifest.py",
                "ops/scripts/release/release_evidence_dashboard.py",
                "ops/scripts/release/release_closeout_summary.py",
                "ops/scripts/release/external_report_lifecycle_runtime.py",
                "ops/scripts/release/release_closeout_fixed_point.py",
                "ops/scripts/release/release_post_seal_attestation.py",
                "ops/scripts/test/test_execution_summary.py",
            ],
        )
        self.assertIn(
            "load-normalize-classify-decide-render-seal",
            release_profile["notes"][0],
        )
        self.assertIn(
            "ops/scripts/learning/learning_delta_scoreboard.py",
            learning_profile["targets"],
        )
        self.assertIn(
            "ops/scripts/learning/learning_claim_model.py",
            learning_profile["targets"],
        )
        self.assertIn(
            "production learning decisions separated",
            learning_profile["notes"][1],
        )

    def test_default_profile_targets_exist_in_current_layout(self) -> None:
        missing = [
            target
            for profile in DEFAULT_TARGET_PROFILES.values()
            for target in profile["targets"]
            if not (REPO_ROOT / target).is_file()
        ]

        self.assertEqual(missing, [])

    def test_function_budget_top_n_includes_unmonitored_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            monitored = vault / "ops" / "scripts" / "monitored_runtime.py"
            unmonitored = vault / "ops" / "scripts" / "unmonitored_runtime.py"
            monitored.parent.mkdir(parents=True, exist_ok=True)
            monitored.write_text(
                "def monitored_runtime(first, second, third):\n"
                "    if first:\n"
                "        if second:\n"
                "            return third\n"
                "    return first\n",
                encoding="utf-8",
            )
            unmonitored.write_text(
                "def unmonitored_runtime(first, second, third, fourth):\n"
                "    if first:\n"
                "        if second:\n"
                "            if third:\n"
                "                return fourth\n"
                "    return first\n",
                encoding="utf-8",
            )

            report = build_report(
                vault,
                context=frozen_context(),
                target_profiles={
                    "runtime_preview": {
                        "targets": ["ops/scripts/monitored_runtime.py"],
                        "budgets": {
                            "nonempty_line_count_total": 100,
                            "python_function_count": 10,
                            "python_branch_node_count": 10,
                        },
                        "notes": ["Preview test profile"],
                    }
                },
                function_budget_config={
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 3,
                            "params": 2,
                            "branches": 1,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            top_n = report["diagnostics"]["function_budget_top_n"]
            monitoring = report["diagnostics"]["function_budget_monitoring"]
            self.assertEqual(top_n["total_candidate_count"], 2)
            self.assertEqual(top_n["monitored_candidate_count"], 1)
            self.assertEqual(top_n["unmonitored_candidate_count"], 1)
            self.assertEqual(
                monitoring,
                {
                    "status": "attention",
                    "gate_effect": "preview",
                    "total_candidate_count": 2,
                    "monitored_candidate_count": 1,
                    "unmonitored_candidate_count": 1,
                    "monitored_target_count": 1,
                    "summary": (
                        "1 function budget candidate(s) are outside monitored structural profiles; "
                        "review diagnostics.function_budget_top_n before promoting complexity gates."
                    ),
                },
            )
            self.assertEqual(
                [(candidate["page"], candidate["monitored"]) for candidate in top_n["candidates"]],
                [
                    ("ops/scripts/unmonitored_runtime.py", False),
                    ("ops/scripts/monitored_runtime.py", True),
                ],
            )
            self.assertEqual(
                [candidate["page"] for candidate in report["function_budget_candidates"]],
                ["ops/scripts/monitored_runtime.py"],
            )

    def test_build_report_marks_missing_targets_as_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)

            report = build_report(
                vault,
                context=frozen_context(),
                target_profiles={
                    "runtime_preview": {
                        "targets": ["ops/scripts/missing_runtime.py"],
                        "budgets": {
                            "nonempty_line_count_total": 1,
                            "python_function_count": 1,
                            "python_branch_node_count": 1,
                        },
                        "notes": ["Missing target preview"],
                    }
                },
                function_budget_config={
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["targets_with_failure_count"], 1)
            self.assertEqual(report["targets"][0]["status"], "fail")
            self.assertEqual(report["diagnostics"]["unreadable_targets"], [{"path": "ops/scripts/missing_runtime.py", "reason": "missing_target"}])

    def test_touched_target_profiles_filter_default_targets_and_keep_fallbacks(self) -> None:
        profiles = touched_target_profiles(
            DEFAULT_TARGET_PROFILES,
            [
                "ops/scripts/mechanism/auto_improve_runtime.py",
                "./ops/scripts/custom_runtime.py",
                "ops/scripts/custom_runtime.py",
            ],
        )

        self.assertEqual(
            profiles["critical_runtime_orchestrators"]["targets"],
            ["ops/scripts/mechanism/auto_improve_runtime.py"],
        )
        self.assertEqual(profiles["touched_targets"]["targets"], ["ops/scripts/custom_runtime.py"])

    def test_touched_target_profiles_use_test_support_budget_for_python_tests(self) -> None:
        profiles = touched_target_profiles(
            DEFAULT_TARGET_PROFILES,
            [
                "ops/scripts/custom_runtime.py",
                "tests/test_custom_runtime.py",
            ],
        )

        self.assertEqual(profiles["touched_targets"]["targets"], ["ops/scripts/custom_runtime.py"])
        self.assertEqual(profiles["touched_test_targets"]["targets"], ["tests/test_custom_runtime.py"])
        self.assertEqual(
            profiles["touched_targets"]["budgets"],
            DEFAULT_TARGET_PROFILES["critical_runtime_orchestrators"]["budgets"],
        )
        self.assertEqual(
            profiles["touched_test_targets"]["budgets"],
            {
                "nonempty_line_count_total": 2400,
                "python_function_count": 60,
                "python_branch_node_count": 130,
            },
        )

    def test_changed_files_manifest_paths_can_drive_empty_touched_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            manifest = vault / "changed-files-manifest.json"
            manifest.write_text(
                '{"files": [{"path": "ops/scripts/sample_runtime.py"}, {"path": ""}]}',
                encoding="utf-8",
            )

            paths = target_paths_from_changed_files_manifest(vault, "changed-files-manifest.json")
            report = build_report(
                vault,
                context=frozen_context(),
                target_profiles=touched_target_profiles(DEFAULT_TARGET_PROFILES, paths),
                function_budget_config={
                    "profiles": {
                        "runtime": {
                            "include_prefixes": ["ops/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                        "tests": {
                            "include_prefixes": ["tests/"],
                            "lines": 100,
                            "params": 100,
                            "branches": 100,
                        },
                    }
                },
            )

            self.assertEqual(paths, ["ops/scripts/sample_runtime.py"])
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["targets"][0]["path"], "ops/scripts/sample_runtime.py")


if __name__ == "__main__":
    unittest.main()
