from __future__ import annotations

from pathlib import Path

from .auto_improve_readiness_constants_runtime import (
    FALLBACK_PRIMARY_TARGETS,
    FALLBACK_SUPPORTING_TARGETS,
    FALLBACK_TEST_FILES,
)
from .current_target_path_runtime import current_repo_target_paths
from .mutation_proposal_candidate_runtime import (
    MutationProposal,
    fixed_priority_breakdown,
    must_not_expand_apply_roots,
    proposal_blast_radius_score,
    proposal_id,
    required_artifacts,
    resolve_must_change_tests,
    with_generated_supporting_targets,
)

BOOTSTRAP_FAILURE_MODE = "bootstrap_history_insufficient"
BOOTSTRAP_SOURCE_CANDIDATE_TYPE = "mechanism_bootstrap_history_candidate"
BOOTSTRAP_FAMILY = "bootstrap_queue_unblock"
BOOTSTRAP_NO_HISTORY_BLOCKER = "no_history"
BOOTSTRAP_NO_HISTORY_RUN_ID = "bootstrap-no-history"


def _bootstrap_priority(group: dict) -> int:
    blocked_types = list(group.get("blocked_candidate_types", []))
    additional_runs_needed = min(
        (
            int(item.get("additional_runs_needed", 0))
            for item in blocked_types
            if int(item.get("additional_runs_needed", 0)) > 0
        ),
        default=1,
    )
    comparable_runs = int(group.get("comparable_runs", 0))
    priority = 70
    if additional_runs_needed <= 1:
        priority += 15
    elif additional_runs_needed == 2:
        priority += 8
    priority += min(comparable_runs, 3) * 2
    priority += min(len(blocked_types), 3)
    return max(0, min(100, priority))


def _bootstrap_blocked_candidate_types(group: dict) -> list[str]:
    blocked_types: list[str] = []
    for item in group.get("blocked_candidate_types", []):
        if not isinstance(item, dict):
            continue
        candidate_type = str(item.get("candidate_type", "")).strip()
        if candidate_type:
            blocked_types.append(candidate_type)
    return blocked_types


def _bootstrap_additional_runs_needed(group: dict) -> int:
    additional_runs = [
        int(item.get("additional_runs_needed", 0))
        for item in group.get("blocked_candidate_types", [])
        if isinstance(item, dict) and int(item.get("additional_runs_needed", 0)) > 0
    ]
    return min(additional_runs, default=1)


def _bootstrap_scope(primary_targets: list[str], additional_runs_needed: int) -> str:
    target_scope = ", ".join(f"`{target}`" for target in primary_targets)
    if additional_runs_needed == 1:
        additional = "one additional"
    else:
        additional = f"{additional_runs_needed} additional"
    return (
        f"keep the next system_mechanism run scoped to {target_scope} and finalize {additional} "
        "comparable run on the same primary target set without expanding apply roots"
    )


def _bootstrap_change_hypothesis(
    primary_targets: list[str],
    blocked_candidate_types: list[str],
    additional_runs_needed: int,
) -> str:
    blocked_summary = (
        ", ".join(blocked_candidate_types) or "trend-based mechanism review candidates"
    )
    if additional_runs_needed == 1:
        run_summary = "one more finalized comparable run"
    else:
        run_summary = f"{additional_runs_needed} more finalized comparable runs"
    return (
        f"If {run_summary} is captured for {', '.join(primary_targets)}, "
        "the current bootstrap gate can open "
        f"and {blocked_summary} will become eligible for mechanism review evaluation."
    )


def _bootstrap_expected_binary_signal(primary_targets: list[str]) -> str:
    targets = ", ".join(primary_targets)
    return (
        "mechanism-review bootstrap diagnostics reduce the additional comparable-run "
        "requirement for "
        f"{targets}, and candidate-backed mutation proposals appear for the same primary target set"
    )


def _bootstrap_why_now(group: dict, latest_run_id: str) -> str:
    comparable_runs = int(group.get("comparable_runs", 0))
    additional_runs_needed = _bootstrap_additional_runs_needed(group)
    blocked_candidate_types = _bootstrap_blocked_candidate_types(group)
    blocked_summary = ", ".join(blocked_candidate_types) or "trend-based candidates"
    return (
        f"같은 primary target set에 이미 {comparable_runs}개의 comparable run이 있고 "
        f"최신 근거는 `{latest_run_id}`다. 여기서 {additional_runs_needed}개만 더 좁게 "
        f"finalize하면 {blocked_summary} 평가 창을 열 수 있어 현재 queue unblock의 최소 경로다."
    )


def _bootstrap_budget_signal() -> dict[str, str]:
    return {
        "signal": "mechanism_review.summary.candidates_emitted",
        "expected_change": "increase",
    }


def _bootstrap_no_history_budget_signal() -> dict[str, str]:
    return {
        "signal": "mechanism_review.summary.runs_considered",
        "expected_change": "increase",
    }


