#!/usr/bin/env python3
"""Build a clean-lane blocker ledger from release authority artifacts."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.core.release_risk_state_runtime import (
    release_blocker_entry,
    release_risk_blocks_clean_lane,
    release_risk_identity,
    release_risk_list,
    release_risk_with_effects,
)
from ops.scripts.learning_readiness_vocabulary import (
    LEARNING_REVIEW_REQUIRED_BLOCKER_ID,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.release.release_status_v2 import (
    release_status_v2_view_with_readiness_fallback,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

from .advisory_lifecycle_runtime import (
    ADVISORY_LIFECYCLE_ACTIVE,
    advisory_lifecycle_assessment,
    advisory_lifecycle_summary,
)
from .release_risk_taxonomy_runtime import (
    ADVISORY_REVIEW_BACKLOG,
    CLEAN_LANE_BLOCKS,
    LEARNING_BLOCKS_CLAIM,
    RELEASE_RISK_TAXONOMY_PATH,
    clean_lane_blocks_release,
    load_release_risk_taxonomy,
    release_risk_effects,
)

DEFAULT_OUT = "ops/reports/release-clean-blocker-ledger.json"
PRODUCER = "ops.scripts.release_clean_blocker_ledger"
SCHEMA_PATH = "ops/schemas/release-clean-blocker-ledger.schema.json"
CLOSEOUT_PATH = "ops/reports/release-closeout-summary.json"
COHORT_PATH = "ops/reports/release-evidence-cohort.json"
LANE_SUMMARY_PATH = "ops/reports/release-lane-summary.json"
LEARNING_DELTA_SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"
LEARNING_SIGNOFF_PATH = "ops/reports/learning-readiness-signoff.json"
LEARNING_REVIEW_BLOCKER_ID = LEARNING_REVIEW_REQUIRED_BLOCKER_ID
POLICY_RISK_ACCEPTED_BY = "release_closeout_policy"


@dataclass(frozen=True)
class CleanBlockerSources:
    closeout: dict[str, Any]
    cohort: dict[str, Any]
    lane_summary: dict[str, Any]
    learning_guard: dict[str, Any]
    risk_taxonomy: dict[str, Any]


@dataclass(frozen=True)
class CleanBlockerRiskCollections:
    blockers: list[dict[str, Any]]
    source_clean_blockers: list[dict[str, Any]]
    auto_improve_blockers: list[dict[str, Any]]
    learning_claim_blockers: list[dict[str, Any]]
    advisory_backlog: list[dict[str, Any]]


@dataclass(frozen=True)
class CleanBlockerRenderInputs:
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    generated_at: str
    current_fingerprint: str
    sources: CleanBlockerSources
    clean_lane_contract: dict[str, Any]
    collections: CleanBlockerRiskCollections
    summary: dict[str, Any]


def _load(vault: Path, rel_path: str) -> dict[str, Any]:
    payload, _diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    return payload


def _load_with_status(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def _coverage_status(value: object) -> str:
    if not isinstance(value, int | float):
        return "unknown"
    if value >= 1.0:
        return "full"
    if value > 0:
        return "partial"
    return "none"


def _summary_coverage_status(summary: dict[str, Any], key: str, ratio_key: str) -> str:
    status = str(summary.get(key, "")).strip()
    if status in {"full", "partial", "none", "no_evidence", "not_applicable"}:
        return status
    return _coverage_status(summary.get(ratio_key))


def _learning_delta_guard_summary(payload: dict[str, Any], load_status: str) -> dict[str, Any]:
    if load_status != "ok":
        return {
            "path": LEARNING_DELTA_SCOREBOARD_PATH,
            "load_status": load_status,
            "status": "unknown",
            "claims_learning_improved": False,
            "learning_claim_allowed": False,
            "same_eval_run_count": 0,
            "telemetry_coverage_status": "unknown",
            "same_eval_reason_coverage_status": "unknown",
            "strict_secondary_improvement_coverage_status": "unknown",
            "behavior_delta_digest_coverage_status": "unknown",
            "placeholder_audit_status": "unknown",
            "placeholder_count": 0,
            "reason": f"learning delta scoreboard load_status={load_status}",
        }
    summary_payload = payload.get("summary")
    summary: dict[str, Any] = summary_payload if isinstance(summary_payload, dict) else {}
    guard_payload = payload.get("learning_claim_guard")
    guard: dict[str, Any] = guard_payload if isinstance(guard_payload, dict) else {}
    placeholder_payload = payload.get("external_report_placeholder_audit")
    placeholder_audit: dict[str, Any] = placeholder_payload if isinstance(placeholder_payload, dict) else {}
    return {
        "path": LEARNING_DELTA_SCOREBOARD_PATH,
        "load_status": load_status,
        "status": str(guard.get("status", payload.get("status", "unknown"))).strip() or "unknown",
        "claims_learning_improved": bool(summary.get("claims_learning_improved")),
        "learning_claim_allowed": bool(summary.get("learning_claim_allowed")),
        "same_eval_run_count": int(summary.get("same_eval_run_count", 0) or 0),
        "telemetry_coverage_status": _summary_coverage_status(
            summary,
            "telemetry_coverage_status",
            "telemetry_coverage_ratio",
        ),
        "same_eval_reason_coverage_status": _summary_coverage_status(
            summary,
            "same_eval_reason_coverage_status",
            "same_eval_reason_coverage_ratio",
        ),
        "strict_secondary_improvement_coverage_status": _summary_coverage_status(
            summary,
            "strict_secondary_improvement_coverage_status",
            "strict_secondary_improvement_coverage_ratio",
        ),
        "behavior_delta_digest_coverage_status": _summary_coverage_status(
            summary,
            "behavior_delta_digest_coverage_status",
            "behavior_delta_digest_coverage_ratio",
        ),
        "placeholder_audit_status": str(placeholder_audit.get("status", "unknown")).strip() or "unknown",
        "placeholder_count": int(placeholder_audit.get("placeholder_count", summary.get("placeholder_count", 0)) or 0),
        "reason": str(guard.get("reason", "")).strip() or "learning delta scoreboard guard status loaded",
    }


def _risk_identity(risk: dict[str, Any]) -> str:
    return release_risk_identity(risk)


def _blocker_entry(risk: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    return release_blocker_entry(
        risk,
        generated_at=generated_at,
        advisory_lifecycle_assessment=advisory_lifecycle_assessment,
        clean_lane_effect_default=CLEAN_LANE_BLOCKS,
    )


def _risk_blocks_clean_lane(risk: dict[str, Any]) -> bool:
    return release_risk_blocks_clean_lane(
        risk,
        learning_review_blocker_id=LEARNING_REVIEW_BLOCKER_ID,
        learning_signoff_path=LEARNING_SIGNOFF_PATH,
        policy_risk_accepted_by=POLICY_RISK_ACCEPTED_BY,
    )


def _risk_with_effects(risk: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    return release_risk_with_effects(
        risk,
        release_risk_effects(taxonomy, str(risk.get("code", "")).strip()),
    )


def _dict_child(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _first_known_status(*values: object) -> str:
    for value in values:
        status = str(value).strip()
        if status and status != "unknown":
            return status
    return "unknown"


def _risk_list(payload: dict[str, Any], key: str, taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    return release_risk_list(
        payload,
        key,
        lambda risk: release_risk_effects(taxonomy, str(risk.get("code", "")).strip()),
    )


def _load_clean_blocker_sources(vault: Path) -> CleanBlockerSources:
    learning_scoreboard, learning_scoreboard_load_status = _load_with_status(vault, LEARNING_DELTA_SCOREBOARD_PATH)
    return CleanBlockerSources(
        closeout=_load(vault, CLOSEOUT_PATH),
        cohort=_load(vault, COHORT_PATH),
        lane_summary=_load(vault, LANE_SUMMARY_PATH),
        learning_guard=_learning_delta_guard_summary(learning_scoreboard, learning_scoreboard_load_status),
        risk_taxonomy=load_release_risk_taxonomy(vault),
    )


def _blocker_entries(
    risks: list[dict[str, Any]],
    *,
    generated_at: str,
    predicate: Any,
) -> list[dict[str, Any]]:
    return sorted(
        (
            _blocker_entry(risk, generated_at=generated_at)
            for risk in risks
            if predicate(risk)
        ),
        key=lambda item: item["id"],
    )


def _clean_blocker_risk_collections(
    sources: CleanBlockerSources,
    *,
    generated_at: str,
) -> CleanBlockerRiskCollections:
    accepted_risks = _risk_list(sources.closeout, "accepted_risks", sources.risk_taxonomy)
    active_blockers = _risk_list(sources.closeout, "blockers", sources.risk_taxonomy)
    active_clean_blockers = [
        risk
        for risk in active_blockers
        if clean_lane_blocks_release(risk, sources.risk_taxonomy)
    ]
    accepted_clean_blockers = [
        risk
        for risk in accepted_risks
        if clean_lane_blocks_release(risk, sources.risk_taxonomy) and _risk_blocks_clean_lane(risk)
    ]
    source_clean_blockers = sorted(
        (
            _blocker_entry(risk, generated_at=generated_at)
            for risk in [*active_clean_blockers, *accepted_clean_blockers]
        ),
        key=lambda item: item["id"],
    )
    return CleanBlockerRiskCollections(
        blockers=source_clean_blockers,
        source_clean_blockers=source_clean_blockers,
        auto_improve_blockers=_blocker_entries(
            active_blockers,
            generated_at=generated_at,
            predicate=lambda risk: str(risk.get("source", "")).strip() == "auto_improve_readiness",
        ),
        learning_claim_blockers=_blocker_entries(
            [*active_blockers, *accepted_risks],
            generated_at=generated_at,
            predicate=lambda risk: str(risk.get("learning_lane_effect", "")).strip() == LEARNING_BLOCKS_CLAIM,
        ),
        advisory_backlog=_blocker_entries(
            accepted_risks,
            generated_at=generated_at,
            predicate=lambda risk: str(risk.get("advisory_lifecycle_effect", "")).strip()
            == ADVISORY_REVIEW_BACKLOG,
        ),
    )


def _clean_blocker_summary(
    sources: CleanBlockerSources,
    clean_lane_contract: dict[str, Any],
    collections: CleanBlockerRiskCollections,
) -> dict[str, Any]:
    lane = _dict_child(sources.lane_summary, "lane_summary")
    closeout_status_view = release_status_v2_view_with_readiness_fallback(sources.closeout)
    clean_lane_status = str(lane.get("clean_lane_status", clean_lane_contract.get("status", "fail"))).strip() or "fail"
    auto_improve_lane_status = str(lane.get("auto_improve_lane_status", "pass")).strip() or "pass"
    learning_guard_status = str(sources.learning_guard.get("status", "unknown")).strip() or "unknown"
    release_authority_status = _first_known_status(
        lane.get("release_authority_status", ""),
        closeout_status_view.get("release_authority_status", "unknown"),
    )
    sealed_release_status = _first_known_status(
        lane.get("sealed_release_status", ""),
        closeout_status_view.get("sealed_release_status", "unknown"),
    )
    return {
        **advisory_lifecycle_summary(collections.advisory_backlog),
        "blocker_count": len(collections.blockers),
        "source_clean_blocker_count": len(collections.source_clean_blockers),
        "auto_improve_blocker_count": len(collections.auto_improve_blockers),
        "accepted_risk_family_count": int(lane.get("accepted_risk_family_count", len(collections.blockers)) or 0),
        "accepted_risk_instance_count": int(lane.get("accepted_risk_instance_count", len(collections.blockers)) or 0),
        "clean_lane_blocking_family_count": int(
            lane.get("clean_lane_blocking_family_count", len(collections.blockers)) or 0
        ),
        "learning_claim_blocking_family_count": len({item["id"] for item in collections.learning_claim_blockers}),
        "advisory_lifecycle_family_count": len(collections.advisory_backlog),
        "clean_lane_status": clean_lane_status,
        "conditional_lane_status": str(lane.get("conditional_lane_status", "fail")).strip() or "fail",
        "auto_improve_lane_status": auto_improve_lane_status,
        "machine_release_status": str(lane.get("machine_release_status", "blocked")).strip() or "blocked",
        "operator_release_status": str(lane.get("operator_release_status", "blocked")).strip() or "blocked",
        "release_authority_status": release_authority_status,
        "sealed_release_status": sealed_release_status,
        "learning_claim_guard_status": learning_guard_status,
        "learning_claim_allowed": bool(sources.learning_guard.get("learning_claim_allowed")),
        "same_eval_reason_coverage_status": str(
            sources.learning_guard.get("same_eval_reason_coverage_status", "unknown")
        ),
        "strict_secondary_improvement_coverage_status": str(
            sources.learning_guard.get("strict_secondary_improvement_coverage_status", "unknown")
        ),
        "behavior_delta_digest_coverage_status": str(
            sources.learning_guard.get("behavior_delta_digest_coverage_status", "unknown")
        ),
        "placeholder_audit_status": str(sources.learning_guard.get("placeholder_audit_status", "unknown")),
    }


def _clean_blocker_status(summary: dict[str, Any]) -> str:
    if (
        summary["clean_lane_status"] == "pass"
        and int(summary["source_clean_blocker_count"]) == 0
        and int(summary["auto_improve_blocker_count"]) == 0
        and summary["learning_claim_guard_status"] == "pass"
        and summary["advisory_backlog_status"] in {"clear", ADVISORY_LIFECYCLE_ACTIVE}
    ):
        return "pass"
    return "attention"


def _render_clean_blocker_ledger(inputs: CleanBlockerRenderInputs) -> dict[str, Any]:
    collections = inputs.collections
    return {
        **build_canonical_report_envelope(
            inputs.vault,
            generated_at=inputs.generated_at,
            artifact_kind="release_clean_blocker_ledger",
            producer=PRODUCER,
            source_command="python -m ops.scripts.release_clean_blocker_ledger --vault . --out ops/reports/release-clean-blocker-ledger.json",
            resolved_policy_path=inputs.resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/release/release_clean_blocker_ledger.py",
                "ops/scripts/release/advisory_lifecycle_runtime.py",
            ],
            file_inputs={
                "release_closeout_summary": CLOSEOUT_PATH,
                "release_evidence_cohort": COHORT_PATH,
                "release_lane_summary": LANE_SUMMARY_PATH,
                "learning_delta_scoreboard": LEARNING_DELTA_SCOREBOARD_PATH,
                "release_risk_taxonomy": RELEASE_RISK_TAXONOMY_PATH,
            },
            text_inputs={"current_source_tree_fingerprint": inputs.current_fingerprint},
        ),
        "vault": report_path(inputs.vault, inputs.vault),
        "policy": {
            "path": report_path(inputs.vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "status": _clean_blocker_status(inputs.summary),
        "summary": inputs.summary,
        "learning_claim_guard": inputs.sources.learning_guard,
        "clean_lane_contract": {
            "status": str(inputs.clean_lane_contract.get("status", "fail")).strip() or "fail",
            "failed_conditions": [
                str(item).strip()
                for item in inputs.clean_lane_contract.get("failed_conditions", [])
                if str(item).strip()
            ],
        },
        "blockers": collections.blockers,
        "source_clean_blockers": collections.source_clean_blockers,
        "auto_improve_blockers": collections.auto_improve_blockers,
        "learning_claim_blockers": collections.learning_claim_blockers,
        "advisory_backlog": collections.advisory_backlog,
        "provenance": {
            "closeout_source": CLOSEOUT_PATH,
            "cohort_source": COHORT_PATH,
            "lane_summary_source": LANE_SUMMARY_PATH,
            "learning_delta_scoreboard_source": LEARNING_DELTA_SCOREBOARD_PATH,
        },
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    current_fingerprint = release_source_tree_fingerprint(vault)
    sources = _load_clean_blocker_sources(vault)
    clean_lane_contract = _dict_child(sources.cohort, "clean_lane_contract")
    collections = _clean_blocker_risk_collections(sources, generated_at=generated_at)
    summary = _clean_blocker_summary(sources, clean_lane_contract, collections)
    return _render_clean_blocker_ledger(
        CleanBlockerRenderInputs(
            vault=vault,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            generated_at=generated_at,
            current_fingerprint=current_fingerprint,
            sources=sources,
            clean_lane_contract=clean_lane_contract,
            collections=collections,
            summary=summary,
        )
    )


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release clean blocker ledger schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a clean-lane blocker ledger from release authority artifacts")
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
