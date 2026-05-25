#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,  # noqa: PLC0415
    )
    from ops.scripts.artifact_io_runtime import (  # noqa: PLC0415
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.policy_runtime import load_policy, report_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext


DEFAULT_MATRIX = (
    "runs/run-20260422-raw-intake-registration-and-promotion/"
    "absorption/raw-intake-absorption-matrix-2026-04-22.json"
)
DEFAULT_OUT = "tmp/raw-intake-route-proposal-report.json"
PRODUCER = "ops.scripts.raw_intake_route_proposal"
SCHEMA_PATH = "ops/schemas/raw-intake-route-proposal-report.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.raw_intake_route_proposal"
ALLOWED_ACTIONS = (
    "update_existing_source",
    "refresh_existing_synthesis",
    "create_new_synthesis_family",
    "keep_source_only_seed",
    "discard_from_active_routes",
)
REVIEWED_ROUTE_STATUSES = ("approved", "reviewed")
CONFIDENCE_LEVELS = ("high", "medium", "low")


def _resolved_input_path(vault: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return (vault / resolved).resolve()


def _string_value(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    return str(value).strip() if value is not None else ""


def _route_basis(entry: dict[str, Any]) -> dict[str, str]:
    return {
        "current_topic_family": _string_value(entry, "current_topic_family"),
        "current_domain": _string_value(entry, "current_domain"),
        "title": _string_value(entry, "title"),
        "raw_path": _string_value(entry, "raw_path"),
        "source_page": _string_value(entry, "source_page"),
    }


def _route_key(entry: dict[str, Any]) -> str:
    basis = _route_basis(entry)
    route_material = "\n".join(f"{key}={basis[key]}" for key in sorted(basis))
    return hashlib.sha256(route_material.encode("utf-8")).hexdigest()[:16]


def _proposal_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    action = _string_value(entry, "proposed_action")
    target = _string_value(entry, "target")
    rationale = _string_value(entry, "rationale")
    confidence = _string_value(entry, "confidence")
    review_status = _string_value(entry, "review_status")
    issues: list[str] = []
    review_reasons: list[str] = []

    if action not in ALLOWED_ACTIONS:
        issues.append("unknown_proposed_action")
    if not target:
        issues.append("missing_target")
    if not rationale:
        issues.append("missing_rationale")
    if confidence not in CONFIDENCE_LEVELS:
        issues.append("unknown_confidence")
    if review_status not in REVIEWED_ROUTE_STATUSES:
        issues.append("unreviewed_route_assignment")
        review_reasons.append("route assignment has not been reviewed or approved")
    if confidence == "low":
        review_reasons.append("low confidence route assignment requires explicit review")
    if action == "keep_source_only_seed":
        review_reasons.append("source-only seed posture requires future absorption review")

    closeout_status = "fail" if issues else "pass"
    review_gate = "satisfied" if review_status in REVIEWED_ROUTE_STATUSES else "required"
    if closeout_status == "fail":
        review_gate = "required"

    return {
        "registry_id": _string_value(entry, "registry_id"),
        "source_page": _string_value(entry, "source_page"),
        "raw_path": _string_value(entry, "raw_path"),
        "route_key": _route_key(entry),
        "route_basis": _route_basis(entry),
        "proposed_action": action,
        "target": target,
        "confidence": confidence,
        "review_status": review_status,
        "review_gate": review_gate,
        "closeout_status": closeout_status,
        "issues": issues,
        "review_reasons": review_reasons,
    }


def load_matrix(matrix_path: Path) -> dict[str, Any]:
    return json.loads(matrix_path.read_text(encoding="utf-8"))


def build_report(
    vault: Path,
    *,
    matrix_path: str | Path = DEFAULT_MATRIX,
    mode: str = "route_proposal",
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    resolved_matrix_path = _resolved_input_path(vault, matrix_path)
    matrix = load_matrix(resolved_matrix_path)
    entries = matrix.get("matrix")
    if not isinstance(entries, list):
        entries = []
    proposals = [_proposal_for_entry(entry) for entry in entries if isinstance(entry, dict)]
    blocking = [
        {
            "registry_id": proposal["registry_id"],
            "source_page": proposal["source_page"],
            "issues": proposal["issues"],
        }
        for proposal in proposals
        if proposal["closeout_status"] == "fail"
    ]
    review_gate_counts = Counter(proposal["review_gate"] for proposal in proposals)
    closeout_counts = Counter(proposal["closeout_status"] for proposal in proposals)
    status = "fail" if blocking else "pass"

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_intake_route_proposal_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/raw_intake_route_proposal.py"],
            file_inputs={"matrix": resolved_matrix_path},
            text_inputs={"mode": mode},
        ),
        "vault": report_path(vault, vault),
        "mode": mode,
        "status": status,
        "matrix": {
            "path": report_path(vault, resolved_matrix_path),
            "scope": str(matrix.get("scope", "")).strip(),
            "declared_source_count": int(matrix.get("source_count", 0) or 0),
            "entry_count": len(proposals),
        },
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "allowed_actions": list(ALLOWED_ACTIONS),
        "reviewed_route_statuses": list(REVIEWED_ROUTE_STATUSES),
        "summary": {
            "entry_count": len(proposals),
            "blocking_issue_count": len(blocking),
            "review_required_count": int(review_gate_counts.get("required", 0)),
            "review_satisfied_count": int(review_gate_counts.get("satisfied", 0)),
            "closeout_pass_count": int(closeout_counts.get("pass", 0)),
            "closeout_fail_count": int(closeout_counts.get("fail", 0)),
        },
        "blocking_issues": blocking,
        "proposals": proposals,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="raw intake route proposal schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic raw-intake route proposal and absorption closeout gate.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--matrix", default=DEFAULT_MATRIX)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--mode",
        choices=("route_proposal", "absorption_closeout"),
        default="route_proposal",
    )
    parser.add_argument("--fail-on-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, matrix_path=args.matrix, mode=args.mode)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.fail_on_fail and report["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
