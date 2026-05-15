from __future__ import annotations

import json
from pathlib import Path

from ops.scripts.filesystem_runtime import AtomicTextUpdate, atomic_multi_write, build_atomic_text_updates
from .finalize_run_errors_runtime import FinalizeRunWriteError


def json_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_finalize_atomic_updates(
    *,
    promotion_path: Path,
    report: dict,
    ledger_path: Path,
    ledger: dict,
    planning_path: Path,
    planning_validation: dict,
    log_path: Path | None,
    final_log_text: str | None,
) -> list[AtomicTextUpdate]:
    update_specs = [
        (promotion_path, json_text(report)),
        (ledger_path, json_text(ledger)),
        (planning_path, json_text(planning_validation)),
    ]
    if final_log_text is not None and log_path is not None:
        update_specs.append((log_path, final_log_text))
    return build_atomic_text_updates(update_specs)


def write_finalize_atomic_updates(updates: list[AtomicTextUpdate]) -> None:
    try:
        atomic_multi_write(updates)
    except OSError as exc:
        raise FinalizeRunWriteError(str(exc)) from exc
