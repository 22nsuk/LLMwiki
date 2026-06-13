from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.core.path_classification_runtime import (
    SOURCE_CONTRACT_CATEGORIES,
    classify_path,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.structural_complexity_budget_runtime import (
    DEFAULT_TARGET_PROFILES,
    build_report as build_structural_complexity_budget_report,
    touched_target_profiles,
)

STRUCTURAL_COMPLEXITY_REPAIR_MARKERS = (
    "structural_complexity",
    "structural-complexity",
    "complexity_non_regression",
    "complexity-non-regression",
    "function_budget",
    "function-budget",
)


def _list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def proposal_declares_structural_complexity_repair(proposal: dict[str, Any]) -> bool:
    fields = [
        proposal.get("proposal_id", ""),
        proposal.get("failure_mode", ""),
        proposal.get("single_mechanism_scope", ""),
        proposal.get("change_hypothesis", ""),
        proposal.get("expected_binary_signal", ""),
        *_list_strings(proposal.get("metrics_triggered")),
    ]
    budget_signal = proposal.get("must_change_budget_signal")
    if isinstance(budget_signal, dict):
        fields.extend(str(value) for value in budget_signal.values())
    text = "\n".join(str(field).lower() for field in fields)
    return any(marker in text for marker in STRUCTURAL_COMPLEXITY_REPAIR_MARKERS)


def structural_complexity_source_targets(paths: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            path
            for path in paths
            if path and classify_path(path) in SOURCE_CONTRACT_CATEGORIES
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
