from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.release.release_source_ready_commit import classify_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.structural_complexity_budget_runtime import (
    DEFAULT_TARGET_PROFILES,
    touched_target_profiles,
)
from ops.scripts.structural_complexity_budget_runtime import (
    build_report as build_structural_complexity_budget_report,
)


def structural_complexity_source_targets(paths: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            path
            for path in paths
            if path and classify_path(path) != "generated_canonical"
        )
    )


def generated_canonical_targets(paths: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            path
            for path in paths
            if path and classify_path(path) == "generated_canonical"
        )
    )


def source_targets_structural_complexity_report(
    vault: Path,
    target_paths: list[str],
    *,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    source_targets = structural_complexity_source_targets(target_paths)
    return build_structural_complexity_budget_report(
        vault,
        context=context,
        target_profiles=touched_target_profiles(
            DEFAULT_TARGET_PROFILES,
            source_targets,
        ),
    )


def source_targets_within_structural_complexity_budget(
    vault: Path,
    target_paths: list[str],
    *,
    context: RuntimeContext | None = None,
) -> bool:
    source_targets = structural_complexity_source_targets(target_paths)
    if not source_targets:
        return True
    try:
        report = source_targets_structural_complexity_report(
            vault,
            source_targets,
            context=context,
        )
    except (OSError, TypeError, ValueError):
        return False
    return str(report.get("status", "")).strip() == "pass"