def _bootstrap_group_proposal(
    vault: Path,
    policy: dict,
    group: dict,
) -> MutationProposal | None:
    primary_targets = current_repo_target_paths(
        vault,
        [str(target).strip() for target in group.get("primary_targets", []) if str(target).strip()],
    )
    latest_run_id = str(group.get("latest_run_id", "")).strip()
    if not primary_targets or not latest_run_id:
        return None

    blocked_candidate_types = _bootstrap_blocked_candidate_types(group)
    additional_runs_needed = _bootstrap_additional_runs_needed(group)
    priority = _bootstrap_priority(group)
    priority_breakdown = fixed_priority_breakdown(priority)
    supporting_targets = with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=[],
    )
    pseudo_candidate = {
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "tier": "supporting",
    }
    must_change_tests = resolve_must_change_tests(
        vault,
        policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
    )
    target_stems = "-".join(Path(target).stem for target in primary_targets)
    source_candidate_id = f"bootstrap_queue_unblock__{target_stems}"
    proposal_identifier = proposal_id(
        {
            "primary_targets": primary_targets,
            "candidate_id": source_candidate_id,
        },
        BOOTSTRAP_FAILURE_MODE,
    )
    return MutationProposal(
        proposal_id=proposal_identifier,
        source_candidate_id=source_candidate_id,
        source_candidate_type=BOOTSTRAP_SOURCE_CANDIDATE_TYPE,
        family=BOOTSTRAP_FAMILY,
        tier="supporting",
        priority=priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=[BOOTSTRAP_FAILURE_MODE],
        run_ids=[latest_run_id],
        failure_mode=BOOTSTRAP_FAILURE_MODE,
        single_mechanism_scope=_bootstrap_scope(primary_targets, additional_runs_needed),
        change_hypothesis=_bootstrap_change_hypothesis(
            primary_targets,
            blocked_candidate_types,
            additional_runs_needed,
        ),
        expected_binary_signal=_bootstrap_expected_binary_signal(primary_targets),
        blast_radius_score=proposal_blast_radius_score(
            pseudo_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal=_bootstrap_budget_signal(),
        must_not_expand_apply_roots=must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=required_artifacts(),
        blocked_by=[BOOTSTRAP_FAILURE_MODE],
        why_now=_bootstrap_why_now(group, latest_run_id),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=[],
    )


def bootstrap_proposal_models_from_review(
    vault: Path,
    policy: dict,
    mechanism_review_report: dict,
) -> list[MutationProposal]:
    allowed_failure_modes = set(policy["mutation_proposal"]["allowed_failure_modes"])
    if BOOTSTRAP_FAILURE_MODE not in allowed_failure_modes:
        return []
    if mechanism_review_report.get("candidates"):
        return []
    diagnostics = mechanism_review_report.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return []
    bootstrap = diagnostics.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return []
    bootstrap_status = str(bootstrap.get("status", "")).strip()

    if bootstrap_status == BOOTSTRAP_NO_HISTORY_BLOCKER:
        no_history_proposal = _bootstrap_no_history_proposal(vault, policy)
        return [no_history_proposal] if no_history_proposal is not None else []
    if bootstrap_status != BOOTSTRAP_FAILURE_MODE:
        return []

    models: list[MutationProposal] = []
    for group in bootstrap.get("target_groups_under_min_history", []):
        if not isinstance(group, dict):
            continue
        proposal = _bootstrap_group_proposal(vault, policy, group)
        if proposal is not None:
            models.append(proposal)
    return models


def _bootstrap_no_history_proposal(
    vault: Path,
    policy: dict,
) -> MutationProposal | None:
    primary_targets = list(FALLBACK_PRIMARY_TARGETS)
    supporting_targets = with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=list(FALLBACK_SUPPORTING_TARGETS),
    )
    if not primary_targets:
        return None

    must_change_tests = resolve_must_change_tests(
        vault,
        policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
    )
    if not must_change_tests:
        must_change_tests = [
            path
            for path in FALLBACK_TEST_FILES
            if (vault / path).exists()
        ]

    priority = 92
    priority_breakdown = fixed_priority_breakdown(priority)
    candidate_id = "bootstrap_queue_unblock__fallback-seed"
    pseudo_candidate = {
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "tier": "supporting",
    }
    return MutationProposal(
        proposal_id=proposal_id(
            {
                "primary_targets": primary_targets,
                "candidate_id": candidate_id,
            },
            BOOTSTRAP_FAILURE_MODE,
        ),
        source_candidate_id=candidate_id,
        source_candidate_type=BOOTSTRAP_SOURCE_CANDIDATE_TYPE,
        family=BOOTSTRAP_FAMILY,
        tier="supporting",
        priority=priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=[BOOTSTRAP_FAILURE_MODE],
        run_ids=[BOOTSTRAP_NO_HISTORY_RUN_ID],
        failure_mode=BOOTSTRAP_FAILURE_MODE,
        single_mechanism_scope=(
            "finalize one narrow fallback-family system_mechanism run on "
            "`ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py` "
            "with supporting scope `ops/schemas/run-telemetry.schema.json` and "
            "`tests/test_auto_improve_iteration_runtime.py`"
        ),
        change_hypothesis=(
            "If the fallback target family gets its first finalized comparable "
            "system_mechanism run, "
            "mechanism review can move from no_history to a target-specific bootstrap diagnostic "
            "and the queue can reopen on concrete history."
        ),
        expected_binary_signal=(
            "mechanism review bootstrap status moves off no_history for the fallback target "
            "family and subsequent queue refreshes surface target-specific candidates or "
            "remaining history depth requirements"
        ),
        blast_radius_score=proposal_blast_radius_score(
            pseudo_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal=_bootstrap_no_history_budget_signal(),
        must_not_expand_apply_roots=must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=required_artifacts(),
        blocked_by=[BOOTSTRAP_NO_HISTORY_BLOCKER],
        why_now=(
            "현재 유효한 comparable system_mechanism run이 0건이라 mechanism review가 no_history 상태다. "
            "readiness가 이미 가리키는 fallback target family부터 1건을 좁게 finalized하는 것이 "
            "queue reopen의 가장 작은 시작점이다."
        ),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=[],
    )
