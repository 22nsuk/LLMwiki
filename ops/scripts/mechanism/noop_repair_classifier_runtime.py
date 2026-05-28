from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

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
    stderr_path = vault / "runs" / source_run_id / "mutation-command.stderr.txt"
    try:
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return text_has_executor_noop_mutation_failure(stderr_text)


def repair_decision_ended_as_noop_mutation_failure(
    vault: Path,
    decision: Mapping[str, Any],
    *,
    queue_unblock_family: str,
) -> bool:
    proposal_family = str(decision.get("proposal_family", "")).strip()
    if not (
        is_next_run_failure_repair_source(decision)
        or proposal_family == queue_unblock_family
    ):
        return False
    if str(decision.get("failure_taxonomy", "")).strip() != "mutation_failed":
        return False
    source_run_id = str(decision.get("source_run_id", "")).strip()
    if not source_run_id:
        return False
    return run_has_noop_mutation_failure(vault, source_run_id)
