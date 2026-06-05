from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.wiki_page_runtime import line_count

from .candidate_rule_runtime import CandidateRuleSpec, evaluate_candidate_rules
from .policy_runtime import report_path
from .registry_diagnostics_runtime import (
    RegistryDiagnosticEmitter as RegistryLintEmitter,
    RegistryInventoryContext,
    RegistryPaths as RegistryLintPaths,
)
from .registry_pass_support_runtime import (
    _backlog_entry_age_days,
    registry_entry_line_span,
    registry_entry_target_report_path,
    registry_topic_family,
    registry_topic_subfamily,
)
from .runtime_context import RuntimeContext


def _summary_shard_review_candidate_pass(
    vault: Path,
    paths: RegistryLintPaths,
    *,
    inventory_context: RegistryInventoryContext,
    system_refactor_policy: dict,
    emitter: RegistryLintEmitter,
) -> None:
    summary_max_lines = system_refactor_policy["raw_registry_summary_max_lines_before_review"]
    shard_max_lines = system_refactor_policy["raw_registry_shard_max_lines_before_review"]

    if paths.raw_registry_entry_pages:
        summary_line_total = line_count(paths.raw_registry_path)
        if summary_line_total > summary_max_lines:
            emitter.review_candidate(
                {
                    "type": "raw_registry_summary_lines_over_threshold",
                    "page": report_path(vault, paths.raw_registry_path),
                    "value": summary_line_total,
                    "threshold": summary_max_lines,
                    "suggested_action": "review_registry_summary_compaction",
                }
            )

        for entry_page in sorted(paths.raw_registry_entry_pages):
            page_key = entry_page.as_posix()
            page_entries = inventory_context.entries_by_page.get(page_key, [])
            if not page_entries:
                continue

            shard_line_total = line_count(entry_page)
            if shard_line_total <= shard_max_lines:
                continue
            family_line_totals: dict[str, int] = defaultdict(int)
            family_entry_totals: dict[str, int] = defaultdict(int)
            for entry in page_entries:
                topic_family = registry_topic_family(entry) or "(unlabeled)"
                family_entry_totals[topic_family] += 1
                line_span = registry_entry_line_span(entry)
                if line_span is not None:
                    family_line_totals[topic_family] += line_span
            top_contributing_families = [
                {
                    "topic_family": topic_family,
                    "entry_count": family_entry_totals[topic_family],
                    "estimated_line_count": family_line_totals.get(topic_family, 0),
                }
                for topic_family in sorted(
                    family_entry_totals,
                    key=lambda item: (-family_line_totals.get(item, 0), -family_entry_totals[item], item),
                )[:3]
            ]
            emitter.review_candidate(
                {
                    "type": "raw_registry_shard_lines_over_threshold",
                    "page": report_path(vault, entry_page),
                    "value": shard_line_total,
                    "threshold": shard_max_lines,
                    "entry_count": len(page_entries),
                    "top_contributing_families": top_contributing_families,
                    "suggested_action": "review_family_router_or_second_order_shard",
                }
            )


def _backlog_over_threshold_rule_trigger(state: dict) -> bool:
    thresholds = state["thresholds"]
    return (
        state["backlog_count"] > thresholds["backlog_count"]
        or state["backlog_ratio"] > thresholds["backlog_ratio"]
    )


def _build_backlog_over_threshold_candidate(state: dict) -> dict:
    thresholds = state["thresholds"]
    backlog_entries = state["backlog_entries"]
    return {
        "type": "raw_registry_shard_backlog_over_threshold",
        "page": state["page"],
        "value": {
            "backlog_count": state["backlog_count"],
            "backlog_ratio": round(state["backlog_ratio"], 3),
        },
        "threshold": {
            "backlog_count": thresholds["backlog_count"],
            "backlog_ratio": thresholds["backlog_ratio"],
        },
        "supporting_registry_ids": [entry.get("registry_id") for entry in backlog_entries],
        "suggested_action": "review_registry_backlog_or_ingest_queue",
    }


def _backlog_pending_age_rule_trigger(state: dict) -> bool:
    oldest_pending_age_days = state["oldest_pending_age_days"]
    average_pending_age_days = state["average_pending_age_days"]
    if oldest_pending_age_days is None or average_pending_age_days is None:
        return False
    thresholds = state["thresholds"]
    return (
        oldest_pending_age_days > thresholds["oldest_pending_age_days"]
        or average_pending_age_days > thresholds["average_pending_age_days"]
    )


