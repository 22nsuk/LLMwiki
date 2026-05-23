#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope  # noqa: PLC0415
    from ops.scripts.artifact_io_runtime import (  # noqa: PLC0415
        ReportWriterKernelRequest,
        write_report_with_kernel,
    )
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.policy_runtime import load_policy, report_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
    from ops.scripts.wiki_lint_review_classification import build_report as build_classification_report  # noqa: PLC0415
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import ReportWriterKernelRequest, write_report_with_kernel
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from .wiki_lint_review_classification import build_report as build_classification_report


DEFAULT_OUT = "ops/reports/function-budget-refactor-proposals.json"
DEFAULT_CLASSIFICATION_PATH = "tmp/wiki-lint-review-classification.json"
PRODUCER = "ops.scripts.function_budget_refactor_proposals"
SCHEMA_PATH = "ops/schemas/function-budget-refactor-proposals.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.function_budget_refactor_proposals --vault ."
SMALL_FUNCTION_LINE_OVERAGE = 40
SMALL_PARAMETER_OVERAGE = 2
SMALL_BRANCH_OVERAGE = 4


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _resolve_optional_repo_path(vault: Path, rel_path: str | None) -> Path | None:
    if not rel_path:
        return None
    path = Path(rel_path)
    resolved = path if path.is_absolute() else vault / path
    return resolved.resolve()


def _classification_report(
    vault: Path,
    *,
    classification_path: str | None,
    context: RuntimeContext,
) -> tuple[dict[str, Any], str]:
    resolved = _resolve_optional_repo_path(vault, classification_path)
    if resolved is not None and resolved.is_file():
        return _load_json(resolved), report_path(vault, resolved)
    return build_classification_report(vault, context=context), "fresh_wiki_lint_review_classification"


