from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.self_improvement_negative_lessons import build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault


pytestmark = pytest.mark.public


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 15, 0, 0, tzinfo=dt.timezone.utc),
    )


def test_negative_learning_ledger_is_extracted_as_schema_backed_report(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    activation_path = vault / "ops" / "reports" / "learning_claim_activation_report.json"
    activation_path.parent.mkdir(parents=True, exist_ok=True)
    activation_path.write_text(
        json.dumps(
            {
                "negative_learning_ledger": {
                    "patterns": [
                        {
                            "id": "same_failure_repeated",
                            "status": "open",
                            "summary": "same failure repeated without promotion evidence",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_report(vault, context=fixed_context())
    out_path = write_report(vault, report)
    persisted = json.loads(out_path.read_text(encoding="utf-8"))
    schema = load_schema(
        vault / "ops" / "schemas" / "self-improvement-negative-lessons.schema.json"
    )

    assert validate_with_schema(persisted, schema) == []
    assert persisted["status"] == "attention"
    assert persisted["summary"]["pattern_count"] == 1
    assert persisted["patterns"][0]["id"] == "same_failure_repeated"


def test_repeated_goal_backlog_item_becomes_negative_lesson(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    reports_dir = vault / "ops" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "learning_claim_activation_report.json").write_text(
        json.dumps({"negative_learning_ledger": {"patterns": []}}),
        encoding="utf-8",
    )
    (reports_dir / "remediation-backlog.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/remediation-backlog.schema.json",
                "artifact_kind": "remediation_backlog",
                "status": "attention",
                "source_readiness_report": "ops/reports/auto-improve-readiness.json",
                "summary": {"open_item_count": 1, "repeated_blocker_count": 1},
                "items": [
                    {
                        "id": "goal-audit-repeated-executor_usage_limited",
                        "source": "goal_audit_log.repeated_blocker",
                        "blocker": "executor_usage_limited",
                        "blocker_kind": "goal_runtime_audit",
                        "status": "open",
                        "remediation_code": "convert_repeated_goal_runtime_blocker",
                        "recommended_next_step": (
                            "Convert the repeated goal runtime blocker into explicit "
                            "remediation evidence before resuming the sustained profile."
                        ),
                        "minimum_evidence": [
                            "ops/reports/goal-audit-log.jsonl",
                            "ops/reports/remediation-backlog.json",
                        ],
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
    schema = load_schema(
        vault / "ops" / "schemas" / "self-improvement-negative-lessons.schema.json"
    )

    assert validate_with_schema(persisted, schema) == []
    assert persisted["status"] == "attention"
    assert persisted["summary"]["pattern_count"] == 1
    assert persisted["patterns"][0]["id"] == "remediation-backlog-executor_usage_limited"
    assert persisted["patterns"][0]["source"] == "remediation_backlog"
    assert persisted["patterns"][0]["evidence_paths"] == [
        "ops/reports/goal-audit-log.jsonl",
        "ops/reports/remediation-backlog.json",
    ]
    assert "remediation_backlog" in persisted["input_fingerprints"]
