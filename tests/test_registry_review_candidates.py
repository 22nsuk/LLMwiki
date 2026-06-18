from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.eval.wiki_lint import lint
from tests.minimal_vault_runtime import (
    add_registry_entry_scalar_field,
    seed_registry_review_smoke_vault,
    set_policy_value,
)
from tests.vault_test_runtime import SeededMinimalVaultTestCase

pytestmark = pytest.mark.slow


def override_system_refactor_policy(vault: Path, **overrides: int | float) -> None:
    for key, value in overrides.items():
        set_policy_value(vault, ("system_refactor_policy", key), value)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2000, 1, 3, 12, tzinfo=dt.UTC),
    )


def add_topic_family_to_wiki_shard(vault: Path, family: str) -> None:
    add_registry_entry_scalar_field(
        vault / "system" / "system-raw-registry" / "wiki.md",
        "R-100",
        "topic family",
        family,
        after_field="domain",
    )


def mark_wiki_shard_entry_as_pending(vault: Path, *, registered_on: str | None = None) -> None:
    add_registry_entry_scalar_field(
        vault / "system" / "system-raw-registry" / "wiki.md",
        "R-100",
        "status",
        "registered-not-ingested",
        after_field="target_page",
    )
    if registered_on is not None:
        add_registry_entry_scalar_field(
            vault / "system" / "system-raw-registry" / "wiki.md",
            "R-100",
            "registered on",
            f"`{registered_on}`",
            after_field="status",
        )


class RegistryReviewCandidatesTest(SeededMinimalVaultTestCase):
    @classmethod
    def seed_vault(cls, vault: Path) -> None:
        seed_registry_review_smoke_vault(vault)

    @classmethod
    def fresh_vault_strategy(cls) -> str:
        return "reseed"

    def test_lint_wires_registry_topic_family_review_candidate(self) -> None:
        with self.fresh_vault() as vault:
            add_topic_family_to_wiki_shard(vault, "coffee-science-and-brewing")
            override_system_refactor_policy(
                vault,
                raw_registry_shard_max_entries_before_review=0,
                raw_registry_topic_family_min_entries_before_review=1,
                raw_registry_topic_family_min_unique_target_pages_before_review=1,
                raw_registry_summary_max_lines_before_review=999,
                raw_registry_shard_max_lines_before_review=999,
            )

            family_candidate = next(
                candidate
                for candidate in lint(vault)["review_candidates"]
                if candidate["type"] == "raw_registry_topic_family_needs_subfamily"
            )

            self.assertEqual(family_candidate["page"], "system/system-raw-registry/wiki.md")
            self.assertEqual(family_candidate["topic_family"], "coffee-science-and-brewing")
            self.assertEqual(family_candidate["suggested_action"], "review_add_topic_subfamily_labels")

    def test_lint_preserves_backlog_threshold_candidate_payload_shape(self) -> None:
        with self.fresh_vault() as vault:
            mark_wiki_shard_entry_as_pending(vault)
            override_system_refactor_policy(
                vault,
                raw_registry_backlog_max_count_before_review=0,
                raw_registry_backlog_max_ratio_before_review=0.0,
            )

            backlog_candidate = next(
                candidate
                for candidate in lint(vault)["review_candidates"]
                if candidate["type"] == "raw_registry_shard_backlog_over_threshold"
            )

            self.assertEqual(
                backlog_candidate,
                {
                    "type": "raw_registry_shard_backlog_over_threshold",
                    "page": "system/system-raw-registry/wiki.md",
                    "value": {
                        "backlog_count": 1,
                        "backlog_ratio": 1.0,
                    },
                    "threshold": {
                        "backlog_count": 0,
                        "backlog_ratio": 0.0,
                    },
                    "supporting_registry_ids": ["R-100"],
                    "suggested_action": "review_registry_backlog_or_ingest_queue",
                },
            )
            self.assertEqual(
                list(backlog_candidate.keys()),
                [
                    "type",
                    "page",
                    "value",
                    "threshold",
                    "supporting_registry_ids",
                    "suggested_action",
                ],
            )

    def test_lint_preserves_pending_age_candidate_payload_shape_and_order(self) -> None:
        with self.fresh_vault() as vault:
            mark_wiki_shard_entry_as_pending(vault, registered_on="2000-01-01")
            override_system_refactor_policy(
                vault,
                raw_registry_backlog_max_oldest_age_days_before_review=1,
                raw_registry_backlog_max_average_age_days_before_review=1,
                raw_registry_backlog_max_count_before_review=0,
                raw_registry_backlog_max_ratio_before_review=0.0,
            )

            review_candidates = lint(vault, context=fixed_context())["review_candidates"]
            backlog_candidate_types = [
                candidate["type"]
                for candidate in review_candidates
                if candidate["type"]
                in {
                    "raw_registry_shard_backlog_over_threshold",
                    "raw_registry_shard_pending_age_over_threshold",
                }
            ]
            self.assertEqual(
                backlog_candidate_types,
                [
                    "raw_registry_shard_backlog_over_threshold",
                    "raw_registry_shard_pending_age_over_threshold",
                ],
            )

            age_candidate = next(
                candidate
                for candidate in review_candidates
                if candidate["type"] == "raw_registry_shard_pending_age_over_threshold"
            )
            self.assertEqual(
                age_candidate,
                {
                    "type": "raw_registry_shard_pending_age_over_threshold",
                    "page": "system/system-raw-registry/wiki.md",
                    "value": {
                        "dated_backlog_count": 1,
                        "undated_backlog_count": 0,
                        "oldest_pending_age_days": 2,
                        "average_pending_age_days": 2.0,
                    },
                    "threshold": {
                        "oldest_pending_age_days": 1,
                        "average_pending_age_days": 1,
                    },
                    "supporting_registry_ids": ["R-100"],
                    "suggested_action": "review_registry_backlog_age_or_ingest_queue",
                },
            )
            self.assertEqual(
                list(age_candidate.keys()),
                [
                    "type",
                    "page",
                    "value",
                    "threshold",
                    "supporting_registry_ids",
                    "suggested_action",
                ],
            )


if __name__ == "__main__":
    unittest.main()
