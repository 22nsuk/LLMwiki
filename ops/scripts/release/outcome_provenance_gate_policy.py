#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
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
    from ops.scripts.schema_constants_runtime import (
        ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
    )
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
    )


DEFAULT_OUT = "ops/reports/outcome-provenance-gate-policy.json"
SCHEMA_PATH = "ops/schemas/outcome-provenance-gate-policy.schema.json"
PRODUCER = "ops.scripts.outcome_provenance_gate_policy"
SOURCE_COMMAND = "python -m ops.scripts.outcome_provenance_gate_policy --vault ."
OUTCOME_METRICS_PATH = "ops/reports/outcome-metrics.json"
SUPPLY_CHAIN_GATE_PATH = "ops/reports/supply-chain-gate-report.json"
ROUTING_AGGREGATE_GLOB = "ops/reports/routing-provenance-aggregates/*.json"


ESCALATION_CONDITIONS = [
    {
        "condition_id": "rollback_signal_without_rehearsal_coverage",
        "promotion_effect_when_default": "block_promotion",
        "required_evidence": "rollback_signal_count must be covered by passing rollback-rehearsal-report artifacts or explicit closure evidence",
        "rollback_rehearsal_required": True,
    },
    {
        "condition_id": "defect_escape_signal_unclosed",
        "promotion_effect_when_default": "block_promotion",
        "required_evidence": "defect escape signals require closure registry evidence before default promotion",
        "rollback_rehearsal_required": False,
    },
    {
        "condition_id": "routing_or_executor_provenance_gap",
        "promotion_effect_when_default": "block_promotion",
        "required_evidence": "routing provenance aggregate must cover routing/executor/telemetry for promoted runs",
        "rollback_rehearsal_required": False,
    },
    {
        "condition_id": "supply_chain_gate_fail",
        "promotion_effect_when_default": "block_release_profile",
        "required_evidence": "supply-chain gate must pass before provenance or sbom release profiles become default",
        "rollback_rehearsal_required": False,
    },
]


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, "invalid"
    return (payload if isinstance(payload, dict) else {}), "ok"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _outcome_evidence(vault: Path) -> dict[str, Any]:
    payload, load_status = _load_json(vault / OUTCOME_METRICS_PATH)
    metrics = _as_dict(payload.get("metrics"))
    summary = _as_dict(payload.get("summary"))
    moving = _as_dict(metrics.get("moving_averages"))
    rollback_signal_count = _int(metrics.get("rollback_signal_count"))
    rollback_rehearsal_coverage_count = _int(metrics.get("rollback_rehearsal_coverage_count"))
    defect_escape_count = _int(metrics.get("defect_escape_count"))
    rework_count = _int(metrics.get("rework_count"))
    maturity_status = "pass"
    if load_status != "ok":
        maturity_status = "missing"
    elif rollback_signal_count > rollback_rehearsal_coverage_count or defect_escape_count or rework_count:
        maturity_status = "attention"
    return {
        "path": OUTCOME_METRICS_PATH,
        "load_status": load_status,
        "status": str(payload.get("status", "unknown")).strip() if payload else "unknown",
        "attempts_considered": _int(summary.get("attempts_considered")),
        "recent_attempt_count": _int(summary.get("recent_attempt_count")),
        "rework_count": rework_count,
        "rollback_signal_count": rollback_signal_count,
        "rollback_rehearsal_coverage_count": rollback_rehearsal_coverage_count,
        "defect_escape_count": defect_escape_count,
        "moving_average_hold": float(moving.get("hold", 0.0) or 0.0),
        "moving_average_discard": float(moving.get("discard", 0.0) or 0.0),
        "maturity_status": maturity_status,
    }


def _routing_provenance_evidence(vault: Path) -> dict[str, Any]:
    paths = sorted(path for path in vault.glob(ROUTING_AGGREGATE_GLOB) if path.is_file())
    health_flags: list[str] = []
    complete_count = 0
    for path in paths:
        payload, load_status = _load_json(path)
        if load_status != "ok":
            health_flags.append("aggregate_load_error")
            continue
        loop_health = _as_dict(payload.get("loop_health"))
        flags = _as_list(loop_health.get("health_flags"))
        health_flags.extend(str(flag) for flag in flags if str(flag).strip())
        if not flags:
            complete_count += 1
    status = "missing" if not paths else "attention" if health_flags else "pass"
    return {
        "path_glob": ROUTING_AGGREGATE_GLOB,
        "aggregate_count": len(paths),
        "complete_aggregate_count": complete_count,
        "status": status,
        "health_flags": sorted(set(health_flags)),
    }


