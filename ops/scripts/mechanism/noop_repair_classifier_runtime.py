from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ops.scripts.core.command_log_summary_runtime import (
    command_log_stream_has_flag,
    command_log_stream_text,
)
from ops.scripts.core.executor_noop_runtime import (
    text_has_executor_noop_mutation_failure,
)

from .auto_improve_next_run_decision_runtime import (
    NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
    NEXT_RUN_FAILURE_REPAIR_FAMILY,
)
from .current_target_path_runtime import current_repo_target_paths

WORKER_STRUCTURAL_PREFLIGHT_FAILURE_MARKER = "worker structural complexity preflight blocked"


def is_next_run_failure_repair_source(decision: Mapping[str, Any]) -> bool:
    if str(decision.get("proposal_family", "")).strip() != NEXT_RUN_FAILURE_REPAIR_FAMILY:
        return False
    source_proposal_id = str(decision.get("proposal_id", "")).strip()
    return source_proposal_id.startswith(f"{NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE}__")


def run_has_noop_mutation_failure(vault: Path, source_run_id: str) -> bool:
    if command_log_stream_has_flag(
        vault,
        source_run_id,
        prefix="mutation-command",
        stream="stderr",
        flag="executor_noop_mutation_failure",
    ):
        return True
    return text_has_executor_noop_mutation_failure(
        command_log_stream_text(
            vault,
            source_run_id,
            prefix="mutation-command",
            stream="stderr",
        )
    )


def run_has_worker_structural_preflight_failure(vault: Path, source_run_id: str) -> bool:
    return WORKER_STRUCTURAL_PREFLIGHT_FAILURE_MARKER in command_log_stream_text(
        vault,
        source_run_id,
        prefix="mutation-command",
        stream="stderr",
    )


def _structural_complexity_targets_pass(vault: Path, targets: object) -> bool:
    target_list = [str(target) for target in targets] if isinstance(targets, list) else []
    primary_targets = current_repo_target_paths(vault, target_list)
    if not primary_targets:
        return False
    try:
        from ops.scripts.eval.structural_complexity_budget_runtime import (
            DEFAULT_TARGET_PROFILES,
            build_report,
            touched_target_profiles,
        )

        report = build_report(
            vault,
            target_profiles=touched_target_profiles(DEFAULT_TARGET_PROFILES, primary_targets),
        )
    except (OSError, TypeError, ValueError):
        return False
    target_statuses = {
        str(target.get("path", "")).strip(): str(target.get("status", "")).strip()
        for target in report.get("targets", [])
        if isinstance(target, dict)
    }
    return all(target_statuses.get(target) == "pass" for target in primary_targets)


def repair_decision_ended_as_noop_mutation_failure(
    vault: Path,
    decision: Mapping[str, Any],
    *,
    queue_unblock_family: str,
) -> bool:
    if str(decision.get("failure_taxonomy", "")).strip() != "mutation_failed":
        return False
    proposal_family = str(decision.get("proposal_family", "")).strip()
    decision_action = str(decision.get("next_run_action", "")).strip()
    decision_kind = str(decision.get("decision", "")).strip()
    if not (
        is_next_run_failure_repair_source(decision)
        or proposal_family == queue_unblock_family
        or decision_action == "repair_failure"
        or decision_kind == "carry_forward"
    ):
        return False
    source_run_id = str(decision.get("source_run_id", "")).strip()
    if not source_run_id:
        return False
    if run_has_noop_mutation_failure(vault, source_run_id):
        return True
    return run_has_worker_structural_preflight_failure(
        vault,
        source_run_id,
    ) and _structural_complexity_targets_pass(vault, decision.get("primary_targets", []))