def _build_backlog_pending_age_candidate(state: dict) -> dict:
    thresholds = state["thresholds"]
    dated_backlog_entries = state["dated_backlog_entries"]
    backlog_count = state["backlog_count"]
    return {
        "type": "raw_registry_shard_pending_age_over_threshold",
        "page": state["page"],
        "value": {
            "dated_backlog_count": len(dated_backlog_entries),
            "undated_backlog_count": backlog_count - len(dated_backlog_entries),
            "oldest_pending_age_days": state["oldest_pending_age_days"],
            "average_pending_age_days": state["average_pending_age_days"],
        },
        "threshold": {
            "oldest_pending_age_days": thresholds["oldest_pending_age_days"],
            "average_pending_age_days": thresholds["average_pending_age_days"],
        },
        "supporting_registry_ids": [
            entry.get("registry_id")
            for entry, _ in sorted(
                dated_backlog_entries,
                key=lambda item: (-item[1], item[0].get("registry_id", "")),
            )
        ],
        "suggested_action": "review_registry_backlog_age_or_ingest_queue",
    }


BACKLOG_REVIEW_RULE_SPECS = [
    CandidateRuleSpec(
        rule_id="raw_registry_shard_backlog_over_threshold",
        candidate_type="raw_registry_shard_backlog_over_threshold",
        applies=_backlog_over_threshold_rule_trigger,
        build_candidate=_build_backlog_over_threshold_candidate,
    ),
    CandidateRuleSpec(
        rule_id="raw_registry_shard_pending_age_over_threshold",
        candidate_type="raw_registry_shard_pending_age_over_threshold",
        applies=_backlog_pending_age_rule_trigger,
        build_candidate=_build_backlog_pending_age_candidate,
    ),
]


@dataclass(frozen=True)
class _BacklogRefactorThresholds:
    shard_max_entries: int
    topic_family_min_entries: int
    topic_family_min_unique_targets: int
    topic_subfamily_min_entries: int
    backlog_max_count: int
    backlog_max_ratio: float
    backlog_max_oldest_age: int
    backlog_max_average_age: float

    def backlog_rule_thresholds(self) -> dict[str, int | float]:
        return {
            "backlog_count": self.backlog_max_count,
            "backlog_ratio": self.backlog_max_ratio,
            "oldest_pending_age_days": self.backlog_max_oldest_age,
            "average_pending_age_days": self.backlog_max_average_age,
        }


def _backlog_refactor_thresholds(system_refactor_policy: dict) -> _BacklogRefactorThresholds:
    return _BacklogRefactorThresholds(
        shard_max_entries=system_refactor_policy["raw_registry_shard_max_entries_before_review"],
        topic_family_min_entries=system_refactor_policy[
            "raw_registry_topic_family_min_entries_before_review"
        ],
        topic_family_min_unique_targets=system_refactor_policy[
            "raw_registry_topic_family_min_unique_target_pages_before_review"
        ],
        topic_subfamily_min_entries=system_refactor_policy[
            "raw_registry_topic_subfamily_min_entries_before_review"
        ],
        backlog_max_count=system_refactor_policy["raw_registry_backlog_max_count_before_review"],
        backlog_max_ratio=system_refactor_policy["raw_registry_backlog_max_ratio_before_review"],
        backlog_max_oldest_age=system_refactor_policy[
            "raw_registry_backlog_max_oldest_age_days_before_review"
        ],
        backlog_max_average_age=system_refactor_policy[
            "raw_registry_backlog_max_average_age_days_before_review"
        ],
    )


def _backlog_rule_state_for_page(
    vault: Path,
    entry_page: Path,
    page_entries: list[dict],
    *,
    thresholds: _BacklogRefactorThresholds,
    today: dt.date,
) -> dict:
    backlog_entries = [entry for entry in page_entries if entry.get("status") == "registered-not-ingested"]
    backlog_count = len(backlog_entries)
    backlog_ratio = backlog_count / len(page_entries)
    dated_backlog_entries = [
        (entry, age_days)
        for entry in backlog_entries
        if (age_days := _backlog_entry_age_days(entry, today=today)) is not None
    ]
    oldest_pending_age_days = None
    average_pending_age_days = None
    if dated_backlog_entries:
        oldest_pending_age_days = max(age_days for _, age_days in dated_backlog_entries)
        average_pending_age_days = round(
            sum(age_days for _, age_days in dated_backlog_entries) / len(dated_backlog_entries),
            1,
        )
    return {
        "page": report_path(vault, entry_page),
        "page_entries": page_entries,
        "backlog_entries": backlog_entries,
        "backlog_count": backlog_count,
        "backlog_ratio": backlog_ratio,
        "dated_backlog_entries": dated_backlog_entries,
        "oldest_pending_age_days": oldest_pending_age_days,
        "average_pending_age_days": average_pending_age_days,
        "thresholds": thresholds.backlog_rule_thresholds(),
    }


