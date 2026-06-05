#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.wiki_lint import lint
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext

    from .wiki_lint import lint


DEFAULT_OUT = "tmp/wiki-lint-review-classification.json"
PRODUCER = "ops.scripts.wiki_lint_review_classification"
SCHEMA_PATH = "ops/schemas/wiki-lint-review-classification.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.wiki_lint_review_classification"
FUNCTION_BUDGET_TYPES = {"python_function_budget_candidate"}
DOCUMENTATION_CANDIDATE_TYPES = {
    "wiki_synthesis_multi_question_watch_candidate",
    "page_lines_over_threshold",
    "raw_registry_shard_lines_over_threshold",
    "index_lines_over_threshold",
}


def _numeric_overage(candidate: dict[str, Any]) -> int:
    try:
        value = int(candidate.get("value", 0) or 0)
        threshold = int(candidate.get("threshold", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value - threshold)


def _schema_scalar(value: Any) -> int | float | str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float, str)):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _budget_metrics(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {
            "function_lines": 0,
            "parameter_count": 0,
            "branch_node_count": 0,
        }
    result: dict[str, int] = {}
    for key in ("function_lines", "parameter_count", "branch_node_count"):
        try:
            result[key] = int(value.get(key, 0) or 0)
        except (TypeError, ValueError):
            result[key] = 0
    return result


def classify_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_type = str(candidate.get("type", "")).strip()
    page = str(candidate.get("page", "")).strip()
    overage = _numeric_overage(candidate)
    raw_triggered_budgets = candidate.get("triggered_budgets", [])
    triggered_budgets = raw_triggered_budgets if isinstance(raw_triggered_budgets, list) else []
    if candidate_type in FUNCTION_BUDGET_TYPES:
        primary_bucket = "function_budget"
        refactor_candidate = overage >= 10
        rationale = "python function budget candidate; inspect complexity before changing behavior"
    elif candidate_type in DOCUMENTATION_CANDIDATE_TYPES:
        primary_bucket = "documentation_candidate"
        refactor_candidate = False
        rationale = "documentation shape or watch candidate; resolve with compaction or scope notes"
    else:
        primary_bucket = "true_refactor_target"
        refactor_candidate = True
        rationale = "candidate type implies source or corpus structure needs a targeted refactor"
    return {
        "type": candidate_type,
        "page": page,
        "symbol": str(candidate.get("symbol", "")).strip(),
        "line": int(candidate.get("line", 0) or 0),
        "profile": str(candidate.get("profile", "")).strip(),
        "triggered_budgets": [
            str(item).strip()
            for item in triggered_budgets
            if str(item).strip()
        ],
        "primary_bucket": primary_bucket,
        "refactor_candidate": refactor_candidate,
        "value": _schema_scalar(candidate.get("value", 0)),
        "threshold": _schema_scalar(candidate.get("threshold", 0)),
        "metrics": _budget_metrics(candidate.get("value")),
        "thresholds": _budget_metrics(candidate.get("threshold")),
        "overage": overage,
        "suggested_action": str(candidate.get("suggested_action", "")).strip(),
        "rationale": rationale,
    }


def classify_review_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [classify_candidate(candidate) for candidate in candidates if isinstance(candidate, dict)]


def _load_lint_report(vault: Path, lint_report_path: str | None) -> tuple[dict[str, Any], str]:
    if lint_report_path:
        path = Path(lint_report_path)
        if not path.is_absolute():
            path = vault / path
        return json.loads(path.read_text(encoding="utf-8")), report_path(vault, path.resolve())
    report = lint(vault)
    return report, "fresh_lint_runtime"


def build_report(
    vault: Path,
    *,
    lint_report_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    lint_report, lint_source = _load_lint_report(vault, lint_report_path)
    candidates = lint_report.get("review_candidates")
    if not isinstance(candidates, list):
        candidates = []
    rows = classify_review_candidates(candidates)
    bucket_counts = Counter(row["primary_bucket"] for row in rows)
    type_counts = Counter(row["type"] for row in rows)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="wiki_lint_review_classification",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/wiki_lint_review_classification.py"],
            file_inputs={"lint_report": lint_report_path} if lint_report_path else None,
            text_inputs={"lint_source": lint_source},
        ),
        "vault": report_path(vault, vault),
        "status": "pass",
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "lint_report": {
            "source": lint_source,
            "status": str(lint_report.get("status", "")).strip(),
            "review_candidate_count": len(candidates),
        },
        "summary": {
            "review_candidate_count": len(rows),
            "function_budget_count": int(bucket_counts.get("function_budget", 0)),
            "documentation_candidate_count": int(
                bucket_counts.get("documentation_candidate", 0)
            ),
            "true_refactor_target_count": int(
                bucket_counts.get("true_refactor_target", 0)
            ),
            "refactor_candidate_count": sum(1 for row in rows if row["refactor_candidate"]),
        },
        "type_counts": dict(sorted(type_counts.items())),
        "classifications": rows,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="wiki lint review classification schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify wiki_lint review candidates into maintenance buckets.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--lint-report")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, lint_report_path=args.lint_report)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
