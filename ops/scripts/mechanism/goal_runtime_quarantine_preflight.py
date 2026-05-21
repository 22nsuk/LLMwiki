from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "tmp/goal-runtime-quarantine-preflight.json"
DEFAULT_MECHANISM_REVIEW_REPORT = "ops/reports/mechanism-review-candidates.json"
PRODUCER = "ops.scripts.goal_runtime_quarantine_preflight"
SCHEMA_PATH = "ops/schemas/goal-runtime-quarantine-preflight.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_runtime_quarantine_preflight --vault ."
RESOLVED_HISTORY_STATUSES = {"archived", "quarantined"}


@dataclass(frozen=True)
class GoalRuntimeQuarantinePreflightRequest:
    vault: Path
    out_path: str | None = None
    policy_path: str | None = None
    mechanism_review_report_path: str = DEFAULT_MECHANISM_REVIEW_REPORT
    context: RuntimeContext | None = None


def _load_json_object(vault: Path, rel_path: str) -> dict[str, Any]:
    try:
        payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list_field(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _text(value: object) -> str:
    return str(value).strip()


def _history_cleanup_required(skipped_run: dict[str, Any]) -> bool:
    triage = _dict_field(skipped_run, "triage")
    if _text(triage.get("status")) != "operator_decision_required":
        return False
    recommended_action = _text(triage.get("recommended_action"))
    options = [_text(item) for item in _list_field(triage, "options")]
    haystack = " ".join([recommended_action, *options]).lower()
    return "archive" in haystack or "quarantine" in haystack


def _skip_summary(skipped_run: dict[str, Any]) -> dict[str, str]:
    return {
        "run_id": _text(skipped_run.get("run_id")),
        "reason": _text(skipped_run.get("reason")),
        "path": _text(skipped_run.get("path")),
        "detail": _text(skipped_run.get("detail")),
    }


def _exclusion_summary(excluded_run: dict[str, Any]) -> dict[str, str]:
    return {
        "run_id": _text(excluded_run.get("run_id")),
        "status": _text(excluded_run.get("status")),
        "reason": _text(excluded_run.get("reason")),
        "path": _text(excluded_run.get("path")),
    }


def _check(
    *,
    check_id: str,
    status: str,
    expected: object,
    observed: object,
    reason: str,
    next_action: str,
    evidence_paths: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "expected": expected,
        "observed": observed,
        "reason": reason,
        "next_action": next_action,
        "evidence_paths": list(dict.fromkeys(path for path in evidence_paths if path)),
    }


def _mechanism_review_check(mechanism_review: dict[str, Any], path: str) -> dict[str, Any]:
    artifact_kind = _text(mechanism_review.get("artifact_kind"))
    producer = _text(mechanism_review.get("producer"))
    report_status = _text(mechanism_review.get("status")) or "missing"
    passed = (
        artifact_kind == "mechanism_review_candidates_report"
        and producer == "ops.scripts.mechanism_review_runtime"
        and report_status in {"pass", "attention"}
    )
    return _check(
        check_id="mechanism_review_history_loaded",
        status="pass" if passed else "fail",
        expected={
            "artifact_kind": "mechanism_review_candidates_report",
            "producer": "ops.scripts.mechanism_review_runtime",
            "status": ["pass", "attention"],
        },
        observed={
            "artifact_kind": artifact_kind or "missing",
            "producer": producer or "missing",
            "status": report_status,
        },
        reason=(
            "mechanism review history report is available"
            if passed
            else "quarantine preflight requires a current mechanism review history report"
        ),
        next_action=(
            "Proceed with quarantine preflight."
            if passed
            else "Run `make refresh-generated-core` before starting a goal runtime run."
        ),
        evidence_paths=[path],
    )


def _unresolved_history_check(unresolved: list[dict[str, str]], path: str) -> dict[str, Any]:
    passed = not unresolved
    return _check(
        check_id="unresolved_history_cleanup_clear",
        status="pass" if passed else "fail",
        expected={"operator_decision_required_count": 0},
        observed={"operator_decision_required_count": len(unresolved), "runs": unresolved},
        reason=(
            "no active mechanism history run requires archive/quarantine cleanup"
            if passed
            else "active mechanism history still has skipped runs that require restore, archive, or quarantine before the next long run"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Repair missing promotion inputs or run `python -m ops.scripts.set_mechanism_run_history --status archived|quarantined` for each listed run."
        ),
        evidence_paths=[path],
    )


def _excluded_history_check(invalid: list[dict[str, str]], path: str) -> dict[str, Any]:
    passed = not invalid
    return _check(
        check_id="excluded_history_classified",
        status="pass" if passed else "fail",
        expected={"excluded_history_statuses": sorted(RESOLVED_HISTORY_STATUSES)},
        observed={"invalid_exclusion_count": len(invalid), "runs": invalid},
        reason=(
            "excluded mechanism runs are classified as archived or quarantined"
            if passed
            else "excluded mechanism history contains a non-resolved status"
        ),
        next_action=(
            "Proceed with run admission."
            if passed
            else "Normalize excluded mechanism history to archived or quarantined before starting a long run."
        ),
        evidence_paths=[path],
    )


def _status(checks: list[dict[str, Any]]) -> str:
    return "fail" if any(check["status"] == "fail" for check in checks) else "pass"


def _recommended_next_action(checks: list[dict[str, Any]]) -> str:
    for check in checks:
        if check["status"] == "fail":
            return str(check["next_action"])
    return "Proceed with `make goal-runtime-run-admission`."


def build_report(
    request: GoalRuntimeQuarantinePreflightRequest | Path,
    **legacy_fields: Any,
) -> dict[str, Any]:
    if isinstance(request, GoalRuntimeQuarantinePreflightRequest):
        if legacy_fields:
            raise TypeError("build_report accepts either a request object or legacy keyword fields")
        active_request = request
    else:
        active_request = GoalRuntimeQuarantinePreflightRequest(vault=Path(request), **legacy_fields)
    vault = active_request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, active_request.policy_path)
    context = active_request.context or RuntimeContext.from_policy(policy)
    mechanism_review = _load_json_object(vault, active_request.mechanism_review_report_path)
    diagnostics = _dict_field(mechanism_review, "diagnostics")
    skipped_runs = [
        item for item in _list_field(diagnostics, "skipped_runs") if isinstance(item, dict)
    ]
    excluded_runs = [
        item for item in _list_field(diagnostics, "excluded_runs") if isinstance(item, dict)
    ]
    unresolved_history_cleanup = [
        _skip_summary(item) for item in skipped_runs if _history_cleanup_required(item)
    ]
    excluded_summaries = [_exclusion_summary(item) for item in excluded_runs]
    invalid_exclusions = [
        item for item in excluded_summaries if item["status"] not in RESOLVED_HISTORY_STATUSES
    ]
    checks = [
        _mechanism_review_check(mechanism_review, active_request.mechanism_review_report_path),
        _unresolved_history_check(unresolved_history_cleanup, active_request.mechanism_review_report_path),
        _excluded_history_check(invalid_exclusions, active_request.mechanism_review_report_path),
    ]
    summary = {
        "skipped_run_count": len(skipped_runs),
        "operator_decision_required_count": len(unresolved_history_cleanup),
        "excluded_run_count": len(excluded_summaries),
        "archived_run_count": sum(1 for item in excluded_summaries if item["status"] == "archived"),
        "quarantined_run_count": sum(
            1 for item in excluded_summaries if item["status"] == "quarantined"
        ),
        "invalid_exclusion_count": len(invalid_exclusions),
    }
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=context.isoformat_z(),
            artifact_kind="goal_runtime_quarantine_preflight",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_runtime_quarantine_preflight.py",
                "ops/scripts/mechanism/mechanism_review_history_runtime.py",
                "ops/scripts/mechanism/set_mechanism_run_history.py",
                "ops/schemas/goal-runtime-quarantine-preflight.schema.json",
            ],
            file_inputs={
                "mechanism_review_report": active_request.mechanism_review_report_path,
            },
            source_tree_excluded_files=(active_request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "status": _status(checks),
        "summary": summary,
        "recommended_next_action": _recommended_next_action(checks),
        "inputs": {
            "mechanism_review_report": active_request.mechanism_review_report_path,
        },
        "checks": checks,
        "unresolved_history_cleanup": unresolved_history_cleanup,
        "excluded_runs": excluded_summaries,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="goal runtime quarantine preflight schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check goal-runtime history quarantine cleanup before a run.")
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output report path.")
    parser.add_argument("--mechanism-review-report", default=DEFAULT_MECHANISM_REVIEW_REPORT)
    parser.add_argument("--policy-path", default=None)
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when preflight fails.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRuntimeQuarantinePreflightRequest(
            vault=vault,
            out_path=args.out,
            policy_path=args.policy_path,
            mechanism_review_report_path=args.mechanism_review_report,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.strict and report["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