def _emit_unsharded_registry_entry_candidate(
    vault: Path,
    paths: RegistryLintPaths,
    *,
    inventory_context: RegistryInventoryContext,
    thresholds: _BacklogRefactorThresholds,
    emitter: RegistryLintEmitter,
) -> None:
    if inventory_context.total_entry_count <= thresholds.shard_max_entries:
        return
    emitter.review_candidate(
        {
            "type": "raw_registry_entries_over_threshold",
            "page": report_path(vault, paths.raw_registry_path),
            "value": inventory_context.total_entry_count,
            "threshold": thresholds.shard_max_entries,
            "suggested_action": "review_registry_sharding_or_summary_split",
        }
    )


def _emit_backlog_review_candidates_for_page(
    vault: Path,
    entry_page: Path,
    page_entries: list[dict],
    *,
    thresholds: _BacklogRefactorThresholds,
    emitter: RegistryLintEmitter,
    today: dt.date,
) -> None:
    backlog_rule_state = _backlog_rule_state_for_page(
        vault,
        entry_page,
        page_entries,
        thresholds=thresholds,
        today=today,
    )
    for candidate in evaluate_candidate_rules(
        [backlog_rule_state],
        BACKLOG_REVIEW_RULE_SPECS,
    ):
        emitter.review_candidate(candidate)


def _supporting_target_pages(
    entries: list[dict],
    inventory_context: RegistryInventoryContext,
) -> list[str]:
    return [
        target_path
        for target_path in (
            registry_entry_target_report_path(entry, inventory_context.corpus_roots)
            for entry in entries
        )
        if target_path is not None
    ]


def _entries_by_topic_family(page_entries: list[dict]) -> dict[str, list[dict]]:
    family_to_entries: dict[str, list[dict]] = defaultdict(list)
    for entry in page_entries:
        topic_family = registry_topic_family(entry)
        if topic_family is not None:
            family_to_entries[topic_family].append(entry)
    return family_to_entries


def _entries_by_topic_subfamily(family_entries: list[dict]) -> dict[str, list[dict]]:
    subfamily_to_entries: dict[str, list[dict]] = defaultdict(list)
    for entry in family_entries:
        topic_subfamily = registry_topic_subfamily(entry)
        if topic_subfamily is not None:
            subfamily_to_entries[topic_subfamily].append(entry)
    return subfamily_to_entries


def _emit_missing_topic_family_candidate(
    vault: Path,
    entry_page: Path,
    page_entries: list[dict],
    missing_topic_family_entries: list[dict],
    *,
    thresholds: _BacklogRefactorThresholds,
    emitter: RegistryLintEmitter,
) -> None:
    emitter.review_candidate(
        {
            "type": "raw_registry_shard_needs_topic_family",
            "page": report_path(vault, entry_page),
            "value": {
                "entry_count": len(page_entries),
                "missing_topic_family_count": len(missing_topic_family_entries),
            },
            "threshold": thresholds.shard_max_entries,
            "supporting_registry_ids": [
                entry.get("registry_id") for entry in missing_topic_family_entries
            ],
            "suggested_action": "review_add_topic_family_labels",
        }
    )


def _emit_missing_topic_subfamily_candidate(
    vault: Path,
    entry_page: Path,
    topic_family: str,
    family_entries: list[dict],
    unique_target_pages: list[str],
    missing_topic_subfamily_entries: list[dict],
    *,
    thresholds: _BacklogRefactorThresholds,
    emitter: RegistryLintEmitter,
) -> None:
    emitter.review_candidate(
        {
            "type": "raw_registry_topic_family_needs_subfamily",
            "page": report_path(vault, entry_page),
            "topic_family": topic_family,
            "value": {
                "entry_count": len(family_entries),
                "unique_target_page_count": len(unique_target_pages),
                "missing_topic_subfamily_count": len(missing_topic_subfamily_entries),
            },
            "threshold": {
                "entry_count": thresholds.topic_family_min_entries,
                "unique_target_page_count": thresholds.topic_family_min_unique_targets,
            },
            "supporting_pages": unique_target_pages,
            "supporting_registry_ids": [entry.get("registry_id") for entry in family_entries],
            "suggested_action": "review_add_topic_subfamily_labels",
        }
    )


