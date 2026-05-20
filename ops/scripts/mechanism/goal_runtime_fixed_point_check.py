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


DEFAULT_OUT = "tmp/goal-runtime-fixed-point-check.json"
PRODUCER = "ops.scripts.goal_runtime_fixed_point_check"
SCHEMA_PATH = "ops/schemas/goal-runtime-fixed-point-check.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_runtime_fixed_point_check --vault ."
CODEX_GOAL_CONTRACT_PATH = "ops/reports/codex-goal-contract.json"
GOAL_RUN_STATUS_PATH = "ops/reports/goal-run-status.json"
AUTO_IMPROVE_READINESS_PATH = "ops/reports/auto-improve-readiness.json"
SESSION_SYNOPSIS_PATH = "ops/reports/session-synopsis.json"
REMEDIATION_BACKLOG_PATH = "ops/reports/remediation-backlog.json"
DERIVED_REMEDIATION_BACKLOG_BLOCKER_IDS = {
    "goal_status_promotion_blocked_by_remediation_backlog_open",
    "promotion_blocked_by_remediation_backlog_open",
}


@dataclass(frozen=True)
class GoalRuntimeFixedPointCheckRequest:
    vault: Path
    out_path: str | None = None
    policy_path: str | None = None
    context: RuntimeContext | None = None
    codex_goal_contract_path: str = CODEX_GOAL_CONTRACT_PATH
    goal_run_status_path: str = GOAL_RUN_STATUS_PATH
    auto_improve_readiness_path: str = AUTO_IMPROVE_READINESS_PATH
    session_synopsis_path: str = SESSION_SYNOPSIS_PATH
    remediation_backlog_path: str = REMEDIATION_BACKLOG_PATH


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _check(
    check_id: str,
    *,
    expected: object,
    observed: object,
    reason: str,
) -> dict[str, Any]:
    status = "pass" if expected == observed else "fail"
    return {
        "id": check_id,
        "status": status,
        "expected": expected,
        "observed": observed,
        "reason": "" if status == "pass" else reason,
    }


def _report_loaded_checks(
    reports: dict[str, dict[str, Any]],
    *,
    report_paths: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        _check(
            f"{name}_loaded",
            expected=True,
            observed=bool(report),
            reason=f"{path} is missing or is not a JSON object",
        )
        for name, path, report in (
            ("codex_goal_contract", report_paths["codex_goal_contract"], reports["contract"]),
            ("goal_run_status", report_paths["goal_run_status"], reports["status"]),
            (
                "auto_improve_readiness",
                report_paths["auto_improve_readiness"],
                reports["readiness"],
            ),
            ("session_synopsis", report_paths["session_synopsis"], reports["session"]),
            ("remediation_backlog", report_paths["remediation_backlog"], reports["backlog"]),
        )
    ]


def _promotion_guard(payload: dict[str, Any]) -> dict[str, Any]:
    guard = payload.get("promotion_guard")
    return guard if isinstance(guard, dict) else {}


