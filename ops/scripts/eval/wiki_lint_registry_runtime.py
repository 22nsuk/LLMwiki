from __future__ import annotations

import datetime as dt
from pathlib import Path

from ops.scripts.core.registry_alignment_passes_runtime import (
    _locator_raw_path_corpus_consistency_pass,
    _registry_frontmatter_alignment_pass,
    locator_raw_path_corpus_consistency_pass,
    registry_frontmatter_alignment_pass,
)
from ops.scripts.core.registry_diagnostics_runtime import (
    RegistryDiagnosticEmitter as RegistryLintEmitter,
    RegistryInventoryContext,
    RegistryPaths as RegistryLintPaths,
    registry_diagnostic_paths as _registry_lint_paths,
    registry_inventory_context_pass as _registry_inventory_context_pass,
    registry_page_presence_pass as _registry_page_presence_pass,
    registry_raw_inventory_consistency_pass as _raw_inventory_consistency_pass,
    registry_shared_inventory_diagnostics_pass as _shared_registry_inventory_diagnostics_pass,
    registry_source_target_page_naming_pass as _registry_source_target_page_naming_pass,
    registry_summary_consistency_pass as _registry_summary_consistency_pass,
)
from ops.scripts.core.registry_pass_support_runtime import (
    _backlog_entry_age_days,
    _parse_registry_iso_date,
    registry_entry_line_span,
    registry_entry_target_report_path,
    registry_review_exempt_paths,
    registry_topic_family,
    registry_topic_subfamily,
)
from ops.scripts.core.registry_review_candidate_passes_runtime import (
    _backlog_refactor_threshold_pass,
    _summary_shard_review_candidate_pass,
    backlog_refactor_threshold_pass,
    summary_shard_review_candidate_pass,
)
from ops.scripts.core.runtime_context import RuntimeContext


def lint_registry_contract(
    vault: Path,
    pages: dict[str, Path],
    frontmatters: dict[str, dict | None],
    frontmatter_contract: dict,
    lint_thresholds: dict,
    system_refactor_policy: dict,
    registry_contract: dict,
    corpus_routing: dict,
    source_page_slug_review: dict,
    *,
    context: RuntimeContext | None = None,
) -> dict:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    emitter = RegistryLintEmitter(lint_thresholds=lint_thresholds)
    paths = _registry_lint_paths(vault, registry_contract)
    registry_entries: list[dict] = []
    registered_raw_paths: set[str] = set()

    if _registry_page_presence_pass(
        vault,
        paths,
        registry_contract=registry_contract,
        emitter=emitter,
    ):
        inventory_context = _registry_inventory_context_pass(
            vault,
            paths,
            registry_contract=registry_contract,
            corpus_routing=corpus_routing,
            emitter=emitter,
        )
        if inventory_context is not None:
            registry_entries = inventory_context.registry_entries
            registered_raw_paths = inventory_context.registered_raw_paths
            _summary_shard_review_candidate_pass(
                vault,
                paths,
                inventory_context=inventory_context,
                system_refactor_policy=system_refactor_policy,
                emitter=emitter,
            )
            _registry_summary_consistency_pass(
                vault,
                paths,
                context=inventory_context,
                emitter=emitter,
            )
            _backlog_refactor_threshold_pass(
                vault,
                paths,
                inventory_context=inventory_context,
                system_refactor_policy=system_refactor_policy,
                emitter=emitter,
                runtime_context=runtime_context,
            )
            _registry_frontmatter_alignment_pass(
                vault,
                pages=pages,
                frontmatters=frontmatters,
                frontmatter_contract=frontmatter_contract,
                inventory_context=inventory_context,
                emitter=emitter,
            )
            _shared_registry_inventory_diagnostics_pass(
                vault,
                paths,
                context=inventory_context,
                emitter=emitter,
            )
            _registry_source_target_page_naming_pass(
                vault,
                paths,
                context=inventory_context,
                source_page_slug_review=source_page_slug_review,
                emitter=emitter,
            )
            _locator_raw_path_corpus_consistency_pass(
                vault,
                paths,
                inventory_context=inventory_context,
                emitter=emitter,
            )
            _raw_inventory_consistency_pass(
                vault,
                paths,
                context=inventory_context,
                emitter=emitter,
            )

    return {
        "errors": emitter.errors,
        "warnings": emitter.warnings,
        "review_candidates": emitter.review_candidates,
        "registered_raw_paths": registered_raw_paths,
        "registry_entries": registry_entries,
    }


__all__ = [
    "RegistryInventoryContext",
    "RegistryLintEmitter",
    "RegistryLintPaths",
    "_backlog_entry_age_days",
    "_backlog_refactor_threshold_pass",
    "_locator_raw_path_corpus_consistency_pass",
    "_parse_registry_iso_date",
    "_raw_inventory_consistency_pass",
    "_registry_frontmatter_alignment_pass",
    "_registry_inventory_context_pass",
    "_registry_lint_paths",
    "_registry_page_presence_pass",
    "_registry_source_target_page_naming_pass",
    "_registry_summary_consistency_pass",
    "_shared_registry_inventory_diagnostics_pass",
    "_summary_shard_review_candidate_pass",
    "backlog_refactor_threshold_pass",
    "lint_registry_contract",
    "locator_raw_path_corpus_consistency_pass",
    "registry_entry_line_span",
    "registry_entry_target_report_path",
    "registry_frontmatter_alignment_pass",
    "registry_review_exempt_paths",
    "registry_topic_family",
    "registry_topic_subfamily",
    "summary_shard_review_candidate_pass",
]
