from __future__ import annotations

import datetime as dt
import unittest
from copy import deepcopy
from pathlib import Path

from ops.scripts.policy_runtime import load_policy
from ops.scripts.policy_validation_runtime import (
    POLICY_SAFETY_INVARIANT_RULES,
    display_timezone_from_policy,
    release_archive_root_name_from_policy,
    validate_policy_registry_references,
    validate_policy_safety_invariants,
    workspace_preparation_declared_dependencies_from_policy,
    workspace_preparation_mode_from_policy,
    zip_normalization_from_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_live_policy() -> dict:
    policy, _ = load_policy(REPO_ROOT)
    return policy


class PolicyValidationRuntimeTests(unittest.TestCase):
    def test_policy_safety_invariant_rules_are_named_and_stable(self) -> None:
        rules = POLICY_SAFETY_INVARIANT_RULES

        self.assertEqual(
            [rule.rule_id for rule in rules],
            [
                "required_runtime_paths",
                "complexity_policy_contract",
                "subagent_safety_contract",
                "auto_improve_safety_contract",
                "complexity_ratchet_contract",
                "strict_warning_budget_contract",
                "raw_registry_shard_policy_contract",
                "runtime_defaults_contract",
            ],
        )
        self.assertTrue(all(rule.summary for rule in rules))

        policy = _load_live_policy()
        for rule in rules:
            rule.evaluate(policy)

    def test_display_timezone_from_policy_returns_named_timezone(self) -> None:
        timezone = display_timezone_from_policy(_load_live_policy())
        sample = dt.datetime(2026, 4, 21, 12, 0, tzinfo=timezone)

        self.assertEqual(sample.utcoffset(), dt.timedelta(hours=9))
        self.assertTrue(timezone.tzname(sample))

    def test_zip_normalization_from_policy_returns_expected_values(self) -> None:
        policy = _load_live_policy()
        normalization = zip_normalization_from_policy(policy)

        self.assertEqual(normalization["timestamp_utc"].utcoffset(), dt.timedelta(0))
        self.assertEqual(
            normalization["file_mode"],
            int(policy["release_packaging"]["zip_normalization"]["file_mode_octal"], 8),
        )
        self.assertEqual(release_archive_root_name_from_policy(policy), "LLMwiki")

    def test_validate_policy_safety_invariants_rejects_short_wrapper_timeout(self) -> None:
        policy = deepcopy(_load_live_policy())
        defaults = policy["auto_improve_policy"]["defaults"]
        defaults["wrapper_command_timeout_seconds"] = defaults["executor_timeout_seconds"] - 1

        with self.assertRaisesRegex(
            ValueError,
            "wrapper_command_timeout_seconds must be greater than or equal",
        ):
            validate_policy_safety_invariants(policy)

    def test_workspace_preparation_mode_defaults_and_rejects_unknown_modes(self) -> None:
        policy = deepcopy(_load_live_policy())
        policy["auto_improve_policy"].pop("workspace_preparation", None)
        self.assertEqual(workspace_preparation_mode_from_policy(policy), "full_copy")
        self.assertEqual(workspace_preparation_declared_dependencies_from_policy(policy), [])
        validate_policy_safety_invariants(policy)

        policy["auto_improve_policy"]["workspace_preparation"] = {"mode": "unsupported"}
        with self.assertRaisesRegex(
            ValueError,
            "unsupported auto_improve_policy.workspace_preparation.mode",
        ):
            validate_policy_safety_invariants(policy)

    def test_workspace_preparation_declared_dependencies_normalize_and_reject_invalid_paths(self) -> None:
        policy = deepcopy(_load_live_policy())
        policy["auto_improve_policy"]["workspace_preparation"] = {
            "mode": "sparse_manifest",
            "declared_dependencies": ["tools/", "tools", "../raw"],
        }

        with self.assertRaisesRegex(
            ValueError,
            "invalid auto_improve_policy.workspace_preparation.declared_dependencies entry",
        ):
            validate_policy_safety_invariants(policy)

        policy["auto_improve_policy"]["workspace_preparation"]["declared_dependencies"] = [
            "tools/",
            "tools",
            "Makefile",
        ]
        self.assertEqual(
            workspace_preparation_declared_dependencies_from_policy(policy),
            ["tools", "Makefile"],
        )

    def test_complexity_ratchet_policy_requires_disjoint_warn_and_resolved_sets(self) -> None:
        policy = deepcopy(_load_live_policy())
        ratchet = policy["system_refactor_policy"]["complexity_ratchet"]
        ratchet["resolved_targets"] = [ratchet["warn_targets"][0]]

        with self.assertRaisesRegex(
            ValueError,
            "warn_targets and resolved_targets must be disjoint",
        ):
            validate_policy_safety_invariants(policy)

    def test_validate_policy_registry_references_rejects_unknown_reviewer_score_band(self) -> None:
        policy = deepcopy(_load_live_policy())
        policy["auto_improve_policy"]["scope_resolution"]["reviewer_score_bands"] = [
            "medium",
            "unsupported_band",
        ]

        with self.assertRaisesRegex(
            ValueError,
            "reviewer_score_bands references values outside",
        ):
            validate_policy_registry_references(policy)

    def test_raw_registry_shard_policy_contract_requires_frontmatter_special_page(self) -> None:
        policy = deepcopy(_load_live_policy())
        shard_page = policy["registry_contract"]["raw_registry_shard_pages"][0]
        policy["frontmatter_contract"]["special_pages"].pop(shard_page)

        with self.assertRaisesRegex(
            ValueError,
            "frontmatter_contract.special_pages must define every raw registry shard page",
        ):
            validate_policy_safety_invariants(policy)

    def test_raw_registry_shard_policy_contract_rejects_wrong_special_page_shape(self) -> None:
        policy = deepcopy(_load_live_policy())
        shard_page = policy["registry_contract"]["raw_registry_shard_pages"][0]
        policy["frontmatter_contract"]["special_pages"][shard_page]["expected"][
            "page_type"
        ] = "registry"

        with self.assertRaisesRegex(
            ValueError,
            "raw registry shard rules must expect page_type=registry-shard",
        ):
            validate_policy_safety_invariants(policy)