def _contract_status_alignment(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    contract = reports["contract"]
    status = reports["status"]
    contract_runtime = contract.get("runtime")
    status_run = status.get("run")
    status_goal = status.get("goal")
    return [
        _check(
            "contract_status_contract_id",
            expected=str(contract.get("contract_id", "")).strip(),
            observed=str(status_goal.get("contract_id", "")).strip()
            if isinstance(status_goal, dict)
            else "",
            reason="goal-run-status must describe the selected codex goal contract",
        ),
        _check(
            "contract_status_runtime_mode",
            expected=str(contract_runtime.get("mode", "")).strip()
            if isinstance(contract_runtime, dict)
            else "",
            observed=str(status_run.get("runtime_mode", "")).strip() if isinstance(status_run, dict) else "",
            reason="goal-run-status run.runtime_mode must match the selected contract runtime mode",
        ),
        _check(
            "contract_status_promotion_blockers",
            expected=sorted(_string_list(_promotion_guard(contract).get("promotion_blockers"))),
            observed=sorted(_string_list(_promotion_guard(status).get("promotion_blockers"))),
            reason="goal-run-status promotion guard must mirror the selected contract blockers",
        ),
    ]


def _session_active_goal_alignment(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    status = reports["status"]
    session = reports["session"]
    status_goal = status.get("goal")
    status_run = status.get("run")
    active_goal = session.get("active_goal")
    if not isinstance(status_goal, dict):
        status_goal = {}
    if not isinstance(status_run, dict):
        status_run = {}
    if not isinstance(active_goal, dict):
        active_goal = {}
    return [
        _check(
            "session_active_goal_contract_id",
            expected=str(status_goal.get("contract_id", "")).strip(),
            observed=str(active_goal.get("contract_id", "")).strip(),
            reason="session synopsis active goal must reference the current goal-run-status contract",
        ),
        _check(
            "session_active_goal_run_id",
            expected=str(status_run.get("run_id", "")).strip(),
            observed=str(active_goal.get("run_id", "")).strip(),
            reason="session synopsis active goal must reference the current goal run id",
        ),
        _check(
            "session_active_goal_run_status",
            expected=str(status_run.get("status", "")).strip(),
            observed=str(active_goal.get("run_status", "")).strip(),
            reason="session synopsis active goal must reference the current goal run status",
        ),
        _check(
            "session_active_goal_runtime_mode",
            expected=str(status_run.get("runtime_mode", "")).strip(),
            observed=str(active_goal.get("runtime_mode", "")).strip(),
            reason="session synopsis active goal must reference the current goal run runtime mode",
        ),
        _check(
            "session_active_goal_can_promote",
            expected=bool(_promotion_guard(status).get("can_promote_result", False)),
            observed=bool(active_goal.get("can_promote_result", False)),
            reason="session synopsis active goal must mirror goal-run-status promotion guard",
        ),
    ]


def _readiness_blocker_ids(readiness: dict[str, Any]) -> list[str]:
    return sorted(
        blocker_id
        for blocker in _dict_list(readiness.get("promotion_blockers"))
        for blocker_id in [str(blocker.get("id", "")).strip()]
        if blocker_id and blocker_id not in DERIVED_REMEDIATION_BACKLOG_BLOCKER_IDS
    )


def _session_readiness_blocker_ids(session: dict[str, Any]) -> list[str]:
    return sorted(
        blocker_id
        for blocker in _dict_list(session.get("recent_blockers"))
        if str(blocker.get("source", "")).strip() == "auto_improve_readiness.promotion_blockers"
        for blocker_id in [str(blocker.get("id", "")).strip()]
        if blocker_id
    )


def _session_blocker_ids(session: dict[str, Any]) -> list[str]:
    return sorted(
        blocker_id
        for blocker in _dict_list(session.get("recent_blockers"))
        for blocker_id in [str(blocker.get("id", "")).strip()]
        if blocker_id
    )


def _backlog_open_active_blocker_ids(backlog: dict[str, Any]) -> list[str]:
    return sorted(
        blocker_id
        for item in _dict_list(backlog.get("items"))
        if str(item.get("status", "")).strip() == "open"
        if str(item.get("item_type", "")).strip() == "active_blocker"
        if str(item.get("severity", "")).strip() == "blocks_promotion"
        for blocker_id in [str(item.get("blocker_id", "")).strip()]
        if blocker_id
    )


def _readiness_remediation_signal_ids(readiness: dict[str, Any]) -> list[str]:
    for blocker in _dict_list(readiness.get("promotion_blockers")):
        if str(blocker.get("id", "")).strip() == "promotion_blocked_by_remediation_backlog_open":
            return sorted(_string_list(blocker.get("signal_ids")))
    return []


def _blocker_alignment_checks(reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    readiness = reports["readiness"]
    session = reports["session"]
    backlog = reports["backlog"]
    active_backlog_ids = _backlog_open_active_blocker_ids(backlog)
    return [
        _check(
            "session_readiness_blockers",
            expected=_readiness_blocker_ids(readiness),
            observed=_session_readiness_blocker_ids(session),
            reason="session synopsis readiness blockers must match current auto-improve readiness blockers",
        ),
        _check(
            "backlog_session_blockers",
            expected=_session_blocker_ids(session),
            observed=active_backlog_ids,
            reason=(
                "remediation backlog open active promotion blocker ids must match "
                "session synopsis recent blockers"
            ),
        ),
        _check(
            "readiness_backlog_signals",
            expected=active_backlog_ids,
            observed=_readiness_remediation_signal_ids(readiness),
            reason=(
                "readiness remediation blocker signal ids must match current "
                "active promotion blockers in remediation backlog"
            ),
        ),
    ]


def _summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [check for check in checks if check["status"] != "pass"]
    return {
        "report_count": 5,
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "status": "pass" if not failed else "fail",
    }


def build_report(request: GoalRuntimeFixedPointCheckRequest) -> dict[str, Any]:
    vault = request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    context = request.context or RuntimeContext.from_policy(policy)
    report_paths = {
        "codex_goal_contract": request.codex_goal_contract_path,
        "goal_run_status": request.goal_run_status_path,
        "auto_improve_readiness": request.auto_improve_readiness_path,
        "session_synopsis": request.session_synopsis_path,
        "remediation_backlog": request.remediation_backlog_path,
    }
    reports = {
        "contract": _load_json_object(vault / request.codex_goal_contract_path),
        "status": _load_json_object(vault / request.goal_run_status_path),
        "readiness": _load_json_object(vault / request.auto_improve_readiness_path),
        "session": _load_json_object(vault / request.session_synopsis_path),
        "backlog": _load_json_object(vault / request.remediation_backlog_path),
    }
    checks = [
        *_report_loaded_checks(reports, report_paths=report_paths),
        *_contract_status_alignment(reports),
        *_session_active_goal_alignment(reports),
        *_blocker_alignment_checks(reports),
    ]
    summary = _summary(checks)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=context.isoformat_z(),
            artifact_kind="goal_runtime_fixed_point_check",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_runtime_fixed_point_check.py",
                "ops/schemas/goal-runtime-fixed-point-check.schema.json",
                "mk/mechanism.mk",
            ],
            file_inputs=report_paths,
            source_tree_excluded_files=(request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "status": summary["status"],
        "summary": summary,
        "checks": checks,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="goal runtime fixed-point check schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output report path.")
    parser.add_argument("--policy-path", default=None, help="Policy path relative to the vault.")
    parser.add_argument("--codex-goal-contract", default=CODEX_GOAL_CONTRACT_PATH)
    parser.add_argument("--goal-run-status", default=GOAL_RUN_STATUS_PATH)
    parser.add_argument("--auto-improve-readiness", default=AUTO_IMPROVE_READINESS_PATH)
    parser.add_argument("--session-synopsis", default=SESSION_SYNOPSIS_PATH)
    parser.add_argument("--remediation-backlog", default=REMEDIATION_BACKLOG_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRuntimeFixedPointCheckRequest(
            vault=vault,
            out_path=args.out,
            policy_path=args.policy_path,
            codex_goal_contract_path=args.codex_goal_contract,
            goal_run_status_path=args.goal_run_status,
            auto_improve_readiness_path=args.auto_improve_readiness,
            session_synopsis_path=args.session_synopsis,
            remediation_backlog_path=args.remediation_backlog,
        )
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
