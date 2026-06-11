from __future__ import annotations

import json
from pathlib import Path

from ops.scripts.proposal_scope_runtime import dedupe_preserve_order

from .current_target_path_runtime import current_repo_target_paths
from .mutation_proposal_candidate_runtime import (
    MutationProposal,
    RecentLogOverlapMatch,
    fixed_priority_breakdown,
    must_not_expand_apply_roots,
    proposal_blast_radius_score,
    proposal_id,
    recent_log_overlap_matches,
    required_artifacts,
    resolve_must_change_tests,
    target_slug,
    with_generated_supporting_targets,
)
from .mutation_proposal_loader_runtime import RecentLogSection
from .next_run_repair_queue_runtime import safe_repo_relative_path
from .noop_repair_classifier_runtime import run_has_noop_mutation_failure
from .structural_complexity_scope_runtime import (
    source_targets_within_structural_complexity_budget,
)

RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE = "recent_log_overlap_queue_blocked"
RECENT_LOG_OVERLAP_UNBLOCK_SOURCE_CANDIDATE_TYPE = (
    "mechanism_recent_log_overlap_queue_unblock_candidate"
)
RECENT_LOG_OVERLAP_UNBLOCK_FAMILY = "queue_unblock"
RECENT_LOG_OVERLAP_UNBLOCK_PREFERRED_TARGETS = [
    "ops/scripts/mechanism/mutation_proposal_runtime.py",
    "ops/scripts/mechanism/mechanism_run_validation_runtime.py",
]
RECENT_LOG_OVERLAP_UNBLOCK_RETIRED_TARGETS = frozenset(
    {
        "ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py",
    }
)
RECENT_LOG_OVERLAP_UNBLOCK_TEST_FALLBACKS = {
    "ops/scripts/mechanism/mutation_proposal_runtime.py": [
        "tests/test_mutation_proposal.py",
        "tests/test_report_generation_smoke.py",
    ],
    "ops/scripts/mechanism/mechanism_run_validation_runtime.py": [
        "tests/test_mechanism_run_validation_runtime.py",
    ],
}
RECENT_LOG_OVERLAP_UNBLOCK_RUN_ID = "recent-log-overlap-queue-blocked"
RECENT_OUTCOME_REWORK_BLOCKER = "recent_outcome_rework"
RECENT_OUTCOME_REWORK_MIN_ATTEMPTS = 2
RECENT_LOG_OVERLAP_UNBLOCK_REWORK_MIN_ATTEMPTS = 1
STRUCTURAL_COMPLEXITY_BUDGET_BLOCKER = "structural_complexity_budget"
RESOLVED_PROMOTION_HISTORY_STATUSES = {"archived", "quarantined"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _next_run_decision_source_run_id(source_candidate_id: str) -> str:
    prefix = "next-run-decision:"
    if not source_candidate_id.startswith(prefix):
        return ""
    remainder = source_candidate_id[len(prefix):]
    source_run_id, separator, _decision_suffix = remainder.rpartition(":")
    if not separator:
        return ""
    return source_run_id.strip()


def _promotion_report_history_resolved(
    vault: Path,
    attempt: dict,
) -> bool:
    report_rel_path = safe_repo_relative_path(attempt.get("promotion_report"))
    if report_rel_path is None:
        return False

    try:
        promotion_report = _read_json(vault / report_rel_path)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(promotion_report, dict):
        return False

    attempt_run_id = str(attempt.get("run_id", "")).strip()
    report_run_id = str(promotion_report.get("run_id", "")).strip()
    report_path_run_id = Path(report_rel_path).parent.name
    if attempt_run_id:
        if report_run_id and attempt_run_id not in {report_run_id, report_path_run_id}:
            return False
        if not report_run_id and attempt_run_id != report_path_run_id:
            return False

    history = promotion_report.get("history", {})
    if not isinstance(history, dict):
        return False
    history_status = str(history.get("status", "active")).strip().lower()
    proposal_identifier = str(attempt.get("proposal_id", "")).strip()
    source_run_id = attempt_run_id or report_run_id or report_path_run_id
    if (
        history_status in RESOLVED_PROMOTION_HISTORY_STATUSES
        and proposal_identifier.startswith(f"{RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE}__")
        and run_has_noop_mutation_failure(vault, source_run_id)
    ):
        return False
    return history_status in RESOLVED_PROMOTION_HISTORY_STATUSES


def _recent_unresolved_outcome_attempt_count(
    vault: Path,
    outcome_metrics_report: dict,
    *,
    proposal_id: str,
) -> int:
    recent_attempts = outcome_metrics_report.get("recent_attempts", [])
    if not isinstance(recent_attempts, list):
        return 0

    repaired_source_run_ids: set[str] = set()
    unresolved_count = 0
    for attempt in recent_attempts:
        if not isinstance(attempt, dict):
            continue

        outcome = str(attempt.get("outcome", "")).strip().lower()
        decision = str(attempt.get("decision", "")).strip().upper()
        if outcome == "promoted" or decision == "PROMOTE":
            repaired_source_run_id = _next_run_decision_source_run_id(
                str(attempt.get("source_candidate_id", "")).strip()
            )
            if repaired_source_run_id:
                repaired_source_run_ids.add(repaired_source_run_id)

        if str(attempt.get("proposal_id", "")).strip() != proposal_id:
            continue

        if outcome == "promoted" or decision == "PROMOTE":
            break
        if str(attempt.get("run_id", "")).strip() in repaired_source_run_ids:
            continue
        if _promotion_report_history_resolved(vault, attempt):
            continue
        if outcome or decision:
            unresolved_count += 1
    return unresolved_count


def _recent_outcome_rework_blockers(
    vault: Path,
    outcome_metrics_report: dict,
    *,
    proposal_id: str,
    min_attempts: int = RECENT_OUTCOME_REWORK_MIN_ATTEMPTS,
) -> list[str]:
    unresolved_count = _recent_unresolved_outcome_attempt_count(
        vault,
        outcome_metrics_report,
        proposal_id=proposal_id,
    )
    if unresolved_count < min_attempts:
        return []
    return [RECENT_OUTCOME_REWORK_BLOCKER]


def _fallback_test_files(vault: Path, test_files: list[str]) -> list[str]:
    existing = [path for path in test_files if (vault / path).exists()]
    return existing or list(test_files)


def _recent_log_overlap_unblock_discovery_sort_key(target: str) -> tuple[int, str]:
    stem = Path(target).stem
    if "queue" in stem:
        rank = 0
    elif "proposal" in stem:
        rank = 1
    elif "readiness" in stem:
        rank = 2
    else:
        rank = 3
    return rank, target


def _recent_log_overlap_unblock_primary_target_options(vault: Path) -> list[str]:
    ordered = list(RECENT_LOG_OVERLAP_UNBLOCK_PREFERRED_TARGETS)

    mechanism_dir = vault / "ops" / "scripts" / "mechanism"
    if mechanism_dir.is_dir():
        for path in sorted(
            mechanism_dir.glob("*.py"),
            key=lambda item: _recent_log_overlap_unblock_discovery_sort_key(
                item.relative_to(vault).as_posix()
            ),
        ):
            relative = path.relative_to(vault).as_posix()
            if path.name == "__init__.py" or relative in RECENT_LOG_OVERLAP_UNBLOCK_RETIRED_TARGETS:
                continue
            ordered.append(relative)
    return dedupe_preserve_order(ordered)


def _recent_log_overlap_unblock_target_option(
    vault: Path,
    policy: dict,
    *,
    recent_log_sections: list[RecentLogSection],
    outcome_metrics_report: dict,
) -> tuple[list[str], list[str], list[str], list[RecentLogOverlapMatch], str, list[str]]:
    options: list[
        tuple[list[str], list[str], list[str], list[RecentLogOverlapMatch], str, list[str]]
    ] = []
    for primary_target in _recent_log_overlap_unblock_primary_target_options(vault):
        primary_targets = current_repo_target_paths(
            vault,
            [primary_target],
        )
        if not primary_targets:
            continue
        supporting_targets = with_generated_supporting_targets(
            vault,
            primary_targets=primary_targets,
            supporting_targets=[],
        )
        must_change_tests = resolve_must_change_tests(
            vault,
            policy,
            primary_targets=primary_targets,
            supporting_targets=supporting_targets,
        )
        if not must_change_tests:
            fallback_tests = RECENT_LOG_OVERLAP_UNBLOCK_TEST_FALLBACKS.get(
                primary_targets[0],
                [],
            )
            must_change_tests = _fallback_test_files(
                vault,
                [str(path).strip() for path in fallback_tests if str(path).strip()],
            )
        if not must_change_tests:
            continue
        candidate_id = f"recent_log_overlap_queue_unblock__{target_slug(primary_targets)}"
        pseudo_candidate = {
            "candidate_id": candidate_id,
            "primary_targets": primary_targets,
            "supporting_targets": supporting_targets,
            "tier": "supporting",
        }
        recent_log_matches = recent_log_overlap_matches(
            pseudo_candidate,
            recent_log_sections,
        )
        proposal_identifier = proposal_id(
            {
                "primary_targets": primary_targets,
                "candidate_id": candidate_id,
            },
            RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
        )
        recent_outcome_blockers = _recent_outcome_rework_blockers(
            vault,
            outcome_metrics_report,
            proposal_id=proposal_identifier,
            min_attempts=RECENT_LOG_OVERLAP_UNBLOCK_REWORK_MIN_ATTEMPTS,
        )
        structural_blockers: list[str] = []
        if not source_targets_within_structural_complexity_budget(
            vault,
            [*primary_targets, *supporting_targets],
        ):
            structural_blockers.append(STRUCTURAL_COMPLEXITY_BUDGET_BLOCKER)
        target_blockers = [*structural_blockers, *recent_outcome_blockers]
        options.append(
            (
                primary_targets,
                supporting_targets,
                must_change_tests,
                recent_log_matches,
                candidate_id,
                target_blockers,
            )
        )
        if not recent_log_matches and not target_blockers:
            return options[-1]

    for option_candidate in options:
        if not option_candidate[3] and not option_candidate[5]:
            return option_candidate
    for option_candidate in options:
        if not option_candidate[5]:
            return option_candidate
    for option_candidate in options:
        if not option_candidate[3]:
            return option_candidate
    if options:
        return options[0]
    return ([], [], [], [], "recent_log_overlap_queue_unblock__unresolved", [])


def recent_log_overlap_queue_unblock_proposal(
    vault: Path,
    policy: dict,
    available_proposals: list[MutationProposal],
    *,
    recent_log_sections: list[RecentLogSection],
    outcome_metrics_report: dict,
) -> MutationProposal | None:
    allowed_failure_modes = set(policy["mutation_proposal"]["allowed_failure_modes"])
    if RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE not in allowed_failure_modes:
        return None
    if not available_proposals or any(
        not proposal.blocked_by or proposal.blocked_by != ["recent_log_overlap"]
        for proposal in available_proposals
    ):
        return None

    (
        primary_targets,
        supporting_targets,
        must_change_tests,
        recent_log_matches,
        candidate_id,
        recent_outcome_blockers,
    ) = _recent_log_overlap_unblock_target_option(
        vault,
        policy,
        recent_log_sections=recent_log_sections,
        outcome_metrics_report=outcome_metrics_report,
    )
    if not primary_targets:
        return None

    priority = 91
    priority_breakdown = fixed_priority_breakdown(priority)
    pseudo_candidate = {
        "candidate_id": candidate_id,
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "tier": "supporting",
    }
    proposal_identifier = proposal_id(
        {
            "primary_targets": primary_targets,
            "candidate_id": candidate_id,
        },
        RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
    )
    blocked_by = list(recent_outcome_blockers)
    scoped_target_text = " and ".join(f"`{path}`" for path in primary_targets)
    scoped_test_text = " and ".join(f"`{path}`" for path in must_change_tests)
    return MutationProposal(
        proposal_id=proposal_identifier,
        source_candidate_id=candidate_id,
        source_candidate_type=RECENT_LOG_OVERLAP_UNBLOCK_SOURCE_CANDIDATE_TYPE,
        family=RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
        tier="supporting",
        priority=priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=[RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE],
        run_ids=[RECENT_LOG_OVERLAP_UNBLOCK_RUN_ID],
        failure_mode=RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
        single_mechanism_scope=(
            f"keep the unblock experiment scoped to {scoped_target_text} and "
            f"{scoped_test_text} so all existing recent-log-overlap-blocked proposals remain "
            "diagnostic evidence while one runnable rotation target reopens the queue"
        ),
        change_hypothesis=(
            "If mutation proposal runtime emits a narrow non-overlapping fallback when every candidate "
            "is blocked only by recent_log_overlap, auto-improve readiness can keep a runnable queue "
            "without weakening the chronology overlap guardrail."
        ),
        expected_binary_signal=(
            "mutation proposal diagnostics retain recent_log_overlap blocked candidates and "
            "queue_selection.runnable_available_count becomes greater than zero"
        ),
        blast_radius_score=proposal_blast_radius_score(
            pseudo_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal={
            "signal": "mutation_proposal.queue_selection.runnable_available_count",
            "expected_change": "greater_than_zero",
        },
        must_not_expand_apply_roots=must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=required_artifacts(),
        blocked_by=blocked_by,
        why_now=(
            "현재 후보들이 모두 recent_log_overlap 하나로만 막히면 live queue가 비어 readiness와 learning "
            "execution gate까지 연쇄적으로 닫힌다. guardrail은 보존하고 target rotation proposal만 별도로 열어둔다."
        ),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=recent_log_matches,
    )
