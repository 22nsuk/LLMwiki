from __future__ import annotations

from typing import Any

from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_BLOCKS_PROMOTION,
    GATE_EFFECT_NONE,
)


def artifact_freshness_gate_record(
    *,
    component: dict[str, Any],
    payload: dict[str, Any],
    stable_contract_debt_only: bool,
    release_owned_attention: bool,
) -> dict[str, Any]:
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    schema_invalid_count = int(summary.get("schema_invalid_artifact_count", 0) or 0)
    stable_debt_count = int(summary.get("stable_contract_debt_issue_count", 0) or 0)
    status = str(payload.get("status", component.get("source_status", "unknown"))).strip() or "unknown"
    if status == "pass":
        gate_effect = GATE_EFFECT_ADVISORY if schema_invalid_count > 0 else GATE_EFFECT_NONE
    elif status == "attention":
        if stable_contract_debt_only or release_owned_attention:
            gate_effect = GATE_EFFECT_ADVISORY
        else:
            gate_effect = GATE_EFFECT_NONE
    else:
        gate_effect = GATE_EFFECT_BLOCKS_PROMOTION

    if gate_effect == GATE_EFFECT_NONE:
        display_effect = "none"
    elif gate_effect == GATE_EFFECT_ADVISORY:
        display_effect = "advisory"
    else:
        display_effect = "blocking"

    blocking = display_effect == "blocking"
    ready = bool(component.get("ready")) and not blocking
    return {
        "path": "ops/reports/artifact-freshness-report.json",
        "load_status": str(component.get("load_status", "missing")).strip() or "missing",
        "status": status,
        "ready": ready,
        "schema_invalid_artifact_count": schema_invalid_count,
        "stable_contract_debt_issue_count": stable_debt_count,
        "gate_effect": gate_effect,
        "display_effect": display_effect,
        "blocking": blocking,
    }
