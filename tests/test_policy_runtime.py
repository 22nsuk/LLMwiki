from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.subagent_routing_runtime import score_band_name
from ops.scripts.core.yaml_runtime import parse_simple_yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
POLICY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-maintainer-policy.schema.json"


def _mutated_live_policy_text(mutator: Callable[[dict[str, Any]], None]) -> str:
    policy = parse_simple_yaml(LIVE_POLICY_PATH.read_text(encoding="utf-8"))
    mutator(policy)
    return yaml.safe_dump(policy, allow_unicode=True, sort_keys=False)


def _set_policy_path(policy: dict[str, Any], path: Sequence[str | int], value: Any) -> None:
    target: Any = policy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _append_policy_path(policy: dict[str, Any], path: Sequence[str | int], value: Any) -> None:
    target: Any = policy
    for key in path:
        target = target[key]
    target.append(value)


class PolicyRuntimeTest(unittest.TestCase):
    def _live_policy(self) -> dict:
        return load_policy(REPO_ROOT)[0]

    def test_live_policy_core_evaluation_and_routing_contracts(self) -> None:
        policy = self._live_policy()

        self.assertEqual(policy["mutation_policy"]["default_requires_eval_improvement"], True)
        self.assertEqual(
            policy["equal_score_promotion"]["allowed_artifact_classes"],
            ["system_mechanism"],
        )
        self.assertEqual(
            policy["stage2_eval"],
            {
                "source_count_consistency_enabled": True,
                "central_research_anchor_enabled": True,
                "broad_synthesis_boundary_enabled": True,
                "seed_source_absorption_enabled": True,
                "content_quality_scaffold_enabled": True,
            },
        )
        self.assertEqual(
            policy["eval_coverage_review"]["cohorts"][0]["cohort_id"],
            "stage1_source_substance_coverage",
        )
        self.assertEqual(
            policy["eval_coverage_review"]["cohorts"][3]["coverage_rules"],
            ["declared_source_count_matches_evidence"],
        )
        self.assertEqual(
            policy["complexity_policy"]["risk_overrides"]["high_risk_flags"],
            [
                "schema_change",
                "dependency_change",
                "migration",
                "security_surface",
                "destructive_command",
                "policy_surface",
                "log_append_surface",
            ],
        )
        self.assertEqual(
            policy["subagent_routing_policy"]["ladder"][0],
            {
                "rung": 1,
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
            },
        )
        self.assertEqual(
            policy["subagent_routing_policy"]["roles"]["worker"]["allowed_rungs"],
            [1, 2, 3],
        )
        self.assertEqual(
            policy["subagent_routing_policy"]["roles"]["reviewer"]["score_band_rungs"]["high"],
            3,
        )
        self.assertEqual(
            policy["subagent_routing_policy"]["roles"]["scope-gate-reviewer"]["sandbox_mode"],
            "read-only",
        )
        self.assertEqual(
            policy["subagent_routing_policy"]["roles"]["scope-gate-reviewer"]["allowed_rungs"],
            [2, 3],
        )
        self.assertEqual(
            policy["system_refactor_policy"]["python_function_review"]["profiles"]["runtime"],
            {
                "include_prefixes": ["ops/", "tools/"],
                "lines": 120,
                "params": 10,
                "branches": 18,
            },
        )
        self.assertEqual(
            policy["system_refactor_policy"]["python_function_review"]["profiles"]["tests"],
            {
                "include_prefixes": ["tests/"],
                "lines": 180,
                "params": 12,
                "branches": 12,
            },
        )

    def test_live_policy_corpus_intake_and_warning_contracts(self) -> None:
        policy = self._live_policy()

        self.assertEqual(policy["content_promotion_review"]["research_anchor_min_inbound_links"], 5)
        self.assertEqual(
            policy["page_shape"]["query_required_sections"],
            [
                "Question",
                "Short answer",
                "Evidence considered",
                "Analysis",
                "Decision / takeaway",
                "Follow-up questions",
            ],
        )
        self.assertEqual(
            policy["content_promotion_review"]["research_anchor_required_sections"],
            [
                "What this source adds to the corpus",
                "How strong is the evidence",
                "What this source does not establish",
            ],
        )
        self.assertEqual(
            policy["raw_markdown_normalization_contract"]["required_metadata"],
            ["title", "source", "published", "created"],
        )
        self.assertEqual(
            policy["raw_markdown_normalization_contract"]["allow_unknown"],
            ["published", "created"],
        )
        self.assertEqual(
            policy["raw_markdown_normalization_contract"]["disallow_unknown"],
            ["title", "source"],
        )
        self.assertEqual(
            policy["doc_audit"]["external_report_extensions"],
            [".pdf", ".docx", ".md"],
        )
        self.assertEqual(
            policy["raw_markdown_normalization_contract"]["removable_noise_classes"]["blob_prefixes"],
            ["blob:http://localhost"],
        )
        self.assertEqual(
            policy["strict_warning_budget"],
            {
                "default_profile": "release_clean",
                "profiles": {
                    "release_clean": {
                        "description": (
                            "Strict full-vault readiness gate for warning debt that should be "
                            "resolved before release packaging."
                        ),
                        "sources": {
                            "raw_registry_preflight": {
                                "warning_type_budgets": {
                                    "unregistered_raw_file": 0,
                                    "raw_markdown_blank_published": 0,
                                }
                            },
                            "wiki_lint": {
                                "warning_type_budgets": {
                                    "unregistered_raw_file": 0,
                                    "raw_markdown_blank_published": 0,
                                }
                            },
                        },
                    }
                },
            },
        )
        self.assertEqual(
            policy["system_refactor_policy"]["raw_registry_backlog_max_oldest_age_days_before_review"],
            30,
        )
        self.assertEqual(
            policy["system_refactor_policy"]["raw_registry_backlog_max_average_age_days_before_review"],
            14,
        )

    def test_live_policy_mechanism_review_and_mutation_contracts(self) -> None:
        policy = self._live_policy()

        self.assertEqual(policy["mechanism_review"]["families"]["self_mod_stability"]["tier"], "core")
        self.assertEqual(policy["mechanism_review"]["families"]["schema_drift"]["tier"], "core")
        self.assertEqual(
            policy["mechanism_review"]["families"]["policy_complexity_growth"]["tier"],
            "supporting",
        )
        self.assertEqual(
            policy["mechanism_review"]["families"]["contract_regression_signals"]["tier"],
            "supporting",
        )
        self.assertEqual(policy["mechanism_review"]["thresholds"]["stagnation_window"], 5)
        self.assertEqual(policy["mechanism_review"]["thresholds"]["repeated_schema_drift_runs"], 2)
        self.assertEqual(policy["mechanism_review"]["thresholds"]["repeated_policy_growth_runs"], 2)
        self.assertEqual(policy["mechanism_review"]["thresholds"]["policy_nonempty_growth_min_delta"], 8)
        self.assertEqual(
            policy["mechanism_review"]["thresholds"]["policy_complexity_score_growth_min_delta"],
            5,
        )
        self.assertEqual(
            policy["mechanism_review"]["calibration"],
            {
                "enabled": True,
                "lookback_runs": 6,
                "unstable_followup_window": 2,
                "priority_adjustments": {
                    "promoted_then_regressed": 15,
                    "repeated_same_eval_after_promote": 10,
                    "durable_promote": -10,
                },
                "session_priority_adjustments": {
                    "positive_cap": 12,
                    "negative_cap": 12,
                    "by_family": {
                        "self_mod_stability": {
                            "validation_blocked": 0,
                            "review_blocked": 0,
                            "mutation_failed": -5,
                            "validator_dispatch": 0,
                            "reviewer_dispatch": 0,
                            "high_risk_routing": -3,
                        },
                        "schema_drift": {
                            "validation_blocked": 6,
                            "review_blocked": 4,
                            "mutation_failed": 0,
                            "validator_dispatch": 2,
                            "reviewer_dispatch": 0,
                            "high_risk_routing": 0,
                        },
                        "policy_complexity_growth": {
                            "validation_blocked": 0,
                            "review_blocked": 0,
                            "mutation_failed": -4,
                            "validator_dispatch": 0,
                            "reviewer_dispatch": 0,
                            "high_risk_routing": -4,
                        },
                        "contract_regression_signals": {
                            "validation_blocked": 5,
                            "review_blocked": 4,
                            "mutation_failed": 0,
                            "validator_dispatch": 2,
                            "reviewer_dispatch": 1,
                            "high_risk_routing": 0,
                        },
                    },
                },
                "outcome_metrics_preview": {
                    "enabled": True,
                    "mode": "audit_only",
                    "source_report": "ops/reports/outcome-metrics.json",
                    "recent_window": 20,
                    "high_rework_count": 1,
                    "hold_or_discard_moving_average": 0.25,
                    "rollback_signal_ratio": 0.2,
                    "defect_escape_pair_count": 1,
                    "min_attempts_considered": 10,
                    "min_target_attempts": 2,
                    "shadow_priority_max_delta": 10,
                    "notes": [
                        (
                            "outcome metrics preview is diagnostic only and does not change "
                            "mechanism review priority."
                        ),
                        (
                            "priority_delta wiring requires a later explicit policy step after "
                            "the preview signal stabilizes."
                        ),
                    ],
                },
            },
        )
        self.assertEqual(policy["mutation_proposal"]["lookback_runs"], 5)
        self.assertEqual(policy["mutation_proposal"]["recent_log_overlap_max_age_days"], 7)
        self.assertEqual(
            policy["mutation_proposal"]["allowed_failure_modes"],
            [
                "branch_growth_without_test_growth",
                "high_complexity_low_test_pressure",
                "schema_change_without_test_guardrails",
                "policy_surface_growth_without_eval_gain",
                "repeated_same_eval_or_discard",
                "repeated_same_eval_after_promote",
                "repeated_discard_runs",
                "bootstrap_history_insufficient",
                "recent_log_overlap_queue_blocked",
                "next_run_failure_repair",
            ],
        )

    def test_live_policy_auto_improve_and_promotion_contracts(self) -> None:
        policy = self._live_policy()

        self.assertEqual(policy["auto_improve_policy"]["defaults"]["executor_timeout_seconds"], 2400)
        self.assertEqual(policy["auto_improve_policy"]["defaults"]["wrapper_command_timeout_seconds"], 5400)
        self.assertEqual(policy["auto_improve_policy"]["apply_mode"], "live")
        self.assertEqual(policy["auto_improve_policy"]["workspace_preparation"]["mode"], "full_copy")
        self.assertIn(
            "Makefile",
            policy["auto_improve_policy"]["workspace_preparation"]["declared_dependencies"],
        )
        self.assertEqual(
            policy["behavior_delta"],
            {
                "required_for_system_mechanism": False,
                "required_for_auto_improve": True,
                "required_for_equal_score_promotion": True,
            },
        )
        self.assertEqual(
            policy["equal_score_promotion"]["nonempty_line_growth_budget_per_added_test_case"],
            20,
        )
        self.assertEqual(
            policy["promotion_policy"]["decision_values"],
            ["PROMOTE", "HOLD", "DISCARD"],
        )
        self.assertEqual(
            policy["promotion_policy"]["log_defaults"]["status_values"],
            ["pending", "recorded", "not_required"],
        )
        self.assertEqual(
            policy["promotion_policy"]["rule_registry"]["page_class"],
            [
                "primary_target_scope",
                "primary_target_exists",
                "repo_lint_status",
                "current_policy_consistency",
                "primary_target_eval_full_pass",
                "primary_target_stage2_full_pass",
                "signoff_status",
            ],
        )
        self.assertEqual(
            policy["promotion_policy"]["rule_registry"]["system_mechanism"],
            [
                "primary_target_scope",
                "primary_target_exists",
                "report_consistency",
                "run_ledger_target_coverage",
                "mechanism_report_primary_targets",
                "changed_files_manifest_declared_targets",
                "changed_files_manifest_scope",
                "changed_files_manifest_allowed_apply_roots",
                "changed_files_manifest_nonempty",
                "changed_files_manifest_primary_targets_touched",
                "behavior_delta_presence",
                "candidate_lint_pass",
                "candidate_eval_pass",
                "eval_score_improves",
                "lint_non_regression",
                "lint_improves",
                "structural_complexity_non_regression",
                "structural_complexity_improves",
                "structural_regression_debt",
                "tests_non_regression",
                "tests_increase",
                "complexity_profile_score",
                "risk_flags",
                "equal_score_secondary_eligibility",
                "signoff_status",
            ],
        )
        page_rule_metadata = policy["promotion_policy"]["rule_metadata"]["page_class"]
        self.assertEqual(
            list(page_rule_metadata),
            policy["promotion_policy"]["rule_registry"]["page_class"],
        )
        self.assertEqual(
            page_rule_metadata["repo_lint_status"],
            {
                "artifact_dependencies": ["current_lint"],
                "reducer": "page_repo_lint_status",
                "severity": "blocker",
                "summary_template": "Page repo lint gate emitted {statuses}: {details}",
            },
        )
        mechanism_rule_metadata = policy["promotion_policy"]["rule_metadata"]["system_mechanism"]
        self.assertEqual(
            list(mechanism_rule_metadata),
            policy["promotion_policy"]["rule_registry"]["system_mechanism"],
        )
        self.assertEqual(
            mechanism_rule_metadata["behavior_delta_presence"],
            {
                "artifact_dependencies": ["behavior_delta", "policy"],
                "reducer": "status_fail_discard",
                "severity": "blocker",
                "summary_template": "Behavior-delta presence gate emitted {statuses}: {details}",
            },
        )
        self.assertEqual(
            mechanism_rule_metadata["candidate_eval_pass"]["artifact_dependencies"],
            ["baseline_eval_report", "candidate_eval_report"],
        )
        self.assertEqual(
            mechanism_rule_metadata["candidate_eval_pass"]["summary_template"],
            "Global eval non-regression guard emitted {statuses}: {details}",
        )
        self.assertEqual(
            mechanism_rule_metadata["eval_score_improves"],
            {
                "artifact_dependencies": [
                    "baseline_mechanism_contract_eval_report",
                    "candidate_mechanism_contract_eval_report",
                ],
                "reducer": "status_fail_discard",
                "severity": "blocker",
                "summary_template": (
                    "Mechanism contract eval score comparison emitted {statuses}: {details}"
                ),
            },
        )
        self.assertEqual(
            mechanism_rule_metadata["equal_score_secondary_eligibility"]["artifact_dependencies"][:2],
            [
                "baseline_mechanism_contract_eval_report",
                "candidate_mechanism_contract_eval_report",
            ],
        )
        self.assertEqual(
            mechanism_rule_metadata["lint_non_regression"]["reducer"],
            "none",
        )

    def test_live_policy_starter_runtime_and_packaging_contracts(self) -> None:
        policy = self._live_policy()

        self.assertEqual(
            policy["starter_bundles"]["planning_default"],
            {
                "path": "ops/templates",
                "phase": "starter",
                "promotion_report_input_placeholders": {},
            },
        )
        self.assertEqual(
            policy["starter_bundles"]["system_mechanism"],
            {
                "path": "ops/templates/mechanism-run",
                "phase": "starter",
                "promotion_report_input_placeholders": {
                    "run_ledger": ["runs/<run-id>/run-ledger.json"],
                    "changed_files_manifest": ["runs/<run-id>/changed-files-manifest.json"],
                    "behavior_delta": ["runs/<run-id>/behavior-delta.json"],
                },
            },
        )
        self.assertEqual(
            policy["runtime_defaults"]["display_timezone"],
            {"label": "KST", "utc_offset": "+09:00"},
        )
        self.assertEqual(
            policy["release_packaging"]["zip_normalization"],
            {
                "timestamp_utc": "1980-01-01T00:00:00Z",
                "file_mode_octal": "0644",
            },
        )

    def test_missing_research_anchor_keys_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)

            policy_text = LIVE_POLICY_PATH.read_text(encoding="utf-8")
            filtered_lines = [
                line
                for line in policy_text.splitlines()
                if "research_anchor_min_inbound_links" not in line
                and "research_anchor_required_sections" not in line
                and "What this source adds to the corpus" not in line
                and "How strong is the evidence" not in line
                and "What this source does not establish" not in line
            ]
            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                "\n".join(filtered_lines) + "\n",
                encoding="utf-8",
            )
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "content_promotion_review: missing required property 'research_anchor_min_inbound_links'",
            ):
                load_policy(root)

    def test_policy_schema_uses_bundled_fallback_when_vault_schema_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            policies_dir.mkdir(parents=True)
            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                LIVE_POLICY_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            policy, resolved_path = load_policy(root)

            self.assertEqual(resolved_path, policies_dir / "wiki-maintainer-policy.yaml")
            self.assertEqual(policy["promotion_policy"]["decision_values"], ["PROMOTE", "HOLD", "DISCARD"])

    def test_policy_schema_prefers_vault_override_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                LIVE_POLICY_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                '{"type": "object", "required": ["override_marker"]}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "invalid policy schema"):
                load_policy(root)

    def test_invalid_formula_output_range_and_enum_declarations_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("complexity_policy", "scoring", "output_range"),
                        "0-120",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "unsupported complexity_policy.scoring.output_range",
            ):
                load_policy(root)

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("complexity_policy", "scoring", "formula"),
                        "complexity_score = sum(weight_i * dimension_i)",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "unsupported complexity_policy.scoring.formula",
            ):
                load_policy(root)

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("promotion_policy", "decision_values"),
                        ["PROMOTE", "HOLD"],
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "unsupported promotion_policy.decision_values",
            ):
                load_policy(root)

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("auto_improve_policy", "defaults", "wrapper_command_timeout_seconds"),
                        1,
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "wrapper_command_timeout_seconds must be greater than or equal to executor_timeout_seconds",
            ):
                load_policy(root)

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("promotion_policy", "log_defaults", "status_values"),
                        ["pending", "recorded"],
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "unsupported promotion_policy.log_defaults.status_values",
            ):
                load_policy(root)

    def test_invalid_strict_warning_budget_references_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            base_text = LIVE_POLICY_PATH.read_text(encoding="utf-8")
            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                base_text.replace(
                    "  default_profile: release_clean\n",
                    "  default_profile: missing\n",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "strict_warning_budget.default_profile must reference a configured profile",
            ):
                load_policy(root)

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                base_text.replace(
                    "            raw_markdown_blank_published: 0\n",
                    "            raw_markdown_blank_published: 0\n            unknown_warning: 0\n",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "strict_warning_budget.profiles.release_clean.sources.raw_registry_preflight.warning_type_budgets references values outside lint_thresholds",
            ):
                load_policy(root)

    def test_promotion_rule_metadata_must_match_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            policy_text = LIVE_POLICY_PATH.read_text(encoding="utf-8").replace(
                "      signoff_status:\n        artifact_dependencies:\n",
                (
                    "      unknown_rule:\n"
                    "        artifact_dependencies: []\n"
                    "        reducer: none\n"
                    "        severity: info\n"
                    "        summary_template: \"Unknown metadata entry emitted {statuses}: {details}\"\n"
                    "      signoff_status:\n"
                    "        artifact_dependencies:\n"
                ),
                1,
            )
            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                policy_text,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "promotion_policy.rule_metadata.page_class must match",
            ):
                load_policy(root)

    def test_policy_decision_registry_rejects_additive_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _append_policy_path(
                        policy,
                        ("promotion_policy", "decision_values"),
                        "DEFER",
                    )
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported promotion_policy.decision_values"):
                load_policy(root)

    def test_non_decision_policy_enum_registries_allow_additive_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _append_policy_path(
                        policy,
                        ("promotion_policy", "log_defaults", "status_values"),
                        "skipped",
                    )
                ),
                encoding="utf-8",
            )

            policy, _ = load_policy(root)
            self.assertEqual(
                policy["promotion_policy"]["log_defaults"]["status_values"],
                ["pending", "recorded", "not_required", "skipped"],
            )

    def test_subagent_score_bands_are_policy_registry_driven(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            policy_text = LIVE_POLICY_PATH.read_text(encoding="utf-8").replace(
                "    high:\n      max_score: 64\n    extreme:\n      max_score: 100\n",
                (
                    "    high:\n"
                    "      max_score: 64\n"
                    "    very_high:\n"
                    "      max_score: 84\n"
                    "    extreme:\n"
                    "      max_score: 100\n"
                ),
                1,
            )
            lines: list[str] = []
            for line in policy_text.splitlines():
                if line.startswith("        extreme: "):
                    value = line.split(": ", 1)[1]
                    lines.append(f"        very_high: {value}")
                lines.append(line)
            policy_text = "\n".join(lines) + "\n"
            policy_text = policy_text.replace(
                "      - high\n      - extreme\n",
                "      - high\n      - very_high\n      - extreme\n",
                1,
            )
            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                policy_text,
                encoding="utf-8",
            )

            policy, _ = load_policy(root)
            self.assertEqual(score_band_name(policy, 80), "very_high")

    def test_invalid_subagent_ladder_declarations_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("subagent_routing_policy", "ladder", 0, "model"),
                        "gpt-4.1",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "unsupported subagent_routing_policy.ladder entry",
            ):
                load_policy(root)

    def test_invalid_timezone_and_zip_normalization_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policies_dir = root / "ops" / "policies"
            schemas_dir = root / "ops" / "schemas"
            policies_dir.mkdir(parents=True)
            schemas_dir.mkdir(parents=True)
            (schemas_dir / "wiki-maintainer-policy.schema.json").write_text(
                POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("runtime_defaults", "display_timezone", "utc_offset"),
                        "KST",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "unsupported runtime_defaults.display_timezone.utc_offset",
            ):
                load_policy(root)

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("release_packaging", "zip_normalization", "timestamp_utc"),
                        "1970-01-01T00:00:00Z",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "release_packaging.zip_normalization.timestamp_utc must be >= 1980-01-01T00:00:00Z",
            ):
                load_policy(root)

            (policies_dir / "wiki-maintainer-policy.yaml").write_text(
                _mutated_live_policy_text(
                    lambda policy: _set_policy_path(
                        policy,
                        ("release_packaging", "zip_normalization", "file_mode_octal"),
                        "xyz",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "unsupported release_packaging.zip_normalization.file_mode_octal",
            ):
                load_policy(root)


if __name__ == "__main__":
    unittest.main()