def _supply_chain_gate_evidence(vault: Path) -> dict[str, Any]:
    payload, load_status = _load_json(vault / SUPPLY_CHAIN_GATE_PATH)
    checks = _as_list(payload.get("checks"))
    failing_rules = [
        str(check.get("rule", "")).strip()
        for check in checks
        if isinstance(check, dict) and not bool(check.get("pass"))
    ]
    status = str(payload.get("status", "unknown")).strip() if payload else "unknown"
    maturity_status = "pass" if load_status == "ok" and status == "pass" else "attention"
    if load_status != "ok":
        maturity_status = "missing"
    return {
        "path": SUPPLY_CHAIN_GATE_PATH,
        "load_status": load_status,
        "status": status,
        "failing_rules": failing_rules,
        "maturity_status": maturity_status,
    }


def _rollback_schema_evidence(vault: Path) -> dict[str, Any]:
    schema_path = vault / ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH
    payload, load_status = _load_json(schema_path)
    required = _as_list(payload.get("required"))
    return {
        "schema_path": ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
        "load_status": load_status,
        "schema_locked": load_status == "ok",
        "required_field_count": len(required),
        "required_fields": [str(item) for item in required],
    }


def _default_gate_readiness(
    outcome: dict[str, Any],
    routing: dict[str, Any],
    supply_chain: dict[str, Any],
    rollback_schema: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if outcome["load_status"] != "ok":
        blockers.append("outcome_metrics_missing")
    if outcome["rollback_signal_count"] > outcome["rollback_rehearsal_coverage_count"]:
        blockers.append("rollback_rehearsal_coverage_gap")
    if outcome["defect_escape_count"]:
        blockers.append("defect_escape_signal_unclosed")
    if routing["status"] != "pass":
        blockers.append("routing_provenance_not_clean")
    if supply_chain["maturity_status"] != "pass":
        blockers.append("supply_chain_gate_not_clean")
    if not rollback_schema["schema_locked"]:
        blockers.append("rollback_rehearsal_schema_unavailable")
    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "next_mode": "default_gate_candidate" if not blockers else "remain_audit_or_optional_strict",
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    outcome = _outcome_evidence(resolved_vault)
    routing = _routing_provenance_evidence(resolved_vault)
    supply_chain = _supply_chain_gate_evidence(resolved_vault)
    rollback_schema = _rollback_schema_evidence(resolved_vault)
    readiness = _default_gate_readiness(outcome, routing, supply_chain, rollback_schema)
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="outcome_provenance_gate_policy",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/outcome_provenance_gate_policy.py",
                "ops/scripts/outcome_metrics.py",
                "ops/scripts/observability_routing_provenance_runtime.py",
                "ops/scripts/supply_chain_gate_runtime.py",
                ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
            ],
            file_inputs={
                "outcome_metrics": OUTCOME_METRICS_PATH,
                "supply_chain_gate": SUPPLY_CHAIN_GATE_PATH,
                "rollback_rehearsal_schema": ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
            },
            path_group_inputs={
                "routing_provenance_aggregates": [
                    report_path(resolved_vault, path)
                    for path in sorted(resolved_vault.glob(ROUTING_AGGREGATE_GLOB))
                    if path.is_file()
                ]
            },
            text_inputs={
                "escalation_conditions": json.dumps(
                    ESCALATION_CONDITIONS,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "status": "pass" if readiness["status"] == "ready" else "attention",
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "current_policy_mode": "audit_only",
        "recommended_next_mode": readiness["next_mode"],
        "summary": {
            "escalation_condition_count": len(ESCALATION_CONDITIONS),
            "default_gate_blocker_count": len(readiness["blockers"]),
            "routing_aggregate_count": routing["aggregate_count"],
            "rollback_signal_count": outcome["rollback_signal_count"],
            "rollback_rehearsal_coverage_count": outcome["rollback_rehearsal_coverage_count"],
            "defect_escape_count": outcome["defect_escape_count"],
        },
        "promotion_blocker_escalation_conditions": ESCALATION_CONDITIONS,
        "evidence": {
            "outcome_metrics": outcome,
            "routing_provenance": routing,
            "supply_chain_gate": supply_chain,
            "rollback_rehearsal_schema": rollback_schema,
        },
        "default_gate_readiness": readiness,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="outcome provenance gate policy schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize outcome/provenance promotion gate escalation readiness.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
