#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_mtime_runtime import parse_generated_at
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_repo_artifact_path,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        RELEASE_RISK_TAXONOMY_MATRIX_SCHEMA_PATH,
    )
    from ops.scripts.release.release_risk_taxonomy_runtime import (
        ADVISORY_REVIEW_BACKLOG,
        CLEAN_LANE_BLOCKS,
        CONDITIONAL_OPERATOR_REVIEW,
        LEARNING_BLOCKS_CLAIM,
        RELEASE_RISK_TAXONOMY_PATH,
        load_release_risk_taxonomy,
    )
else:
    from ops.scripts.core.artifact_freshness_mtime_runtime import parse_generated_at
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_repo_artifact_path,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        RELEASE_RISK_TAXONOMY_MATRIX_SCHEMA_PATH,
    )

    from .release_risk_taxonomy_runtime import (
        ADVISORY_REVIEW_BACKLOG,
        CLEAN_LANE_BLOCKS,
        CONDITIONAL_OPERATOR_REVIEW,
        LEARNING_BLOCKS_CLAIM,
        RELEASE_RISK_TAXONOMY_PATH,
        load_release_risk_taxonomy,
    )


DEFAULT_OUT = "ops/reports/release-risk-taxonomy-matrix.json"
DEFAULT_MARKDOWN_OUT = "ops/reports/release-risk-taxonomy-matrix.md"
PRODUCER = "ops.scripts.release_risk_taxonomy_matrix"
SOURCE_COMMAND = (
    "python -m ops.scripts.release_risk_taxonomy_matrix --vault . "
    "--out ops/reports/release-risk-taxonomy-matrix.json "
    "--markdown-out ops/reports/release-risk-taxonomy-matrix.md"
)


def _primary_lane(effects: dict[str, str]) -> str:
    if effects["clean_lane_effect"] == CLEAN_LANE_BLOCKS:
        return "clean_lane_blocker"
    if effects["learning_lane_effect"] == LEARNING_BLOCKS_CLAIM:
        return "learning_claim_blocker"
    if effects["advisory_lifecycle_effect"] == ADVISORY_REVIEW_BACKLOG:
        return "advisory_lifecycle_backlog"
    if effects["conditional_lane_effect"] == CONDITIONAL_OPERATOR_REVIEW:
        return "conditional_operator_review"
    return "non_blocking"


def _matrix_rows(taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    risks = taxonomy.get("risks")
    if not isinstance(risks, dict):
        return []
    rows: list[dict[str, Any]] = []
    for code in sorted(str(item) for item in risks):
        entry = risks.get(code)
        if not isinstance(entry, dict):
            continue
        effects = entry.get("effects")
        if not isinstance(effects, dict):
            effects = {}
        normalized_effects = {
            "clean_lane_effect": str(effects.get("clean_lane_effect", "")).strip(),
            "conditional_lane_effect": str(effects.get("conditional_lane_effect", "")).strip(),
            "learning_lane_effect": str(effects.get("learning_lane_effect", "")).strip(),
            "advisory_lifecycle_effect": str(effects.get("advisory_lifecycle_effect", "")).strip(),
        }
        rows.append(
            {
                "code": code,
                "surface": str(entry.get("surface", "")).strip(),
                "description": str(entry.get("description", "")).strip(),
                **normalized_effects,
                "primary_lane": _primary_lane(normalized_effects),
                "clean_lane_blocks": normalized_effects["clean_lane_effect"] == CLEAN_LANE_BLOCKS,
                "conditional_operator_review_required": (
                    normalized_effects["conditional_lane_effect"] == CONDITIONAL_OPERATOR_REVIEW
                ),
                "learning_claim_blocks": normalized_effects["learning_lane_effect"] == LEARNING_BLOCKS_CLAIM,
                "advisory_lifecycle_backlog": (
                    normalized_effects["advisory_lifecycle_effect"] == ADVISORY_REVIEW_BACKLOG
                ),
            }
        )
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "risk_code_count": len(rows),
        "clean_lane_blocking_count": sum(1 for row in rows if row["clean_lane_blocks"]),
        "clean_lane_non_blocking_count": sum(1 for row in rows if not row["clean_lane_blocks"]),
        "conditional_operator_review_count": sum(
            1 for row in rows if row["conditional_operator_review_required"]
        ),
        "learning_claim_blocking_count": sum(1 for row in rows if row["learning_claim_blocks"]),
        "advisory_lifecycle_backlog_count": sum(1 for row in rows if row["advisory_lifecycle_backlog"]),
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    taxonomy = load_release_risk_taxonomy(vault)
    rows = _matrix_rows(taxonomy)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_risk_taxonomy_matrix",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=RELEASE_RISK_TAXONOMY_MATRIX_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/release_risk_taxonomy_matrix.py",
                RELEASE_RISK_TAXONOMY_PATH,
            ],
            file_inputs={"release_risk_taxonomy": RELEASE_RISK_TAXONOMY_PATH},
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": "pass",
        "taxonomy": {
            "path": RELEASE_RISK_TAXONOMY_PATH,
            "version": int(taxonomy.get("version", 0) or 0),
            "description": str(taxonomy.get("description", "")).strip(),
        },
        "summary": _summary(rows),
        "matrix": rows,
    }


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    taxonomy = report.get("taxonomy", {})
    lines = [
        "# Release Risk Taxonomy Matrix",
        "",
        f"- Generated at: {report.get('generated_at', '')}",
        f"- Taxonomy: {taxonomy.get('path', RELEASE_RISK_TAXONOMY_PATH)}",
        f"- Taxonomy version: {taxonomy.get('version', '')}",
        f"- Risk codes: {summary.get('risk_code_count', 0)}",
        f"- Clean-lane blockers: {summary.get('clean_lane_blocking_count', 0)}",
        f"- Learning-claim blockers: {summary.get('learning_claim_blocking_count', 0)}",
        f"- Advisory lifecycle backlog: {summary.get('advisory_lifecycle_backlog_count', 0)}",
        "",
        "| Risk code | Primary lane | Clean | Conditional | Learning | Advisory | Surface |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("matrix", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(row.get("code", "")),
                    _markdown_cell(row.get("primary_lane", "")),
                    _markdown_cell(row.get("clean_lane_effect", "")),
                    _markdown_cell(row.get("conditional_lane_effect", "")),
                    _markdown_cell(row.get("learning_lane_effect", "")),
                    _markdown_cell(row.get("advisory_lifecycle_effect", "")),
                    _markdown_cell(row.get("surface", "")),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _set_mtime(path: Path, generated_at: str) -> None:
    generated_dt = parse_generated_at(generated_at)
    if generated_dt is None:
        return
    timestamp = generated_dt.timestamp()
    os.utime(path, (timestamp, timestamp))


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    destination = write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_RISK_TAXONOMY_MATRIX_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release risk taxonomy matrix schema validation failed",
        )
    )
    _set_mtime(destination, str(report.get("generated_at", "")))
    return destination


def write_markdown(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    destination = resolve_repo_artifact_path(vault, out_path, default_relative_path=DEFAULT_MARKDOWN_OUT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_markdown(report), encoding="utf-8")
    _set_mtime(destination, str(report.get("generated_at", "")))
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build release risk taxonomy audit matrix reports")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--markdown-out", default=DEFAULT_MARKDOWN_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy)
    json_path = write_report(vault, report, args.out)
    markdown_path = write_markdown(vault, report, args.markdown_out)
    print(display_path(vault, json_path))
    print(display_path(vault, markdown_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
