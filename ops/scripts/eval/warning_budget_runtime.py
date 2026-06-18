from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import WARNING_BUDGET_REPORT_SCHEMA_PATH
from ops.scripts.core.schema_runtime import load_schema, validate_or_raise
from ops.scripts.registry.raw_registry_preflight import preflight

from .wiki_lint import lint
from .wiki_snapshot_runtime import WikiRuntimeSnapshot

WARNING_BUDGET_REPORT_SCHEMA = WARNING_BUDGET_REPORT_SCHEMA_PATH


def warning_type_counts(report: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    warnings = report.get("warnings", [])
    if not isinstance(warnings, list):
        return {}
    for issue in warnings:
        issue_type = ""
        if isinstance(issue, dict):
            issue_type = str(issue.get("type") or "")
        counts[issue_type or "unknown"] += 1
    return dict(sorted(counts.items()))


def warning_source_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "warning_count": 0,
            "warning_type_counts": {},
        }
    warnings = report.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    return {
        "status": str(report.get("status", "unknown")),
        "warning_count": len(warnings),
        "warning_type_counts": warning_type_counts(report),
    }


def _profile(policy: dict[str, Any], profile_name: str | None) -> tuple[str, dict[str, Any]]:
    budget_policy = policy["strict_warning_budget"]
    resolved_profile_name = profile_name or budget_policy["default_profile"]
    profiles = budget_policy["profiles"]
    if resolved_profile_name not in profiles:
        raise ValueError(f"unknown strict warning budget profile: {resolved_profile_name}")
    return resolved_profile_name, profiles[resolved_profile_name]


def _budget_check(
    *,
    source: str,
    metric: str,
    actual: int,
    budget: int,
    warning_type: str | None = None,
) -> dict[str, Any]:
    check_id = f"{source}.{metric}"
    check: dict[str, Any] = {
        "id": check_id,
        "source": source,
        "metric": metric,
        "actual": actual,
        "budget": budget,
        "status": "pass" if actual <= budget else "fail",
    }
    if warning_type is not None:
        check["id"] = f"{source}.{warning_type}"
        check["warning_type"] = warning_type
    return check


def evaluate_warning_budget(
    policy: dict[str, Any],
    source_reports: dict[str, dict[str, Any]],
    *,
    profile_name: str | None = None,
) -> dict[str, Any]:
    resolved_profile_name, profile = _profile(policy, profile_name)
    sources: dict[str, dict[str, Any]] = {}
    checks: list[dict[str, Any]] = []

    for source_name, source_policy in profile["sources"].items():
        summary = warning_source_summary(source_reports.get(source_name))
        sources[source_name] = summary

        if "max_total_warnings" in source_policy:
            checks.append(
                _budget_check(
                    source=source_name,
                    metric="total_warnings",
                    actual=summary["warning_count"],
                    budget=source_policy["max_total_warnings"],
                )
            )
        for warning_type, budget in source_policy["warning_type_budgets"].items():
            checks.append(
                _budget_check(
                    source=source_name,
                    metric="warning_type",
                    warning_type=warning_type,
                    actual=summary["warning_type_counts"].get(warning_type, 0),
                    budget=budget,
                )
            )

    source_fail_count = sum(1 for source in sources.values() if source["status"] in {"fail", "missing"})
    failed_check_count = sum(1 for check in checks if check["status"] == "fail")
    status = "fail" if source_fail_count or failed_check_count else "pass"
    return {
        "profile": resolved_profile_name,
        "status": status,
        "sources": sources,
        "checks": checks,
        "summary": {
            "source_count": len(sources),
            "source_fail_count": source_fail_count,
            "check_count": len(checks),
            "failed_check_count": failed_check_count,
        },
    }


def collect_warning_source_reports(
    vault: Path,
    policy_path: str | None = None,
    *,
    context: RuntimeContext | None = None,
    snapshot: WikiRuntimeSnapshot | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "raw_registry_preflight": preflight(vault, policy_path, context=context),
        "wiki_lint": lint(vault, policy_path, snapshot=snapshot, context=context),
    }


def build_report(
    vault: Path,
    policy_path: str | None = None,
    *,
    profile_name: str | None = None,
    context: RuntimeContext | None = None,
    source_reports: dict[str, dict[str, Any]] | None = None,
    snapshot: WikiRuntimeSnapshot | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    reports = (
        source_reports
        if source_reports is not None
        else collect_warning_source_reports(
            vault,
            policy_path,
            context=runtime_context,
            snapshot=snapshot,
        )
    )
    evaluation = evaluate_warning_budget(policy, reports, profile_name=profile_name)
    report = {
        "$schema": WARNING_BUDGET_REPORT_SCHEMA,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        **evaluation,
    }
    schema = load_schema(vault / WARNING_BUDGET_REPORT_SCHEMA)
    validate_or_raise(report, schema, context="warning budget report schema validation failed")
    return report
