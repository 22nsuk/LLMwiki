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
