from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.registry_alignment_passes_runtime import (
    _locator_raw_path_corpus_consistency_pass,
    _registry_frontmatter_alignment_pass,
)
from ops.scripts.core.registry_diagnostics_runtime import RegistryInventoryContext
from ops.scripts.core.registry_pass_support_runtime import registry_review_exempt_paths
from ops.scripts.core.registry_review_candidate_passes_runtime import (
    _backlog_refactor_threshold_pass,
    _summary_shard_review_candidate_pass,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.eval.wiki_lint_registry_runtime import (
    RegistryLintEmitter,
    _registry_inventory_context_pass,
    _registry_lint_paths,
    _registry_page_presence_pass,
    lint_registry_contract,
)
from ops.scripts.eval.wiki_lint_review_runtime import review_candidates_for
from ops.scripts.eval.wiki_snapshot_runtime import build_wiki_runtime_snapshot
from tests.minimal_vault_runtime import (
    add_registry_entry_scalar_field,
    seed_minimal_vault,
    set_policy_value,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2000, 1, 3, 12, tzinfo=dt.UTC),
    )


def override_system_refactor_policy(vault: Path, **overrides: int) -> None:
    for key, value in overrides.items():
        set_policy_value(vault, ("system_refactor_policy", key), value)


def add_topic_family_to_wiki_shard(vault: Path, family: str) -> None:
    add_registry_entry_scalar_field(
        vault / "system" / "system-raw-registry" / "wiki.md",
        "R-100",
        "topic family",
        family,
        after_field="domain",
    )


def add_topic_subfamily_to_wiki_shard(vault: Path, subfamily: str) -> None:
    add_registry_entry_scalar_field(
        vault / "system" / "system-raw-registry" / "wiki.md",
        "R-100",
        "topic subfamily",
        subfamily,
        after_field="topic family",
    )


def build_registry_review_candidates(vault: Path) -> list[dict]:
    policy, _ = load_policy(vault)
    paths = _registry_lint_paths(vault, policy["registry_contract"])
    emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])
    context = _registry_inventory_context_pass(
        vault,
        paths,
        registry_contract=policy["registry_contract"],
        corpus_routing=policy["corpus_routing"],
        emitter=emitter,
    )
    if context is None:
        raise AssertionError("expected registry inventory context for seeded vault")

    _summary_shard_review_candidate_pass(
        vault,
        paths,
        inventory_context=context,
        system_refactor_policy=policy["system_refactor_policy"],
        emitter=emitter,
    )
    _backlog_refactor_threshold_pass(
        vault,
        paths,
        inventory_context=context,
        system_refactor_policy=policy["system_refactor_policy"],
        emitter=emitter,
    )
    return emitter.review_candidates


def build_inventory_context_with_entries(policy: dict, entries: list[dict]) -> RegistryInventoryContext:
    return RegistryInventoryContext(
        registry_entries=entries,
        registered_raw_paths={entry["storage_path"] for entry in entries},
        entries_by_page={},
        corpus_counts={},
        total_entry_count=len(entries),
        shard_corpus_by_page={},
        registry_id_to_entries={},
        registry_id_to_entry={},
        locator_groups={},
        raw_sha256_index=None,
        resolution_stats={},
        corpus_roots=policy["registry_contract"]["corpus_roots"],
        type_to_corpus=policy["corpus_routing"]["type_to_corpus"],
        default_corpus=policy["corpus_routing"]["default_corpus"],
        route_overrides=policy["corpus_routing"].get("route_overrides", {}),
    )


