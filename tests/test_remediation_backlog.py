from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ops.scripts.remediation_backlog import build_report, write_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


pytestmark = pytest.mark.public


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 0, 0, tzinfo=dt.timezone.utc),
    )


def test_remediation_backlog_extracts_readiness_remediations_and_repeated_blockers(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    report_path = vault / "ops" / "reports" / "auto-improve-readiness.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "remediations": [
                    {
                        "blocker": "recent_log_overlap",
                        "blocker_kind": "loop_health",
                        "remediation_code": "convert_to_backlog",
                        "retry_condition": "write explicit remediation evidence",
                        "minimum_evidence": ["ops/reports/remediation-backlog.json"],
                    }
                ],
                "blockers": [
                    {
                        "id": "fallback_target_history_depth",
                        "scope": "history",
                        "required_evidence": ["outcome metrics history"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_report(vault, context=fixed_context())
    out_path = write_report(vault, report)
    persisted = json.loads(out_path.read_text(encoding="utf-8"))
    schema = load_schema(vault / "ops" / "schemas" / "remediation-backlog.schema.json")

    assert validate_with_schema(persisted, schema) == []
    assert persisted["status"] == "attention"
    assert persisted["summary"] == {"open_item_count": 2, "repeated_blocker_count": 2}
    assert [item["blocker"] for item in persisted["items"]] == [
        "recent_log_overlap",
        "fallback_target_history_depth",
    ]


def test_remediation_backlog_promotes_repeated_goal_audit_blockers(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    reports_dir = vault / "ops" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "auto-improve-readiness.json").write_text(
        json.dumps({"remediations": [], "blockers": []}),
        encoding="utf-8",
    )
    audit_events = [
        {
            "ts": "2026-05-15T19:10:36Z",
            "goal_id": "goal-20260515-5day-auto-improve-runtime",
            "event": "goal_run_executor_backoff",
            "reason": (
                "profile=30-minute-trial; executor_usage_limited_backoff; "
                "retry_after=May 20th, 2026 2:21 PM"
            ),
            "status": "running",
            "active_profile": "30-minute-trial",
        },
        {
            "ts": "2026-05-15T19:39:16Z",
            "goal_id": "goal-20260515-5day-auto-improve-runtime",
            "event": "goal_run_executor_backoff",
            "reason": (
                "profile=6-hour-ramp; executor_usage_limited_backoff; "
                "retry_after=May 20th, 2026 2:21 PM"
            ),
            "status": "running",
            "active_profile": "6-hour-ramp",
        },
    ]
    (reports_dir / "goal-audit-log.jsonl").write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in audit_events) + "\n",
        encoding="utf-8",
    )

    report = build_report(vault, context=fixed_context())
    out_path = write_report(vault, report)
    persisted = json.loads(out_path.read_text(encoding="utf-8"))
    schema = load_schema(vault / "ops" / "schemas" / "remediation-backlog.schema.json")

    assert validate_with_schema(persisted, schema) == []
    assert persisted["status"] == "attention"
    assert persisted["summary"] == {"open_item_count": 1, "repeated_blocker_count": 1}
    assert persisted["items"][0] == {
        "id": "goal-audit-repeated-executor_usage_limited",
        "source": "goal_audit_log.repeated_blocker",
        "blocker": "executor_usage_limited",
        "blocker_kind": "goal_runtime_audit",
        "status": "open",
        "remediation_code": "convert_repeated_goal_runtime_blocker",
        "recommended_next_step": (
            "Convert the repeated goal runtime blocker into explicit remediation "
            "evidence before resuming or escalating the sustained profile."
        ),
        "minimum_evidence": [
            "ops/reports/goal-audit-log.jsonl",
            "ops/reports/goal-run-status.json",
            "ops/reports/remediation-backlog.json",
        ],
    }
    assert "goal_audit_log" in persisted["input_fingerprints"]