def _emit_topic_subfamily_candidates(
    vault: Path,
    entry_page: Path,
    topic_family: str,
    family_entries: list[dict],
    *,
    inventory_context: RegistryInventoryContext,
    thresholds: _BacklogRefactorThresholds,
    emitter: RegistryLintEmitter,
) -> None:
    for topic_subfamily, subfamily_entries in sorted(
        _entries_by_topic_subfamily(family_entries).items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        if len(subfamily_entries) < thresholds.topic_subfamily_min_entries:
            continue
        subfamily_supporting_pages = _supporting_target_pages(subfamily_entries, inventory_context)
        emitter.review_candidate(
            {
                "type": "raw_registry_topic_subfamily_over_threshold",
                "page": report_path(vault, entry_page),
                "topic_family": topic_family,
                "topic_subfamily": topic_subfamily,
                "value": {
                    "entry_count": len(subfamily_entries),
                    "unique_target_page_count": len(set(subfamily_supporting_pages)),
                },
                "threshold": {
                    "entry_count": thresholds.topic_subfamily_min_entries,
                },
                "supporting_pages": sorted(set(subfamily_supporting_pages)),
                "supporting_registry_ids": [
                    entry.get("registry_id") for entry in subfamily_entries
                ],
                "suggested_action": "review_subfamily_router_or_second_order_shard",
            }
        )


def _emit_topic_family_review_candidates(
    vault: Path,
    entry_page: Path,
    page_entries: list[dict],
    *,
    inventory_context: RegistryInventoryContext,
    thresholds: _BacklogRefactorThresholds,
    emitter: RegistryLintEmitter,
) -> None:
    if len(page_entries) <= thresholds.shard_max_entries:
        return

    missing_topic_family_entries = [
        entry for entry in page_entries if registry_topic_family(entry) is None
    ]
    if missing_topic_family_entries:
        _emit_missing_topic_family_candidate(
            vault,
            entry_page,
            page_entries,
            missing_topic_family_entries,
            thresholds=thresholds,
            emitter=emitter,
        )
        return

    for topic_family, family_entries in sorted(
        _entries_by_topic_family(page_entries).items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        if len(family_entries) < thresholds.topic_family_min_entries:
            continue
        unique_target_pages = sorted(set(_supporting_target_pages(family_entries, inventory_context)))
        if len(unique_target_pages) < thresholds.topic_family_min_unique_targets:
            continue

        missing_topic_subfamily_entries = [
            entry for entry in family_entries if registry_topic_subfamily(entry) is None
        ]
        if missing_topic_subfamily_entries:
            _emit_missing_topic_subfamily_candidate(
                vault,
                entry_page,
                topic_family,
                family_entries,
                unique_target_pages,
                missing_topic_subfamily_entries,
                thresholds=thresholds,
                emitter=emitter,
            )
            continue

        _emit_topic_subfamily_candidates(
            vault,
            entry_page,
            topic_family,
            family_entries,
            inventory_context=inventory_context,
            thresholds=thresholds,
            emitter=emitter,
        )


def _backlog_refactor_threshold_pass(
    vault: Path,
    paths: RegistryLintPaths,
    *,
    inventory_context: RegistryInventoryContext,
    system_refactor_policy: dict,
    emitter: RegistryLintEmitter,
    runtime_context: RuntimeContext | None = None,
) -> None:
    clock_context = runtime_context or RuntimeContext(display_timezone=dt.UTC)
    thresholds = _backlog_refactor_thresholds(system_refactor_policy)
    today = clock_context.today()

    if not paths.raw_registry_entry_pages:
        _emit_unsharded_registry_entry_candidate(
            vault,
            paths,
            inventory_context=inventory_context,
            thresholds=thresholds,
            emitter=emitter,
        )
        return

    for entry_page in sorted(paths.raw_registry_entry_pages):
        page_key = entry_page.as_posix()
        page_entries = inventory_context.entries_by_page.get(page_key, [])
        if not page_entries:
            continue

        _emit_backlog_review_candidates_for_page(
            vault,
            entry_page,
            page_entries,
            thresholds=thresholds,
            emitter=emitter,
            today=today,
        )
        _emit_topic_family_review_candidates(
            vault,
            entry_page,
            page_entries,
            inventory_context=inventory_context,
            thresholds=thresholds,
            emitter=emitter,
        )


summary_shard_review_candidate_pass = _summary_shard_review_candidate_pass
backlog_refactor_threshold_pass = _backlog_refactor_threshold_pass


__all__ = [
    "_backlog_refactor_threshold_pass",
    "_summary_shard_review_candidate_pass",
    "backlog_refactor_threshold_pass",
    "summary_shard_review_candidate_pass",
]