class WikiLintRegistryRuntimeTests(unittest.TestCase):
    def test_registry_page_presence_pass_emits_missing_summary_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            policy, _ = load_policy(vault)
            paths = _registry_lint_paths(vault, policy["registry_contract"])
            emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])

            paths.raw_registry_path.unlink()
            ready = _registry_page_presence_pass(
                vault,
                paths,
                registry_contract=policy["registry_contract"],
                emitter=emitter,
            )

            self.assertFalse(ready)
            self.assertEqual(emitter.errors[0]["type"], "missing_raw_registry_page")

    def test_registry_frontmatter_alignment_pass_emits_missing_registry_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            policy, _ = load_policy(vault)
            paths = _registry_lint_paths(vault, policy["registry_contract"])
            emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])
            context = _registry_inventory_context_pass(
                vault,
                paths,
                registry_contract=policy["registry_contract"],
                corpus_routing=policy["corpus_routing"],
                emitter=emitter,
            )
            self.assertIsNotNone(context)

            source_page = vault / "wiki" / "source--fake.md"
            source_page.write_text(
                source_page.read_text(encoding="utf-8").replace('registry_id: "R-100"', 'registry_id: "R-404"'),
                encoding="utf-8",
            )
            snapshot = build_wiki_runtime_snapshot(vault, registry_contract=policy["registry_contract"])
            _registry_frontmatter_alignment_pass(
                vault,
                pages=snapshot.pages,
                frontmatters=snapshot.frontmatters,
                frontmatter_contract=policy["frontmatter_contract"],
                inventory_context=context,
                emitter=emitter,
            )

            issue_types = {issue["type"] for issue in emitter.errors + emitter.warnings}
            self.assertIn("source_frontmatter_registry_missing_entry", issue_types)

    def test_backlog_refactor_threshold_pass_emits_backlog_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            policy, _ = load_policy(vault)
            set_policy_value(
                vault,
                ("system_refactor_policy", "raw_registry_backlog_max_count_before_review"),
                0,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "raw_registry_backlog_max_ratio_before_review"),
                0.0,
            )
            add_registry_entry_scalar_field(
                vault / "system" / "system-raw-registry" / "wiki.md",
                "R-100",
                "status",
                "registered-not-ingested",
                after_field="target_page",
            )
            policy, _ = load_policy(vault)
            paths = _registry_lint_paths(vault, policy["registry_contract"])
            emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])
            context = _registry_inventory_context_pass(
                vault,
                paths,
                registry_contract=policy["registry_contract"],
                corpus_routing=policy["corpus_routing"],
                emitter=emitter,
            )
            self.assertIsNotNone(context)

            _backlog_refactor_threshold_pass(
                vault,
                paths,
                inventory_context=context,
                system_refactor_policy=policy["system_refactor_policy"],
                emitter=emitter,
                runtime_context=fixed_context(),
            )

            candidate_types = {candidate["type"] for candidate in emitter.review_candidates}
            self.assertIn("raw_registry_shard_backlog_over_threshold", candidate_types)

    def test_backlog_refactor_threshold_pass_emits_age_based_backlog_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            set_policy_value(
                vault,
                ("system_refactor_policy", "raw_registry_backlog_max_oldest_age_days_before_review"),
                1,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "raw_registry_backlog_max_average_age_days_before_review"),
                1,
            )
            add_registry_entry_scalar_field(
                vault / "system" / "system-raw-registry" / "wiki.md",
                "R-100",
                "status",
                "registered-not-ingested",
                after_field="target_page",
            )
            add_registry_entry_scalar_field(
                vault / "system" / "system-raw-registry" / "wiki.md",
                "R-100",
                "registered on",
                "`2000-01-01`",
                after_field="status",
            )
            policy, _ = load_policy(vault)
            paths = _registry_lint_paths(vault, policy["registry_contract"])
            emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])
            context = _registry_inventory_context_pass(
                vault,
                paths,
                registry_contract=policy["registry_contract"],
                corpus_routing=policy["corpus_routing"],
                emitter=emitter,
            )
            self.assertIsNotNone(context)

            _backlog_refactor_threshold_pass(
                vault,
                paths,
                inventory_context=context,
                system_refactor_policy=policy["system_refactor_policy"],
                emitter=emitter,
                runtime_context=fixed_context(),
            )

            age_candidate = next(
                candidate
                for candidate in emitter.review_candidates
                if candidate["type"] == "raw_registry_shard_pending_age_over_threshold"
            )
            self.assertEqual(age_candidate["page"], "system/system-raw-registry/wiki.md")
            self.assertEqual(age_candidate["supporting_registry_ids"], ["R-100"])
            self.assertEqual(age_candidate["value"]["oldest_pending_age_days"], 2)
            self.assertEqual(age_candidate["value"]["average_pending_age_days"], 2.0)
            self.assertEqual(age_candidate["threshold"]["oldest_pending_age_days"], 1)

    def test_lint_registry_contract_keeps_runtime_and_inventory_contexts_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            set_policy_value(
                vault,
                ("system_refactor_policy", "raw_registry_backlog_max_oldest_age_days_before_review"),
                1,
            )
            set_policy_value(
                vault,
                ("system_refactor_policy", "raw_registry_backlog_max_average_age_days_before_review"),
                1,
            )
            add_registry_entry_scalar_field(
                vault / "system" / "system-raw-registry" / "wiki.md",
                "R-100",
                "status",
                "registered-not-ingested",
                after_field="target_page",
            )
            add_registry_entry_scalar_field(
                vault / "system" / "system-raw-registry" / "wiki.md",
                "R-100",
                "registered on",
                "`2000-01-01`",
                after_field="status",
            )
            policy, _ = load_policy(vault)
            snapshot = build_wiki_runtime_snapshot(
                vault,
                registry_contract=policy["registry_contract"],
            )

            result = lint_registry_contract(
                vault,
                snapshot.pages,
                snapshot.frontmatters,
                policy["frontmatter_contract"],
                policy["lint_thresholds"],
                policy["system_refactor_policy"],
                policy["registry_contract"],
                policy["corpus_routing"],
                policy["frontmatter_contract"]["metadata_review"]["source_page_slug"],
                context=fixed_context(),
            )

            age_candidate = next(
                candidate
                for candidate in result["review_candidates"]
                if candidate["type"] == "raw_registry_shard_pending_age_over_threshold"
            )
            self.assertEqual(age_candidate["value"]["oldest_pending_age_days"], 2)

    def test_registry_review_candidates_request_topic_family_labels_before_split(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            override_system_refactor_policy(
                vault,
                raw_registry_shard_max_entries_before_review=0,
                raw_registry_summary_max_lines_before_review=999,
                raw_registry_shard_max_lines_before_review=999,
            )

            candidate_types = {
                candidate["type"] for candidate in build_registry_review_candidates(vault)
            }

            self.assertIn("raw_registry_shard_needs_topic_family", candidate_types)
            self.assertNotIn("raw_registry_topic_family_needs_subfamily", candidate_types)

    def test_registry_review_candidates_request_topic_subfamily_when_family_labels_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
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
                for candidate in build_registry_review_candidates(vault)
                if candidate["type"] == "raw_registry_topic_family_needs_subfamily"
            )

            self.assertEqual(family_candidate["topic_family"], "coffee-science-and-brewing")
            self.assertEqual(family_candidate["value"]["missing_topic_subfamily_count"], 1)

    def test_registry_review_candidates_request_subfamily_router_when_labels_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            add_topic_family_to_wiki_shard(vault, "coffee-science-and-brewing")
            add_topic_subfamily_to_wiki_shard(
                vault,
                "coffee-extraction-models-and-brew-control",
            )
            override_system_refactor_policy(
                vault,
                raw_registry_shard_max_entries_before_review=0,
                raw_registry_topic_family_min_entries_before_review=1,
                raw_registry_topic_family_min_unique_target_pages_before_review=1,
                raw_registry_topic_subfamily_min_entries_before_review=1,
                raw_registry_summary_max_lines_before_review=999,
                raw_registry_shard_max_lines_before_review=999,
            )

            subfamily_candidate = next(
                candidate
                for candidate in build_registry_review_candidates(vault)
                if candidate["type"] == "raw_registry_topic_subfamily_over_threshold"
            )

            self.assertEqual(subfamily_candidate["topic_family"], "coffee-science-and-brewing")
            self.assertEqual(
                subfamily_candidate["topic_subfamily"],
                "coffee-extraction-models-and-brew-control",
            )

    def test_registry_review_candidates_use_shard_line_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            add_topic_family_to_wiki_shard(vault, "ai-capability-and-agent-strategy")
            override_system_refactor_policy(
                vault,
                raw_registry_shard_max_lines_before_review=1,
                raw_registry_summary_max_lines_before_review=999,
            )

            shard_candidate = next(
                candidate
                for candidate in build_registry_review_candidates(vault)
                if candidate["type"] == "raw_registry_shard_lines_over_threshold"
            )

            self.assertEqual(shard_candidate["page"], "system/system-raw-registry/wiki.md")
            self.assertEqual(
                shard_candidate["top_contributing_families"][0]["topic_family"],
                "ai-capability-and-agent-strategy",
            )

    def test_review_candidates_for_skips_generic_page_line_review_for_registry_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            policy, _ = load_policy(vault)
            registry_page = vault / "system" / "system-raw-registry.md"
            candidates = review_candidates_for(
                vault,
                registry_page,
                registry_page.read_text(encoding="utf-8"),
                {
                    **policy["refactor_triggers"],
                    "max_page_lines_before_review": 1,
                },
                policy["system_refactor_policy"],
                registry_review_exempt_paths(policy["registry_contract"]),
            )

            self.assertEqual(candidates, [])

    def test_registry_inventory_context_pass_surfaces_typed_parse_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            policy, _ = load_policy(vault)
            paths = _registry_lint_paths(vault, policy["registry_contract"])
            emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])
            shard = vault / "system" / "system-raw-registry" / "wiki.md"
            shard.write_text("# bad\n\n#### R-100\noops\n", encoding="utf-8")

            context = _registry_inventory_context_pass(
                vault,
                paths,
                registry_contract=policy["registry_contract"],
                corpus_routing=policy["corpus_routing"],
                emitter=emitter,
            )

            self.assertIsNone(context)
            self.assertEqual(emitter.errors[0]["type"], "raw_registry_parse_error")
            self.assertEqual(
                emitter.errors[0]["detail"]["diagnostic_type"],
                "raw_registry_invalid_continuation_line",
            )

    def test_locator_raw_path_corpus_consistency_allows_explicit_system_news_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            policy, _ = load_policy(vault)
            paths = _registry_lint_paths(vault, policy["registry_contract"])
            emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])
            context = build_inventory_context_with_entries(
                policy,
                [
                    {
                        "_registry_page": "system/system-raw-registry/system.md",
                        "registry_id": "R-200",
                        "storage_path": "raw/web-snapshots/system-news.md",
                        "display_path": "raw/web-snapshots/system-news.md",
                        "type": "news-snapshot",
                        "corpus": "system",
                        "target_page": "source--system-news",
                        "status": "registered-not-ingested",
                        "corpus_route_override": "system",
                        "override_reason": "Maintainer-runtime evidence for anti-slop governance policy.",
                    }
                ],
            )

            _locator_raw_path_corpus_consistency_pass(
                vault,
                paths,
                inventory_context=context,
                emitter=emitter,
            )

            issue_types = {issue["type"] for issue in emitter.errors + emitter.warnings}
            self.assertNotIn("corpus_routing_mismatch", issue_types)

    def test_locator_raw_path_corpus_consistency_rejects_system_news_without_override_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = build_vault(temp_dir)
            policy, _ = load_policy(vault)
            paths = _registry_lint_paths(vault, policy["registry_contract"])
            emitter = RegistryLintEmitter(lint_thresholds=policy["lint_thresholds"])
            context = build_inventory_context_with_entries(
                policy,
                [
                    {
                        "_registry_page": "system/system-raw-registry/system.md",
                        "registry_id": "R-201",
                        "storage_path": "raw/web-snapshots/system-news.md",
                        "display_path": "raw/web-snapshots/system-news.md",
                        "type": "news-snapshot",
                        "corpus": "system",
                        "target_page": "source--system-news",
                        "status": "registered-not-ingested",
                        "corpus_route_override": "system",
                    }
                ],
            )

            _locator_raw_path_corpus_consistency_pass(
                vault,
                paths,
                inventory_context=context,
                emitter=emitter,
            )

            mismatch = next(
                issue for issue in emitter.errors if issue["type"] == "corpus_routing_mismatch"
            )
            self.assertEqual(
                mismatch["detail"]["route_override"]["reason"],
                "override_requirements_not_met",
            )
            self.assertEqual(
                mismatch["detail"]["route_override"]["missing_fields"],
                ["override_reason"],
            )


def build_vault(temp_dir: str) -> Path:
    vault = Path(temp_dir) / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    return vault


if __name__ == "__main__":
    unittest.main()
