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
