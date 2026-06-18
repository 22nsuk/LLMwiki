from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
    write_vault_schema_validated_json,
)
from ops.scripts.core.observability_artifacts_shared_runtime import (
    AUTO_IMPROVE_SESSION_REPORT_DIR,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism.goal_runtime_json_loader_runtime import (
    load_json_object_from_path,
)

DEFAULT_OUT = "tmp/goal-runtime-stale-closeout.json"
PRODUCER = "ops.scripts.goal_runtime_stale_closeout"
SCHEMA_PATH = "ops/schemas/goal-runtime-stale-closeout.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_runtime_stale_closeout --vault ."
RESOLVED_HISTORY_STATUSES = {"archived", "quarantined"}
PRE_CANDIDATE_EVENTS = {
    "created",
    "scope_frozen",
    "subagent_routed",
    "seed_frozen",
    "baseline_captured",
    "history_status_updated",
}


@dataclass(frozen=True)
class GoalRuntimeStaleCloseoutRequest:
    vault: Path
    apply: bool = False
    out_path: str | None = None
    policy_path: str | None = None
    context: RuntimeContext | None = None


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_field(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _text(value: object) -> str:
    return str(value or "").strip()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    results: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if path.is_file() and resolved not in seen:
            results.append(path)
            seen.add(resolved)
    return results


def _session_report_paths(vault: Path) -> list[Path]:
    roots = [
        vault / AUTO_IMPROVE_SESSION_REPORT_DIR,
        vault / AUTO_IMPROVE_SESSION_REPORT_DIR / "archive",
        vault / "ops" / "reports" / "archive" / "auto-improve-sessions",
    ]
    paths: list[Path] = []
    for root in roots:
        if root.is_dir():
            paths.extend(sorted(root.glob("*.json")))
    archive_root = vault / "ops" / "reports" / "archive"
    if archive_root.is_dir():
        paths.extend(
            sorted(
                path
                for path in archive_root.rglob("*.json")
                if "auto-improve-sessions" in path.parts
            )
        )
    return _dedupe_paths(paths)


def _run_ledger_paths(vault: Path) -> list[Path]:
    paths = sorted((vault / "runs").glob("*/run-ledger.json"))
    archive_root = vault / "runs" / "archive"
    if archive_root.is_dir():
        paths.extend(sorted(archive_root.rglob("run-ledger.json")))
    return _dedupe_paths(paths)


def _issue(
    *,
    issue_type: str,
    surface: str,
    path: str,
    resolution_status: str,
    reason: str,
    next_action: str,
    evidence_paths: list[str],
    observed: dict[str, Any],
) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "surface": surface,
        "path": path,
        "resolution_status": resolution_status,
        "reason": reason,
        "next_action": next_action,
        "evidence_paths": list(dict.fromkeys(path for path in evidence_paths if path)),
        "observed": observed,
    }


def _session_path_resolution_issue(vault: Path, path: Path, session: dict[str, Any]) -> dict[str, Any] | None:
    recorded_path = _text(session.get("path"))
    actual_path = report_path(vault, path)
    if not recorded_path or recorded_path == actual_path or (vault / recorded_path).is_file():
        return None
    return _issue(
        issue_type="session_path_reference_resolved",
        surface="auto_improve_session",
        path=actual_path,
        resolution_status="resolved_by_path_resolution",
        reason="session report was found at a different path than the embedded session path",
        next_action="Keep readers on archive-aware session path resolution; rewrite the generated session report only during an explicit artifact migration.",
        evidence_paths=[recorded_path, actual_path],
        observed={"recorded_path": recorded_path, "resolved_path": actual_path},
    )


def _session_stale_issue(vault: Path, path: Path, session: dict[str, Any]) -> dict[str, Any] | None:
    if _text(session.get("status")) != "running":
        return None
    iterations = _list_field(session, "iterations")
    run_ids = [item for item in _list_field(session, "run_ids") if _text(item)]
    actual_path = report_path(vault, path)
    if not iterations and not run_ids:
        return _issue(
            issue_type="stale_session_no_attempts",
            surface="auto_improve_session",
            path=actual_path,
            resolution_status="action_required",
            reason="auto-improve session is still running but has no recorded attempts",
            next_action="Explicitly close, archive, or regenerate the stale session report before relying on it as current session evidence.",
            evidence_paths=[actual_path],
            observed={
                "session_id": _text(session.get("session_id")),
                "status": _text(session.get("status")),
                "stop_reason": _text(session.get("stop_reason")),
                "iteration_count": len(iterations),
                "run_id_count": len(run_ids),
            },
        )
    return _issue(
        issue_type="stale_session_incomplete_attempts",
        surface="auto_improve_session",
        path=actual_path,
        resolution_status="action_required",
        reason="auto-improve session has attempts but never reached a terminal session status",
        next_action="Review the recorded attempts, then complete the session with a terminal stop reason or archive it as abandoned evidence.",
        evidence_paths=[actual_path, *[f"runs/{run_id}" for run_id in run_ids]],
        observed={
            "session_id": _text(session.get("session_id")),
            "status": _text(session.get("status")),
            "stop_reason": _text(session.get("stop_reason")),
            "iteration_count": len(iterations),
            "run_id_count": len(run_ids),
        },
    )


def _session_issues(vault: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for path in _session_report_paths(vault):
        session = load_json_object_from_path(path)
        path_issue = _session_path_resolution_issue(vault, path, session)
        if path_issue is not None:
            issues.append(path_issue)
        stale_issue = _session_stale_issue(vault, path, session)
        if stale_issue is not None:
            issues.append(stale_issue)
    return issues


def _event_types(ledger: dict[str, Any]) -> list[str]:
    return [_text(item.get("type")) for item in _list_field(ledger, "events") if isinstance(item, dict)]


def _latest_history_event_status(ledger: dict[str, Any]) -> str:
    for item in reversed(_list_field(ledger, "events")):
        if not isinstance(item, dict) or _text(item.get("type")) != "history_status_updated":
            continue
        return _text(item.get("decision"))
    return ""


def _promotion_history_status(path: Path) -> str:
    promotion = load_json_object_from_path(path.parent / "promotion-report.json")
    return _text(_dict_field(promotion, "history").get("status"))


def _ledger_history_status(path: Path, ledger: dict[str, Any]) -> str:
    return _promotion_history_status(path) or _latest_history_event_status(ledger)


def _ledger_issue(vault: Path, path: Path, ledger: dict[str, Any]) -> dict[str, Any] | None:
    rel_path = report_path(vault, path)
    status = _text(ledger.get("status"))
    events = _event_types(ledger)
    history_status = _ledger_history_status(path, ledger)
    observed = {
        "run_id": _text(ledger.get("run_id")) or path.parent.name,
        "ledger_status": status,
        "history_status": history_status,
        "event_types": events,
    }
    if status == "running" and history_status in RESOLVED_HISTORY_STATUSES:
        return _issue(
            issue_type="ledger_history_status_mismatch",
            surface="run_ledger",
            path=rel_path,
            resolution_status="resolved_by_history",
            reason="promotion history is resolved but run-ledger.status still says running",
            next_action="Normalize the generated ledger lifecycle so archived/quarantined runs no longer look active.",
            evidence_paths=[rel_path, report_path(vault, path.parent / "promotion-report.json")],
            observed=observed,
        )
    if status == "running" and set(events).issubset(PRE_CANDIDATE_EVENTS):
        return _issue(
            issue_type="ledger_baseline_only_abandoned",
            surface="run_ledger",
            path=rel_path,
            resolution_status="action_required",
            reason="run ledger is still running and never reached candidate or repo-health evidence",
            next_action="Archive/quarantine the run history or restore the missing execution evidence before using this run as active history.",
            evidence_paths=[rel_path],
            observed=observed,
        )
    if status == "running":
        return _issue(
            issue_type="ledger_running_stale",
            surface="run_ledger",
            path=rel_path,
            resolution_status="action_required",
            reason="run ledger is still running after recording later execution evidence",
            next_action="Inspect the latest run artifacts and close the run ledger to ready, blocked, complete, archived, or quarantined evidence.",
            evidence_paths=[rel_path],
            observed=observed,
        )
    return None


def _ledger_issues(vault: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for path in _run_ledger_paths(vault):
        ledger = load_json_object_from_path(path)
        issue = _ledger_issue(vault, path, ledger)
        if issue is not None:
            issues.append(issue)
    return issues


def _summary(issues: list[dict[str, Any]]) -> dict[str, Any]:
    action_required = [
        item for item in issues if item["resolution_status"] == "action_required"
    ]
    resolved_by_history = [
        item for item in issues if item["resolution_status"] == "resolved_by_history"
    ]
    path_resolved = [
        item for item in issues if item["resolution_status"] == "resolved_by_path_resolution"
    ]
    return {
        "issue_count": len(issues),
        "action_required_count": len(action_required),
        "resolved_by_history_count": len(resolved_by_history),
        "path_resolution_count": len(path_resolved),
        "session_issue_count": sum(1 for item in issues if item["surface"] == "auto_improve_session"),
        "ledger_issue_count": sum(1 for item in issues if item["surface"] == "run_ledger"),
    }


def _cleanup_summary(*, apply: bool, results: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "apply": apply,
        "eligible_count": len(results),
        "updated_count": sum(1 for item in results if item["action"] == "updated"),
        "skipped_count": sum(1 for item in results if item["action"] == "skipped"),
        "failed_count": sum(1 for item in results if item["action"] == "failed"),
        "updated_paths": [item["path"] for item in results if item["action"] == "updated"],
        "failed_paths": [item["path"] for item in results if item["action"] == "failed"],
    }


def _recommended_next_action(summary: dict[str, Any]) -> str:
    if int(summary["action_required_count"]) > 0:
        return "Close, archive, or quarantine stale running session and ledger evidence before treating it as current run state."
    if int(summary["resolved_by_history_count"]) > 0:
        return "Normalize stale run-ledger.status fields that already have archived/quarantined history decisions."
    if int(summary["path_resolution_count"]) > 0:
        return "Keep archive-aware session path resolution active; migrate embedded generated paths only during explicit artifact migration."
    return "No stale session or run-ledger closeout residue was found."


def _closeout_session(vault: Path, issue: dict[str, Any], *, context: RuntimeContext) -> None:
    rel_path = str(issue["path"])
    session = load_json_object_from_path(vault / rel_path)
    metadata = session.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["stale_closeout"] = {
        "closed_at": context.isoformat_z(),
        "issue_type": str(issue["issue_type"]),
        "prior_status": _text(session.get("status")),
        "prior_stop_reason": _text(session.get("stop_reason")),
    }
    session["metadata"] = metadata
    session["status"] = "blocked"
    session["stop_reason"] = "stale_closeout_required"
    write_vault_schema_validated_json(
        vault,
        rel_path,
        session,
        "ops/schemas/auto-improve-session.schema.json",
        context=f"auto-improve session stale closeout validation failed for {rel_path}",
        trailing_newline=True,
    )


def _closeout_ledger(vault: Path, issue: dict[str, Any]) -> None:
    rel_path = str(issue["path"])
    ledger = load_json_object_from_path(vault / rel_path)
    ledger["status"] = "blocked"
    write_vault_schema_validated_json(
        vault,
        rel_path,
        ledger,
        "ops/schemas/run-ledger.schema.json",
        context=f"run-ledger stale closeout validation failed for {rel_path}",
        trailing_newline=True,
    )


def _cleanup_result(issue: dict[str, Any], *, action: str, error: str = "") -> dict[str, str]:
    return {
        "path": str(issue["path"]),
        "issue_type": str(issue["issue_type"]),
        "surface": str(issue["surface"]),
        "action": action,
        "error": error,
    }


def _apply_closeout(vault: Path, issues: list[dict[str, Any]], *, context: RuntimeContext) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for issue in issues:
        issue_type = str(issue["issue_type"])
        try:
            if issue_type in {"stale_session_no_attempts", "stale_session_incomplete_attempts"}:
                _closeout_session(vault, issue, context=context)
                results.append(_cleanup_result(issue, action="updated"))
            elif issue_type in {
                "ledger_history_status_mismatch",
                "ledger_baseline_only_abandoned",
                "ledger_running_stale",
            }:
                _closeout_ledger(vault, issue)
                results.append(_cleanup_result(issue, action="updated"))
            else:
                results.append(_cleanup_result(issue, action="skipped"))
        except (OSError, ValueError) as exc:
            results.append(_cleanup_result(issue, action="failed", error=str(exc)))
    return results


def build_report(
    request: GoalRuntimeStaleCloseoutRequest | Path,
    **legacy_fields: Any,
) -> dict[str, Any]:
    if isinstance(request, GoalRuntimeStaleCloseoutRequest):
        if legacy_fields:
            raise TypeError("build_report accepts either a request object or legacy keyword fields")
        active_request = request
    else:
        active_request = GoalRuntimeStaleCloseoutRequest(vault=Path(request), **legacy_fields)
    vault = active_request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, active_request.policy_path)
    context = active_request.context or RuntimeContext.from_policy(policy)
    issues = [*_session_issues(vault), *_ledger_issues(vault)]
    cleanup_results: list[dict[str, str]] = []
    if active_request.apply:
        cleanup_results = _apply_closeout(vault, issues, context=context)
        issues = [*_session_issues(vault), *_ledger_issues(vault)]
    summary = _summary(issues)
    cleanup = _cleanup_summary(apply=active_request.apply, results=cleanup_results)
    status = (
        "fail"
        if cleanup["failed_count"] or int(summary["action_required_count"]) > 0
        else "attention" if issues else "pass"
    )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=context.isoformat_z(),
            artifact_kind="goal_runtime_stale_closeout",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_runtime_stale_closeout.py",
                "ops/scripts/core/observability_artifacts_shared_runtime.py",
                "ops/schemas/goal-runtime-stale-closeout.schema.json",
            ],
            source_tree_excluded_files=(active_request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "status": status,
        "summary": summary,
        "cleanup": cleanup,
        "recommended_next_action": _recommended_next_action(summary),
        "issues": issues,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            default_relative_path=DEFAULT_OUT,
            out_path=out_path,
            context="goal runtime stale closeout schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--policy-path")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault)
    report = build_report(
        GoalRuntimeStaleCloseoutRequest(
            vault=vault,
            apply=args.apply,
            out_path=args.out,
            policy_path=args.policy_path,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 1 if args.strict and report["status"] == "fail" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
