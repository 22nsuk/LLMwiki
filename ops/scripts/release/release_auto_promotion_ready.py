#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.release.release_run_manifest import (
    DEFAULT_OUT as DEFAULT_RUN_MANIFEST,
)
from ops.scripts.release.release_run_manifest import (
    _resolve,
    git_commit,
)
from ops.scripts.release.release_sealed_run_manifest import (
    DEFAULT_OUT as DEFAULT_SEALED_RUN_MANIFEST,
)
from ops.scripts.release.release_sealed_run_manifest import (
    _json_identity,
    _unique_failures,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

DEFAULT_OUT = "build/release/release-auto-promotion-ready-manifest.json"
SCHEMA_PATH = "ops/schemas/release-auto-promotion-ready-manifest.schema.json"
PRODUCER = "ops.scripts.release_auto_promotion_ready"
SOURCE_COMMAND = "python -m ops.scripts.release_auto_promotion_ready --vault ."
DEFAULT_OPERATOR_SUMMARY = "build/release/operator-release-summary.json"
DEFAULT_AUTO_IMPROVE_READINESS = "ops/reports/auto-improve-readiness.json"
DEFAULT_AUTO_PROMOTION_PREFLIGHT = "build/release/release-auto-promotion-preflight.json"
DEFAULT_AUTO_PROMOTION_PRESEAL = "build/release/release-auto-promotion-preseal.json"
ALLOWED_LEARNING_REVALIDATION_STATUSES = {
    "current",
    "fresh",
    "metrics_close_candidate",
    "not_required",
    "pass",
}
STRICT_ZERO_ACCEPTED_RISK_FIELDS = (
    "accepted_risk_count",
    "release_accepted_risk_count",
    "accepted_learning_risk_count",
    "clean_lane_blocking_accepted_risk_family_count",
)
STRICT_ZERO_GATE_ATTENTION_FIELDS = (
    "gate_attention_count",
)
STRICT_ZERO_LEARNING_CLAIM_FIELDS = (
    "learning_claim_blocking_family_count",
)


def _dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _list(payload: Any) -> list[Any]:
    return payload if isinstance(payload, list) else []


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _load_report(vault: Path, path_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _resolve(vault, path_value)
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    if diagnostics.get("status") != "ok":
        payload = {}
    return payload, diagnostics


def _blocker(
    *,
    blocker_id: str,
    source: str,
    field_path: str,
    observed: Any,
    expected: str,
    summary: str,
    recommended_next_step: str,
) -> dict[str, Any]:
    return {
        "id": blocker_id,
        "source": source,
        "field_path": field_path,
        "observed": str(observed),
        "expected": expected,
        "summary": summary,
        "recommended_next_step": recommended_next_step,
    }


def _require(
    blockers: list[dict[str, Any]],
    *,
    passed: bool,
    blocker_id: str,
    source: str,
    field_path: str,
    observed: Any,
    expected: str,
    summary: str,
    recommended_next_step: str,
) -> None:
    if passed:
        return
    blockers.append(
        _blocker(
            blocker_id=blocker_id,
            source=source,
            field_path=field_path,
            observed=observed,
            expected=expected,
            summary=summary,
            recommended_next_step=recommended_next_step,
        )
    )


def _operator_count_group(operator_summary: dict[str, Any], fields: tuple[str, ...]) -> dict[str, int]:
    accepted_risk = _dict(operator_summary.get("accepted_risk"))
    return {field: _int_value(accepted_risk.get(field, 0)) for field in fields}


def _release_gate_diagnostic_blockers(blockers: list[Any]) -> list[dict[str, Any]]:
    return [
        blocker
        for blocker in (_dict(item) for item in blockers)
        if str(blocker.get("scope", "")).strip() == "release_gate"
    ]


def _stage3_blocking_promotion_blockers(blockers: list[Any]) -> list[dict[str, Any]]:
    return [
        blocker
        for blocker in (_dict(item) for item in blockers)
        if str(blocker.get("scope", "")).strip() != "release_gate"
    ]


def _operator_diagnostics(operator_summary: dict[str, Any]) -> dict[str, Any]:
    test_evidence = _dict(operator_summary.get("test_evidence"))
    learning_readiness = _dict(operator_summary.get("learning_readiness"))
    return {
        "status": str(operator_summary.get("status", "")).strip(),
        "source_zip_policy_status": str(operator_summary.get("source_zip_policy_status", "")).strip(),
        "tmp_json_policy_status": str(operator_summary.get("tmp_json_policy_status", "")).strip(),
        "artifact_digest_policy_status": str(operator_summary.get("artifact_digest_policy_status", "")).strip(),
        "batch_verify_status": str(_dict(operator_summary.get("batch_verify")).get("status", "")).strip(),
        "full_suite_status": str(test_evidence.get("full_suite_status", "")).strip(),
        "learning_revalidation_status": str(learning_readiness.get("revalidation_status", "")).strip(),
        "accepted_risk": _operator_count_group(operator_summary, STRICT_ZERO_ACCEPTED_RISK_FIELDS),
        "gate_attention": _operator_count_group(operator_summary, STRICT_ZERO_GATE_ATTENTION_FIELDS),
        "learning_claim": _operator_count_group(operator_summary, STRICT_ZERO_LEARNING_CLAIM_FIELDS),
    }


def _auto_improve_diagnostics(
    auto_improve_readiness: dict[str, Any],
    *,
    current_fingerprint: str,
) -> dict[str, Any]:
    learning_claim_blockers = _list(auto_improve_readiness.get("learning_claim_blockers"))
    promotion_blockers = _list(auto_improve_readiness.get("promotion_blockers"))
    clean_release_blockers = _list(auto_improve_readiness.get("clean_release_blockers"))
    stage3_promotion_blockers = _stage3_blocking_promotion_blockers(promotion_blockers)
    release_gate_diagnostic_blockers = _release_gate_diagnostic_blockers(promotion_blockers)
    report_fingerprint = str(auto_improve_readiness.get("source_tree_fingerprint", "")).strip()
    can_execute_trial = bool(auto_improve_readiness.get("can_execute_trial", False))
    return {
        "source_tree_fingerprint": report_fingerprint,
        "currentness_status": "current" if report_fingerprint == current_fingerprint else "stale",
        "can_execute_trial": can_execute_trial,
        "can_promote_result": bool(auto_improve_readiness.get("can_promote_result", False)),
        "stage3_can_promote_result": can_execute_trial and not stage3_promotion_blockers,
        "learning_claim_blocker_count": len(learning_claim_blockers),
        "promotion_blocker_count": len(promotion_blockers),
        "stage3_blocking_promotion_blocker_count": len(stage3_promotion_blockers),
        "release_gate_diagnostic_promotion_blocker_count": len(release_gate_diagnostic_blockers),
        "clean_release_blocker_count": len(clean_release_blockers),
    }


def _preflight_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    goal_run_identity = _dict(payload.get("goal_run_identity"))
    return {
        "phase": str(payload.get("phase", "")).strip(),
        "status": str(payload.get("status", "")).strip(),
        "blocker_count": len(_list(payload.get("blockers"))),
        "goal_run_identity": {
            "status": str(goal_run_identity.get("status", "")).strip(),
            "requested_run_id": str(goal_run_identity.get("requested_run_id", "")).strip(),
            "effective_run_id": str(goal_run_identity.get("effective_run_id", "")).strip(),
            "inferred_run_id": str(goal_run_identity.get("inferred_run_id", "")).strip(),
            "selection_mode": str(goal_run_identity.get("selection_mode", "")).strip(),
            "goal_run_id_origin": str(goal_run_identity.get("goal_run_id_origin", "")).strip(),
            "failure_count": _int_value(goal_run_identity.get("failure_count", 0)),
        },
    }


def build_manifest(
    vault: Path,
    *,
    run_manifest: str = DEFAULT_RUN_MANIFEST,
    sealed_run_manifest: str = DEFAULT_SEALED_RUN_MANIFEST,
    operator_summary: str = DEFAULT_OPERATOR_SUMMARY,
    auto_improve_readiness: str = DEFAULT_AUTO_IMPROVE_READINESS,
    auto_promotion_preflight: str = DEFAULT_AUTO_PROMOTION_PREFLIGHT,
    auto_promotion_preseal: str = DEFAULT_AUTO_PROMOTION_PRESEAL,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    commit = git_commit(vault)
    inputs = {
        "run_manifest": _json_identity(vault, run_manifest),
        "sealed_run_manifest": _json_identity(vault, sealed_run_manifest),
        "operator_summary": _json_identity(vault, operator_summary),
        "auto_improve_readiness": _json_identity(vault, auto_improve_readiness),
        "auto_promotion_preflight": _json_identity(vault, auto_promotion_preflight),
        "auto_promotion_preseal": _json_identity(vault, auto_promotion_preseal),
    }
    run_payload, _run_diagnostics = _load_report(vault, run_manifest)
    sealed_payload, _sealed_diagnostics = _load_report(vault, sealed_run_manifest)
    operator_payload, _operator_diagnostics_load = _load_report(vault, operator_summary)
    auto_payload, _auto_diagnostics_load = _load_report(vault, auto_improve_readiness)
    preflight_payload, _preflight_diagnostics_load = _load_report(vault, auto_promotion_preflight)
    preseal_payload, _preseal_diagnostics_load = _load_report(vault, auto_promotion_preseal)

    operator = _operator_diagnostics(operator_payload)
    auto_improve = _auto_improve_diagnostics(auto_payload, current_fingerprint=fingerprint)
    preflight = _preflight_diagnostics(preflight_payload)
    preseal = _preflight_diagnostics(preseal_payload)
    preflight_goal_identity = _dict(preflight.get("goal_run_identity"))
    preseal_goal_identity = _dict(preseal.get("goal_run_identity"))
    preflight_goal_run_id = str(preflight_goal_identity.get("effective_run_id", "")).strip()
    preseal_goal_run_id = str(preseal_goal_identity.get("effective_run_id", "")).strip()
    accepted_risk_clean = all(count == 0 for count in operator["accepted_risk"].values())
    gate_attention_clean = all(count == 0 for count in operator["gate_attention"].values())
    learning_claim_clean = all(count == 0 for count in operator["learning_claim"].values())
    learning_revalidation_status = str(operator["learning_revalidation_status"])
    checks = {
        "auto_promotion_preflight_load_ok": inputs["auto_promotion_preflight"]["load_status"]
        == "ok",
        "auto_promotion_preflight_artifact_kind_ok": (
            inputs["auto_promotion_preflight"]["artifact_kind"]
            == "release_auto_promotion_preflight"
        ),
        "auto_promotion_preflight_current": (
            inputs["auto_promotion_preflight"]["source_tree_fingerprint"] == fingerprint
        ),
        "auto_promotion_preflight_phase_ok": preflight["phase"] == "preflight",
        "auto_promotion_preflight_pass": preflight["status"] == "pass",
        "auto_promotion_preflight_goal_run_identity_present": bool(preflight_goal_run_id),
        "auto_promotion_preflight_goal_run_identity_pass": (
            preflight_goal_identity.get("status") == "pass"
            and _int_value(preflight_goal_identity.get("failure_count", 0)) == 0
        ),
        "auto_promotion_preseal_load_ok": inputs["auto_promotion_preseal"]["load_status"] == "ok",
        "auto_promotion_preseal_artifact_kind_ok": (
            inputs["auto_promotion_preseal"]["artifact_kind"] == "release_auto_promotion_preflight"
        ),
        "auto_promotion_preseal_current": (
            inputs["auto_promotion_preseal"]["source_tree_fingerprint"] == fingerprint
        ),
        "auto_promotion_preseal_phase_ok": preseal["phase"] == "preseal",
        "auto_promotion_preseal_pass": preseal["status"] == "pass",
        "auto_promotion_preseal_goal_run_identity_present": bool(preseal_goal_run_id),
        "auto_promotion_preseal_goal_run_identity_pass": (
            preseal_goal_identity.get("status") == "pass"
            and _int_value(preseal_goal_identity.get("failure_count", 0)) == 0
        ),
        "auto_promotion_goal_run_identity_match": (
            bool(preflight_goal_run_id)
            and bool(preseal_goal_run_id)
            and preflight_goal_run_id == preseal_goal_run_id
        ),
        "run_manifest_load_ok": inputs["run_manifest"]["load_status"] == "ok",
        "run_manifest_artifact_kind_ok": inputs["run_manifest"]["artifact_kind"] == "release_run_manifest",
        "run_manifest_current": inputs["run_manifest"]["source_tree_fingerprint"] == fingerprint,
        "run_manifest_pass": str(run_payload.get("status", "")).strip() == "pass",
        "sealed_run_manifest_load_ok": inputs["sealed_run_manifest"]["load_status"] == "ok",
        "sealed_run_manifest_artifact_kind_ok": (
            inputs["sealed_run_manifest"]["artifact_kind"] == "release_sealed_run_manifest"
        ),
        "sealed_run_manifest_current": inputs["sealed_run_manifest"]["source_tree_fingerprint"] == fingerprint,
        "sealed_run_manifest_pass": str(sealed_payload.get("status", "")).strip() == "pass",
        "operator_summary_load_ok": inputs["operator_summary"]["load_status"] == "ok",
        "operator_summary_artifact_kind_ok": (
            inputs["operator_summary"]["artifact_kind"] == "operator_release_summary"
        ),
        "operator_summary_current": str(inputs["operator_summary"]["source_tree_fingerprint"]).strip()
        == fingerprint,
        "operator_summary_pass": operator["status"] == "pass",
        "source_zip_policy_match": operator["source_zip_policy_status"] == "match",
        "tmp_json_clean": operator["tmp_json_policy_status"] == "clean",
        "artifact_digest_policy_match": operator["artifact_digest_policy_status"] == "match",
        "batch_verify_pass": operator["batch_verify_status"] == "pass",
        "full_suite_pass": operator["full_suite_status"] == "pass",
        "learning_revalidation_current": learning_revalidation_status
        in ALLOWED_LEARNING_REVALIDATION_STATUSES,
        "accepted_risk_clean": accepted_risk_clean,
        "gate_attention_clean": gate_attention_clean,
        "learning_claim_clean": learning_claim_clean,
        "auto_improve_readiness_load_ok": inputs["auto_improve_readiness"]["load_status"] == "ok",
        "auto_improve_readiness_artifact_kind_ok": (
            inputs["auto_improve_readiness"]["artifact_kind"] == "auto_improve_readiness_report"
        ),
        "auto_improve_current": auto_improve["currentness_status"] == "current",
        "auto_improve_can_execute_trial": bool(auto_improve["can_execute_trial"]),
        "auto_improve_can_promote_result": bool(auto_improve["stage3_can_promote_result"]),
        "auto_improve_blockers_clear": (
            int(auto_improve["learning_claim_blocker_count"]) == 0
            and int(auto_improve["stage3_blocking_promotion_blocker_count"]) == 0
            and int(auto_improve["clean_release_blocker_count"]) == 0
        ),
    }

    blockers: list[dict[str, Any]] = []
    preflight_requirements = (
        (
            "auto_promotion_preflight_not_loadable",
            "auto_promotion_preflight",
            "$.load_status",
            inputs["auto_promotion_preflight"]["load_status"],
            "ok",
            checks["auto_promotion_preflight_load_ok"],
            "Auto-promotion preflight evidence is missing or invalid.",
            "Run make release-auto-promotion-preflight before release-run-ready.",
        ),
        (
            "auto_promotion_preflight_artifact_kind_invalid",
            "auto_promotion_preflight",
            "$.artifact_kind",
            inputs["auto_promotion_preflight"]["artifact_kind"],
            "release_auto_promotion_preflight",
            checks["auto_promotion_preflight_artifact_kind_ok"],
            "Auto-promotion preflight evidence has an unexpected artifact kind.",
            "Regenerate auto-promotion preflight evidence.",
        ),
        (
            "auto_promotion_preflight_stale",
            "auto_promotion_preflight",
            "$.source_tree_fingerprint",
            inputs["auto_promotion_preflight"]["source_tree_fingerprint"],
            fingerprint,
            checks["auto_promotion_preflight_current"],
            "Auto-promotion preflight evidence does not describe the current source tree.",
            "Run make release-auto-promotion-preflight before release-run-ready.",
        ),
        (
            "auto_promotion_preflight_phase_invalid",
            "auto_promotion_preflight",
            "$.phase",
            preflight["phase"],
            "preflight",
            checks["auto_promotion_preflight_phase_ok"],
            "Auto-promotion preflight evidence was written for the wrong phase.",
            "Regenerate it with make release-auto-promotion-preflight.",
        ),
        (
            "auto_promotion_preflight_not_pass",
            "auto_promotion_preflight",
            "$.status",
            preflight["status"],
            "pass",
            checks["auto_promotion_preflight_pass"],
            "Auto-promotion preflight has blockers that should be cleared before run-ready.",
            "Resolve preflight blockers before spending run-ready cycles.",
        ),
        (
            "auto_promotion_preflight_goal_run_identity_missing",
            "auto_promotion_preflight",
            "$.goal_run_identity.effective_run_id",
            preflight_goal_run_id,
            "non-empty run id",
            checks["auto_promotion_preflight_goal_run_identity_present"],
            "Auto-promotion preflight does not bind a selected goal run id.",
            "Regenerate it with make release-auto-promotion-preflight and explicit GOAL_RUN_ID.",
        ),
        (
            "auto_promotion_preflight_goal_run_identity_not_pass",
            "auto_promotion_preflight",
            "$.goal_run_identity.status|$.goal_run_identity.failure_count",
            (
                f"status={preflight_goal_identity.get('status', '')};"
                f"failures={preflight_goal_identity.get('failure_count', '')}"
            ),
            "status=pass; failures=0",
            checks["auto_promotion_preflight_goal_run_identity_pass"],
            "Auto-promotion preflight goal-run identity evidence is not passing.",
            "Regenerate it after make release-auto-promotion-goal-run-id-guard passes.",
        ),
        (
            "auto_promotion_preseal_not_loadable",
            "auto_promotion_preseal",
            "$.load_status",
            inputs["auto_promotion_preseal"]["load_status"],
            "ok",
            checks["auto_promotion_preseal_load_ok"],
            "Auto-promotion preseal evidence is missing or invalid.",
            "Run make release-auto-promotion-preseal after release-run-ready.",
        ),
        (
            "auto_promotion_preseal_artifact_kind_invalid",
            "auto_promotion_preseal",
            "$.artifact_kind",
            inputs["auto_promotion_preseal"]["artifact_kind"],
            "release_auto_promotion_preflight",
            checks["auto_promotion_preseal_artifact_kind_ok"],
            "Auto-promotion preseal evidence has an unexpected artifact kind.",
            "Regenerate auto-promotion preseal evidence.",
        ),
        (
            "auto_promotion_preseal_stale",
            "auto_promotion_preseal",
            "$.source_tree_fingerprint",
            inputs["auto_promotion_preseal"]["source_tree_fingerprint"],
            fingerprint,
            checks["auto_promotion_preseal_current"],
            "Auto-promotion preseal evidence does not describe the current source tree.",
            "Run make release-auto-promotion-preseal before release-sealed-run-ready.",
        ),
        (
            "auto_promotion_preseal_phase_invalid",
            "auto_promotion_preseal",
            "$.phase",
            preseal["phase"],
            "preseal",
            checks["auto_promotion_preseal_phase_ok"],
            "Auto-promotion preseal evidence was written for the wrong phase.",
            "Regenerate it with make release-auto-promotion-preseal.",
        ),
        (
            "auto_promotion_preseal_not_pass",
            "auto_promotion_preseal",
            "$.status",
            preseal["status"],
            "pass",
            checks["auto_promotion_preseal_pass"],
            "Auto-promotion preseal has blockers that should be cleared before sealing.",
            "Resolve preseal blockers before spending sealed-run-ready cycles.",
        ),
        (
            "auto_promotion_preseal_goal_run_identity_missing",
            "auto_promotion_preseal",
            "$.goal_run_identity.effective_run_id",
            preseal_goal_run_id,
            "non-empty run id",
            checks["auto_promotion_preseal_goal_run_identity_present"],
            "Auto-promotion preseal does not bind a selected goal run id.",
            "Regenerate it with make release-auto-promotion-preseal and explicit GOAL_RUN_ID.",
        ),
        (
            "auto_promotion_preseal_goal_run_identity_not_pass",
            "auto_promotion_preseal",
            "$.goal_run_identity.status|$.goal_run_identity.failure_count",
            (
                f"status={preseal_goal_identity.get('status', '')};"
                f"failures={preseal_goal_identity.get('failure_count', '')}"
            ),
            "status=pass; failures=0",
            checks["auto_promotion_preseal_goal_run_identity_pass"],
            "Auto-promotion preseal goal-run identity evidence is not passing.",
            "Regenerate it after make release-auto-promotion-goal-run-id-guard passes.",
        ),
        (
            "auto_promotion_goal_run_identity_mismatch",
            "auto_promotion_preflight|auto_promotion_preseal",
            "$.goal_run_identity.effective_run_id",
            f"preflight={preflight_goal_run_id}; preseal={preseal_goal_run_id}",
            "matching non-empty run ids",
            checks["auto_promotion_goal_run_identity_match"],
            "Auto-promotion preflight and preseal were generated for different goal runs.",
            "Regenerate preflight and preseal with the same explicit GOAL_RUN_ID.",
        ),
    )
    for (
        blocker_id,
        source,
        field_path,
        observed,
        expected,
        passed,
        summary,
        recommended_next_step,
    ) in preflight_requirements:
        _require(
            blockers,
            passed=passed,
            blocker_id=blocker_id,
            source=source,
            field_path=field_path,
            observed=observed,
            expected=expected,
            summary=summary,
            recommended_next_step=recommended_next_step,
        )
    _require(
        blockers,
        passed=checks["run_manifest_load_ok"],
        blocker_id="run_manifest_not_loadable",
        source="release_run_manifest",
        field_path="$.load_status",
        observed=inputs["run_manifest"]["load_status"],
        expected="ok",
        summary="The runnable release manifest is missing or not valid JSON.",
        recommended_next_step="Run make release-run-ready.",
    )
    _require(
        blockers,
        passed=checks["run_manifest_artifact_kind_ok"],
        blocker_id="run_manifest_artifact_kind_invalid",
        source="release_run_manifest",
        field_path="$.artifact_kind",
        observed=inputs["run_manifest"]["artifact_kind"],
        expected="release_run_manifest",
        summary="The runnable release manifest has an unexpected artifact kind.",
        recommended_next_step="Regenerate release-run-ready evidence.",
    )
    _require(
        blockers,
        passed=checks["run_manifest_current"],
        blocker_id="run_manifest_stale",
        source="release_run_manifest",
        field_path="$.source_tree_fingerprint",
        observed=inputs["run_manifest"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="The runnable release manifest does not describe the current source tree.",
        recommended_next_step="Run make release-run-ready.",
    )
    _require(
        blockers,
        passed=checks["run_manifest_pass"],
        blocker_id="run_manifest_not_pass",
        source="release_run_manifest",
        field_path="$.status",
        observed=run_payload.get("status", ""),
        expected="pass",
        summary="The runnable release stage is not passing.",
        recommended_next_step="Run make release-run-ready.",
    )
    _require(
        blockers,
        passed=checks["sealed_run_manifest_load_ok"],
        blocker_id="sealed_run_manifest_not_loadable",
        source="release_sealed_run_manifest",
        field_path="$.load_status",
        observed=inputs["sealed_run_manifest"]["load_status"],
        expected="ok",
        summary="The sealed release manifest is missing or not valid JSON.",
        recommended_next_step="Run make release-sealed-run-ready.",
    )
    _require(
        blockers,
        passed=checks["sealed_run_manifest_artifact_kind_ok"],
        blocker_id="sealed_run_manifest_artifact_kind_invalid",
        source="release_sealed_run_manifest",
        field_path="$.artifact_kind",
        observed=inputs["sealed_run_manifest"]["artifact_kind"],
        expected="release_sealed_run_manifest",
        summary="The sealed release manifest has an unexpected artifact kind.",
        recommended_next_step="Regenerate sealed release evidence.",
    )
    _require(
        blockers,
        passed=checks["sealed_run_manifest_current"],
        blocker_id="sealed_run_manifest_stale",
        source="release_sealed_run_manifest",
        field_path="$.source_tree_fingerprint",
        observed=inputs["sealed_run_manifest"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="The sealed release manifest does not describe the current source tree.",
        recommended_next_step="Run make release-sealed-run-ready.",
    )
    _require(
        blockers,
        passed=checks["sealed_run_manifest_pass"],
        blocker_id="sealed_run_manifest_not_pass",
        source="release_sealed_run_manifest",
        field_path="$.status",
        observed=sealed_payload.get("status", ""),
        expected="pass",
        summary="The sealed release evidence stage is not passing.",
        recommended_next_step="Run make release-sealed-run-ready.",
    )
    _require(
        blockers,
        passed=checks["operator_summary_load_ok"],
        blocker_id="operator_summary_not_loadable",
        source="operator_release_summary",
        field_path="$.load_status",
        observed=inputs["operator_summary"]["load_status"],
        expected="ok",
        summary="Operator diagnostics are missing or not valid JSON.",
        recommended_next_step="Regenerate the operator release summary.",
    )
    _require(
        blockers,
        passed=checks["operator_summary_artifact_kind_ok"],
        blocker_id="operator_summary_artifact_kind_invalid",
        source="operator_release_summary",
        field_path="$.artifact_kind",
        observed=inputs["operator_summary"]["artifact_kind"],
        expected="operator_release_summary",
        summary="Operator diagnostics have an unexpected artifact kind.",
        recommended_next_step="Regenerate the operator release summary.",
    )
    _require(
        blockers,
        passed=checks["operator_summary_current"],
        blocker_id="operator_summary_stale",
        source="operator_release_summary",
        field_path="$.source_tree_fingerprint",
        observed=inputs["operator_summary"]["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Operator diagnostics do not describe the current source tree.",
        recommended_next_step="Regenerate the operator release summary.",
    )
    _require(
        blockers,
        passed=checks["operator_summary_pass"],
        blocker_id="operator_attention_open",
        source="operator_release_summary",
        field_path="$.status",
        observed=operator["status"],
        expected="pass",
        summary="Operator diagnostics still require attention.",
        recommended_next_step="Clear operator-release-summary attention before unattended promotion.",
    )
    operator_requirements = (
        (
            "source_zip_policy_not_match",
            "source_zip_policy_status",
            "match",
            checks["source_zip_policy_match"],
            "Source ZIP policy is not a digest match.",
        ),
        (
            "tmp_json_not_clean",
            "tmp_json_policy_status",
            "clean",
            checks["tmp_json_clean"],
            "Temporary JSON policy is not clean.",
        ),
        (
            "artifact_digest_policy_not_match",
            "artifact_digest_policy_status",
            "match",
            checks["artifact_digest_policy_match"],
            "Artifact digest policy is not a match.",
        ),
        (
            "batch_verify_not_pass",
            "batch_verify_status",
            "pass",
            checks["batch_verify_pass"],
            "Operator batch verification is not passing.",
        ),
        (
            "full_suite_not_pass",
            "full_suite_status",
            "pass",
            checks["full_suite_pass"],
            "Full test-suite evidence is not passing.",
        ),
    )
    for blocker_id, key, expected, passed, summary in operator_requirements:
        _require(
            blockers,
            passed=passed,
            blocker_id=blocker_id,
            source="operator_release_summary",
            field_path=f"$.{key}",
            observed=operator[key],
            expected=expected,
            summary=summary,
            recommended_next_step="Refresh release evidence, then regenerate the operator release summary.",
        )
    _require(
        blockers,
        passed=checks["learning_revalidation_current"],
        blocker_id="learning_revalidation_not_current",
        source="operator_release_summary",
        field_path="$.learning_readiness.revalidation_status",
        observed=learning_revalidation_status,
        expected="one of current, fresh, metrics_close_candidate, not_required, pass",
        summary="Learning revalidation is not current enough for unattended promotion.",
        recommended_next_step="Run learning-readiness-signoff-revalidation and refresh operator summary.",
    )
    for field, count in operator["accepted_risk"].items():
        _require(
            blockers,
            passed=count == 0,
            blocker_id=f"{field}_not_zero",
            source="operator_release_summary",
            field_path=f"$.accepted_risk.{field}",
            observed=count,
            expected="0",
            summary=f"{field} must be zero for unattended promotion.",
            recommended_next_step="Resolve or explicitly keep this release out of auto-promotion.",
        )
    for field, count in operator["gate_attention"].items():
        _require(
            blockers,
            passed=count == 0,
            blocker_id=f"{field}_not_zero",
            source="operator_release_summary",
            field_path=f"$.accepted_risk.{field}",
            observed=count,
            expected="0",
            summary=f"{field} must be zero for unattended promotion.",
            recommended_next_step="Resolve gate attention before unattended promotion.",
        )
    for field, count in operator["learning_claim"].items():
        _require(
            blockers,
            passed=count == 0,
            blocker_id=f"{field}_not_zero",
            source="operator_release_summary",
            field_path=f"$.accepted_risk.{field}",
            observed=count,
            expected="0",
            summary=f"{field} must be zero for unattended promotion.",
            recommended_next_step="Resolve or renew learning claim evidence before unattended promotion.",
        )
    _require(
        blockers,
        passed=checks["auto_improve_readiness_load_ok"],
        blocker_id="auto_improve_readiness_not_loadable",
        source="auto_improve_readiness_report",
        field_path="$.load_status",
        observed=inputs["auto_improve_readiness"]["load_status"],
        expected="ok",
        summary="Auto-improve readiness diagnostics are missing or not valid JSON.",
        recommended_next_step="Run make auto-improve-readiness-report-body.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_readiness_artifact_kind_ok"],
        blocker_id="auto_improve_readiness_artifact_kind_invalid",
        source="auto_improve_readiness_report",
        field_path="$.artifact_kind",
        observed=inputs["auto_improve_readiness"]["artifact_kind"],
        expected="auto_improve_readiness_report",
        summary="Auto-improve readiness diagnostics have an unexpected artifact kind.",
        recommended_next_step="Run make auto-improve-readiness-report-body.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_current"],
        blocker_id="auto_improve_readiness_stale",
        source="auto_improve_readiness_report",
        field_path="$.source_tree_fingerprint",
        observed=auto_improve["source_tree_fingerprint"],
        expected=fingerprint,
        summary="Auto-improve readiness does not describe the current source tree.",
        recommended_next_step="Run make auto-improve-readiness-report-body.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_can_execute_trial"],
        blocker_id="auto_improve_trial_not_executable",
        source="auto_improve_readiness_report",
        field_path="$.can_execute_trial",
        observed=auto_improve["can_execute_trial"],
        expected="true",
        summary="Auto-improve lane cannot execute a trial.",
        recommended_next_step="Refresh auto-improve readiness and resolve execution blockers.",
    )
    _require(
        blockers,
        passed=checks["auto_improve_can_promote_result"],
        blocker_id="auto_improve_result_not_promotable",
        source="auto_improve_readiness_report",
        field_path="$.promotion_blockers[?scope!='release_gate']|$.can_execute_trial",
        observed=(
            f"can_execute_trial={auto_improve['can_execute_trial']};"
            f"stage3_blocking_promotion={auto_improve['stage3_blocking_promotion_blocker_count']};"
            f"raw_can_promote_result={auto_improve['can_promote_result']}"
        ),
        expected="true",
        summary="Auto-improve readiness has independent promotion blockers for Stage 3.",
        recommended_next_step=(
            "Resolve non-release-gate auto-improve promotion blockers before unattended promotion."
        ),
    )
    _require(
        blockers,
        passed=checks["auto_improve_blockers_clear"],
        blocker_id="auto_improve_blockers_open",
        source="auto_improve_readiness_report",
        field_path=(
            "$.learning_claim_blockers|$.promotion_blockers[?scope!='release_gate']|"
            "$.clean_release_blockers"
        ),
        observed=(
            "learning_claim="
            f"{auto_improve['learning_claim_blocker_count']};stage3_promotion="
            f"{auto_improve['stage3_blocking_promotion_blocker_count']};"
            f"release_gate_diagnostic="
            f"{auto_improve['release_gate_diagnostic_promotion_blocker_count']};"
            f"clean_release={auto_improve['clean_release_blocker_count']}"
        ),
        expected="all blocker counts are 0",
        summary="Auto-improve readiness still has Stage 3 blocking diagnostics.",
        recommended_next_step=(
            "Resolve learning, non-release-gate promotion, or clean-release blockers listed in "
            "ops/reports/auto-improve-readiness.json."
        ),
    )

    status = "pass" if not blockers else "fail"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_auto_promotion_ready_manifest",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": commit,
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": {key: str(value["sha256"]) for key, value in inputs.items()},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "status": status,
        "auto_promotion_status": "allowed" if status == "pass" else "blocked",
        "unattended_promotion_allowed": status == "pass",
        "inputs": inputs,
        "diagnostics": {
            "preflight": preflight,
            "preseal": preseal,
            "operator": operator,
            "auto_improve": auto_improve,
        },
        "checks": checks,
        "blockers": blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
    }


def write_manifest(vault: Path, manifest: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=manifest,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release-auto-promotion-ready manifest schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify unattended release auto-promotion readiness.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-manifest", default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--sealed-run-manifest", default=DEFAULT_SEALED_RUN_MANIFEST)
    parser.add_argument("--operator-summary", default=DEFAULT_OPERATOR_SUMMARY)
    parser.add_argument("--auto-improve-readiness", default=DEFAULT_AUTO_IMPROVE_READINESS)
    parser.add_argument("--auto-promotion-preflight", default=DEFAULT_AUTO_PROMOTION_PREFLIGHT)
    parser.add_argument("--auto-promotion-preseal", default=DEFAULT_AUTO_PROMOTION_PRESEAL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    manifest = build_manifest(
        vault,
        run_manifest=args.run_manifest,
        sealed_run_manifest=args.sealed_run_manifest,
        operator_summary=args.operator_summary,
        auto_improve_readiness=args.auto_improve_readiness,
        auto_promotion_preflight=args.auto_promotion_preflight,
        auto_promotion_preseal=args.auto_promotion_preseal,
    )
    path = write_manifest(vault, manifest, args.out)
    print(display_path(vault, path))
    if args.check:
        print(f"release_auto_promotion_ready_status={manifest['status']}")
    return 0 if manifest["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main(sys.argv[1:]))