def _int_metric(metrics: dict[str, Any], key: str) -> int:
    try:
        return int(metrics.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _metrics(row: dict[str, Any], key: str) -> dict[str, int]:
    raw = row.get(key)
    if not isinstance(raw, dict):
        return {
            "function_lines": 0,
            "parameter_count": 0,
            "branch_node_count": 0,
        }
    return {
        "function_lines": _int_metric(raw, "function_lines"),
        "parameter_count": _int_metric(raw, "parameter_count"),
        "branch_node_count": _int_metric(raw, "branch_node_count"),
    }


def _overages(metrics: dict[str, int], thresholds: dict[str, int]) -> dict[str, int]:
    return {
        key: max(0, int(metrics.get(key, 0)) - int(thresholds.get(key, 0)))
        for key in ("function_lines", "parameter_count", "branch_node_count")
    }


def _owner_surface(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"ops", "tests", "tools"}:
        return "/".join(parts[:2])
    return parts[0] if parts else "unknown"


def _direct_test_path(page: str) -> str:
    path = Path(page)
    if path.parts[:2] == ("ops", "scripts"):
        return f"tests/test_{path.stem.removesuffix('_runtime')}.py"
    if path.parts and path.parts[0] == "tests":
        return page
    return ""


def _has_direct_test(vault: Path, page: str) -> bool:
    direct = _direct_test_path(page)
    return bool(direct and (vault / direct).is_file())


def _has_doc_reference(vault: Path, page: str) -> bool:
    doc_paths = [
        "README.md",
        "ops/README.md",
        *(
            path.relative_to(vault).as_posix()
            for path in sorted((vault / "docs").glob("*.md"))
            if path.is_file()
        ),
    ]
    for rel_path in doc_paths:
        path = vault / rel_path
        if path.is_file() and page in path.read_text(encoding="utf-8"):
            return True
    return False


def _scope_class(vault: Path, page: str, symbol: str) -> str:
    symbol_name = symbol.rsplit(".", 1)[-1]
    if symbol_name == "main" and not _has_direct_test(vault, page) and not _has_doc_reference(vault, page):
        return "large_main_without_tests_or_docs"
    if page.startswith("ops/scripts/") and page.endswith("_runtime.py"):
        return "shared_runtime_helper"
    if page.startswith("ops/scripts/"):
        return "script_or_report_helper"
    if page.startswith("tests/"):
        return "test_helper"
    return "other_python"


def _risk_tier(scope_class: str, overages: dict[str, int], triggered_budgets: list[str]) -> str:
    if scope_class == "large_main_without_tests_or_docs":
        return "high"
    if scope_class == "shared_runtime_helper" and (
        overages["function_lines"] > SMALL_FUNCTION_LINE_OVERAGE
        or overages["branch_node_count"] > SMALL_BRANCH_OVERAGE
        or "branch_node_count" in triggered_budgets
    ):
        return "high"
    if scope_class == "shared_runtime_helper":
        return "medium"
    if overages["function_lines"] > SMALL_FUNCTION_LINE_OVERAGE:
        return "medium"
    return "low"


def _proposal_blockers(
    *,
    scope_class: str,
    risk_tier: str,
    overages: dict[str, int],
    triggered_budgets: list[str],
) -> list[str]:
    blockers: list[str] = []
    if scope_class == "large_main_without_tests_or_docs":
        blockers.append("needs_direct_test_or_doc_before_refactor")
    if risk_tier == "high":
        blockers.append("high_risk_shared_or_large_function")
    if len(triggered_budgets) > 1:
        blockers.append("multiple_budget_axes_triggered")
    if overages["function_lines"] > SMALL_FUNCTION_LINE_OVERAGE:
        blockers.append("function_line_overage_too_large_for_small_adapter")
    if overages["parameter_count"] > SMALL_PARAMETER_OVERAGE:
        blockers.append("parameter_overage_too_large_for_small_adapter")
    if overages["branch_node_count"] > SMALL_BRANCH_OVERAGE:
        blockers.append("branch_overage_too_large_for_small_adapter")
    return sorted(set(blockers))


def _proposal_action(scope_class: str, triggered_budgets: list[str]) -> str:
    if "parameter_count" in triggered_budgets:
        return "introduce_request_or_context_object"
    if scope_class == "test_helper":
        return "split_fixture_or_assertion_helper"
    if scope_class == "shared_runtime_helper":
        return "extract_private_runtime_helper"
    return "extract_private_local_helper"


def _proposal_id(page: str, symbol: str, line: int) -> str:
    raw = f"{page}:{symbol}:{line}".lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return f"function-budget-{slug[:120]}"


def _candidate_from_row(vault: Path, row: dict[str, Any]) -> dict[str, Any]:
    page = str(row.get("page", "")).strip()
    symbol = str(row.get("symbol", "")).strip()
    line = int(row.get("line", 0) or 0)
    metrics = _metrics(row, "metrics")
    thresholds = _metrics(row, "thresholds")
    overages = _overages(metrics, thresholds)
    raw_triggered = row.get("triggered_budgets", [])
    triggered_budgets = [
        str(item).strip()
        for item in (raw_triggered if isinstance(raw_triggered, list) else [])
        if str(item).strip()
    ]
    scope_class = _scope_class(vault, page, symbol)
    risk_tier = _risk_tier(scope_class, overages, triggered_budgets)
    blockers = _proposal_blockers(
        scope_class=scope_class,
        risk_tier=risk_tier,
        overages=overages,
        triggered_budgets=triggered_budgets,
    )
    return {
        "page": page,
        "symbol": symbol,
        "line": line,
        "profile": str(row.get("profile", "")).strip(),
        "owner_surface": _owner_surface(page),
        "scope_class": scope_class,
        "risk_tier": risk_tier,
        "triggered_budgets": triggered_budgets,
        "metrics": metrics,
        "thresholds": thresholds,
        "overages": overages,
        "direct_test_path": _direct_test_path(page),
        "has_direct_test": _has_direct_test(vault, page),
        "has_doc_reference": _has_doc_reference(vault, page),
        "proposal_eligible": not blockers,
        "proposal_blockers": blockers,
    }


def _proposal_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": _proposal_id(
            str(candidate["page"]),
            str(candidate["symbol"]),
            int(candidate["line"]),
        ),
        "page": candidate["page"],
        "symbol": candidate["symbol"],
        "line": candidate["line"],
        "owner_surface": candidate["owner_surface"],
        "scope_class": candidate["scope_class"],
        "recommended_action": _proposal_action(
            str(candidate["scope_class"]),
            list(candidate["triggered_budgets"]),
        ),
        "bounded_scope": "single_function_adapter",
        "suggested_tests": [
            str(candidate["direct_test_path"])
            if candidate["direct_test_path"]
            else "add focused regression test before refactor"
        ],
        "why_small": "single budget axis within adapter overage limits",
    }


