from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ops.scripts.command_log_summary_runtime import (
    command_log_stream_has_flag,
    command_log_stream_text,
)
from ops.scripts.executor_noop_runtime import text_has_executor_noop_mutation_failure

from .auto_improve_next_run_decision_runtime import (
    NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
    NEXT_RUN_FAILURE_REPAIR_FAMILY,
)


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
    return run_has_noop_mutation_failure(vault, source_run_id)
