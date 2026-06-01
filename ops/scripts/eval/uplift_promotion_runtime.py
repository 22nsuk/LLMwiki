from __future__ import annotations

from typing import Any

TYPE_FLAGS = (
    "check_untyped_defs",
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
)


def _rule_count_from_plan_entry(rule: str, plan: dict[str, Any]) -> int:
    strict_preview = plan.get("strict_preview")
    if isinstance(strict_preview, dict):
        counts = strict_preview.get("rule_counts")
        if isinstance(counts, dict) and rule in counts:
            return int(counts[rule])

    summary = plan.get("summary")
    if isinstance(summary, dict):
        counts = summary.get("rule_counts")
        if isinstance(counts, dict) and rule in counts:
            return int(counts[rule])

    remaining = plan.get("remaining_violations")
    if isinstance(remaining, dict) and rule in remaining:
        return int(remaining[rule])
    return 0


def _rule_count_from_audit(rule: str, audit: dict[str, Any]) -> int:
    ruff = audit.get("ruff")
    if isinstance(ruff, dict):
        counts = ruff.get("rule_counts")
        if isinstance(counts, dict) and rule in counts:
            return int(counts[rule])
        if isinstance(counts, dict):
            return sum(
                int(count)
                for rule_id, count in counts.items()
                if str(rule_id).strip().startswith(rule)
            )
    return 0


def _type_count_from_plan_entry(flag: str, plan: dict[str, Any]) -> int:
    remaining = plan.get("remaining_errors")
    if isinstance(remaining, dict) and flag in remaining:
        return int(remaining[flag])
    return 0


def _type_count_from_audit(flag: str, audit: dict[str, Any]) -> int:
    mypy = audit.get("mypy")
    if not isinstance(mypy, dict):
        return 0
    error_count = int(mypy.get("error_count", 0) or 0)
    if error_count == 0:
        return 0
    return error_count


def lint_promotion_order(lint_uplift_plan: dict[str, Any], audit: dict[str, Any]) -> list[str]:
    rules: set[str] = set()

    strict_preview = lint_uplift_plan.get("strict_preview")
    if isinstance(strict_preview, dict):
        counts = strict_preview.get("rule_counts")
        if isinstance(counts, dict):
            rules.update(str(rule) for rule in counts)

    summary = lint_uplift_plan.get("summary")
    if isinstance(summary, dict):
        counts = summary.get("rule_counts")
        if isinstance(counts, dict):
            rules.update(str(rule) for rule in counts)

    remaining = lint_uplift_plan.get("remaining_violations")
    if isinstance(remaining, dict):
        rules.update(str(rule) for rule in remaining)

    ruff = audit.get("ruff")
    if isinstance(ruff, dict):
        counts = ruff.get("rule_counts")
        if isinstance(counts, dict):
            rules.update(str(rule) for rule in counts)

    return sorted(
        rules,
        key=lambda rule: (
            max(_rule_count_from_plan_entry(rule, lint_uplift_plan), _rule_count_from_audit(rule, audit)),
            rule,
        ),
    )


def type_promotion_order(type_uplift_plan: dict[str, Any], audit: dict[str, Any]) -> list[str]:
    flags: set[str] = set(TYPE_FLAGS)
    remaining = type_uplift_plan.get("remaining_errors")
    if isinstance(remaining, dict):
        flags.update(str(flag) for flag in remaining)
    return sorted(
        flags,
        key=lambda flag: (
            _type_count_from_plan_entry(flag, type_uplift_plan),
            _type_count_from_audit(flag, audit),
            flag,
        ),
    )


def is_promotable(remaining_violations: int) -> bool:
    return int(remaining_violations) == 0