def _owner_groups(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[(str(candidate["owner_surface"]), str(candidate["scope_class"]))].append(candidate)
    rows = []
    for (owner_surface, scope_class), items in sorted(grouped.items()):
        risk_counts = Counter(str(item["risk_tier"]) for item in items)
        rows.append(
            {
                "owner_surface": owner_surface,
                "scope_class": scope_class,
                "candidate_count": len(items),
                "proposal_count": sum(1 for item in items if item["proposal_eligible"]),
                "high_risk_count": int(risk_counts.get("high", 0)),
                "medium_risk_count": int(risk_counts.get("medium", 0)),
                "low_risk_count": int(risk_counts.get("low", 0)),
            }
        )
    return rows


def _backlog_theme(candidate: dict[str, Any]) -> str:
    page = str(candidate["page"])
    symbol = str(candidate["symbol"])
    if page == "ops/scripts/external_report_reference_manifest.py" and symbol == "build_report":
        return "external_report_reference_manifest_request_object"
    if page.startswith("ops/scripts/") and (
        "learning_" in page or "release_" in page
    ):
        return "learning_release_report_builders"
    if page.startswith("ops/scripts/") and (
        "mechanism_run" in page or str(candidate["scope_class"]) == "shared_runtime_helper"
    ):
        return "mechanism_run_request_helpers"
    if page.startswith("tests/"):
        return "test_helper_design_backlog"
    return "owner_design_backlog"


def _backlog_priority(theme: str, items: list[dict[str, Any]]) -> str:
    if theme in {
        "learning_release_report_builders",
        "external_report_reference_manifest_request_object",
    }:
        return "P0"
    if theme == "mechanism_run_request_helpers":
        return "P1"
    if any(str(item["risk_tier"]) == "high" for item in items):
        return "P1"
    return "P2"


def _backlog_strategy(theme: str) -> tuple[str, str]:
    strategies = {
        "learning_release_report_builders": (
            "stabilize_report_assembly_steps_before_helper_split",
            "Pin direct report tests, then name assembly phases so evidence-policy decisions stay reviewable.",
        ),
        "external_report_reference_manifest_request_object": (
            "introduce_request_object_for_parameter_budget",
            "Cover direct manifest behavior first, then move ZIP/report inputs into one request object.",
        ),
        "mechanism_run_request_helpers": (
            "apply_request_object_pattern_incrementally",
            "Pick one mechanism-run helper surface at a time and preserve existing routing contracts.",
        ),
        "test_helper_design_backlog": (
            "split_fixture_or_assertion_helpers_when_tests_change",
            "Avoid churn-only test refactors; split helpers alongside the next behavior change.",
        ),
        "owner_design_backlog": (
            "owner_review_required_before_refactor",
            "Treat this as design backlog, not an automatic refactor proposal.",
        ),
    }
    return strategies.get(theme, strategies["owner_design_backlog"])


def _owner_backlog(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if candidate["proposal_eligible"]:
            continue
        theme = _backlog_theme(candidate)
        grouped[
            (
                str(candidate["owner_surface"]),
                str(candidate["scope_class"]),
                theme,
            )
        ].append(candidate)

    rows: list[dict[str, Any]] = []
    for (owner_surface, scope_class, theme), items in sorted(grouped.items()):
        risk_counts = Counter(str(item["risk_tier"]) for item in items)
        blockers = Counter(
            blocker
            for item in items
            for blocker in list(item["proposal_blockers"])
        )
        recommended_strategy, next_owner_action = _backlog_strategy(theme)
        rows.append(
            {
                "backlog_id": _proposal_id(owner_surface, theme, len(items)),
                "owner_surface": owner_surface,
                "scope_class": scope_class,
                "backlog_theme": theme,
                "priority": _backlog_priority(theme, items),
                "candidate_count": len(items),
                "high_risk_count": int(risk_counts.get("high", 0)),
                "medium_risk_count": int(risk_counts.get("medium", 0)),
                "low_risk_count": int(risk_counts.get("low", 0)),
                "dominant_blockers": [
                    blocker for blocker, _count in blockers.most_common(5)
                ],
                "candidate_symbols": [
                    f"{item['page']}::{item['symbol']}:{item['line']}"
                    for item in sorted(
                        items,
                        key=lambda item: (
                            str(item["page"]),
                            int(item["line"]),
                            str(item["symbol"]),
                        ),
                    )[:10]
                ],
                "recommended_strategy": recommended_strategy,
                "next_owner_action": next_owner_action,
            }
        )
    return sorted(rows, key=lambda item: (item["priority"], item["owner_surface"], item["backlog_theme"]))


def build_report(
    vault: Path,
    *,
    classification_path: str | None = DEFAULT_CLASSIFICATION_PATH,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    classification, classification_source = _classification_report(
        resolved_vault,
        classification_path=classification_path,
        context=runtime_context,
    )
    rows = [
        item
        for item in classification.get("classifications", [])
        if isinstance(item, dict) and item.get("primary_bucket") == "function_budget"
    ]
    candidates = [_candidate_from_row(resolved_vault, row) for row in rows]
    proposals = [
        _proposal_from_candidate(candidate)
        for candidate in candidates
        if candidate["proposal_eligible"]
    ]
    scope_counts = Counter(str(candidate["scope_class"]) for candidate in candidates)
    owner_backlog = _owner_backlog(candidates)
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="function_budget_refactor_proposals",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/function_budget_refactor_proposals.py",
                "ops/scripts/wiki_lint_review_classification.py",
                "ops/scripts/python_function_budget_runtime.py",
            ],
            file_inputs={"classification_report": classification_source}
            if classification_source != "fresh_wiki_lint_review_classification"
            else None,
            text_inputs={
                "classification_source": classification_source,
                "small_adapter_limits": json.dumps(
                    {
                        "function_lines": SMALL_FUNCTION_LINE_OVERAGE,
                        "parameter_count": SMALL_PARAMETER_OVERAGE,
                        "branch_node_count": SMALL_BRANCH_OVERAGE,
                    },
                    sort_keys=True,
                ),
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "status": "pass",
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "classification_report": {
            "source": classification_source,
            "status": str(classification.get("status", "")).strip(),
            "function_budget_count": int(
                classification.get("summary", {}).get("function_budget_count", len(rows))
            ),
        },
        "summary": {
            "function_budget_candidate_count": len(candidates),
            "owner_group_count": len(_owner_groups(candidates)),
            "owner_backlog_count": len(owner_backlog),
            "proposal_count": len(proposals),
            "large_main_without_tests_or_docs_count": int(
                scope_counts.get("large_main_without_tests_or_docs", 0)
            ),
            "shared_runtime_helper_count": int(scope_counts.get("shared_runtime_helper", 0)),
            "non_proposal_candidate_count": sum(
                1 for candidate in candidates if not candidate["proposal_eligible"]
            ),
        },
        "owner_groups": _owner_groups(candidates),
        "owner_backlog": owner_backlog,
        "candidates": candidates,
        "proposals": proposals,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_report_with_kernel(
        ReportWriterKernelRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            artifact_kind="function_budget_refactor_proposals",
            producer=PRODUCER,
            context="function budget refactor proposal schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert function-budget review candidates into bounded refactor proposals.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--classification", default=DEFAULT_CLASSIFICATION_PATH)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        classification_path=args.classification,
        policy_path=args.policy_path,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
