from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext

from .learning_claim_evidence_bundle import (
    DEFAULT_OUT as DEFAULT_EVIDENCE_BUNDLE_PATH,
    SAME_EVAL_PROPOSAL_FAILURE_MODES,
    validate_learning_claim_evidence_bundle,
)

DEFAULT_OUT = "ops/reports/learning-confirmed-evidence-cohort.json"
DEFAULT_CONFIRMED_POLICY_PATH = "ops/policies/learning-claim-confirmed-improvement.json"
PRODUCER = "ops.scripts.learning_confirmed_evidence_cohort"
SCHEMA_PATH = "ops/schemas/learning-confirmed-evidence-cohort.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.learning_confirmed_evidence_cohort --vault ."


@dataclass(frozen=True)
class ConfirmedCohortThresholds:
    min_run_count: int
    min_family_count: int


@dataclass(frozen=True)
class ConfirmedCohortSummaryInputs:
    cohort_digest: str
    confirmed_status: str
    bundle_status: str
    run_rows: list[dict[str, Any]]
    selected_valid_run_ids: list[str]
    rejected_run_diagnostics: list[dict[str, Any]]
    legacy_reconstruction_summary: dict[str, Any]
    families: list[dict[str, Any]]
    eligible_families: list[dict[str, Any]]
    max_valid_run_count: int
    thresholds: ConfirmedCohortThresholds
    predicates: list[dict[str, Any]]


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _policy_int(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(policy.get(key, default))
    except (TypeError, ValueError):
        return default


def _predicate_result(
    predicate_id: str,
    status: str,
    source_path: str,
    required_condition: str,
    observed_value: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "id": predicate_id,
        "status": status,
        "source_path": source_path,
        "required_condition": required_condition,
        "observed_value": observed_value,
        "summary": summary,
    }


def _proposal_family(proposal: dict[str, Any]) -> str:
    failure_mode = str(proposal.get("failure_mode", "")).strip()
    if failure_mode:
        return failure_mode
    expected_change = str(proposal.get("expected_change", "")).strip()
    return expected_change or "unknown"


def _run_family_map(mutation_proposals: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    proposals = mutation_proposals.get("proposals", [])
    if not isinstance(proposals, list):
        return mapping
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        if str(proposal.get("failure_mode", "")).strip() not in SAME_EVAL_PROPOSAL_FAILURE_MODES:
            continue
        family = _proposal_family(proposal)
        for run_id_value in proposal.get("run_ids", []):
            run_id = str(run_id_value).strip()
            if not run_id:
                continue
            mapping.setdefault(run_id, [])
            if family not in mapping[run_id]:
                mapping[run_id].append(family)
    return mapping


def _behavior_delta_summary(vault: Path, rel_path: str) -> dict[str, Any]:
    payload = load_optional_json_object(vault / rel_path) if rel_path else {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    deltas = payload.get("deltas", []) if isinstance(payload, dict) else []
    deltas = deltas if isinstance(deltas, list) else []
    delta_count = int(summary.get("delta_count", len(deltas)) or 0)
    behavior_changed = bool(summary.get("behavior_changed"))
    return {
        "behavior_changed": behavior_changed,
        "delta_count": delta_count,
        "before_after_evidence_present": behavior_changed and delta_count > 0,
    }


def _run_evidence(
    vault: Path,
    telemetry_items: list[dict[str, Any]],
    run_families: dict[str, list[str]],
    run_artifacts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in telemetry_items:
        if not isinstance(item, dict):
            continue
        run_id = str(item.get("run_id", "")).strip()
        families = _string_list(item.get("families")) or run_families.get(run_id, [])
        behavior_delta_path = str(item.get("behavior_delta_path", "")).strip()
        behavior_summary = _behavior_delta_summary(vault, behavior_delta_path)
        decision = str(item.get("decision", "")).strip().upper()
        axes = _string_list(item.get("secondary_improvement_axes"))
        digest_source = str(item.get("behavior_delta_digest_source", "")).strip()
        artifact_row = run_artifacts.get(run_id, {})
        artifacts = artifact_row.get("artifacts", []) if isinstance(artifact_row, dict) else []
        artifacts = artifacts if isinstance(artifacts, list) else []
        missing_artifacts = [
            str(artifact.get("id", "")).strip()
            for artifact in artifacts
            if isinstance(artifact, dict)
            and bool(artifact.get("required_for_confirmed"))
            and not bool(artifact.get("exists"))
        ]
        artifact_binding_status = str(artifact_row.get("status", "")).strip() if artifact_row else "missing"
        valid = (
            bool(families)
            and decision == "PROMOTE"
            and bool(item.get("exists"))
            and bool(item.get("behavior_delta_digest_valid"))
            and bool(item.get("behavior_delta_artifact_exists"))
            and bool(item.get("behavior_delta_artifact_digest_match"))
            and bool(item.get("strict_secondary_improvement_present"))
            and bool(axes)
            and bool(behavior_summary["before_after_evidence_present"])
            and artifact_binding_status == "pass"
        )
        reasons: list[str] = []
        if not families:
            reasons.append("no same-family proposal mapping")
        if decision != "PROMOTE":
            reasons.append(f"decision={decision or 'missing'}")
        if not item.get("exists"):
            reasons.append("run telemetry missing")
        if not item.get("behavior_delta_digest_valid"):
            reasons.append("behavior_delta_digest invalid or missing")
        if not item.get("behavior_delta_artifact_exists"):
            reasons.append("behavior_delta artifact missing")
        if item.get("behavior_delta_artifact_exists") and not item.get("behavior_delta_artifact_digest_match"):
            reasons.append("behavior_delta artifact digest mismatch")
        if not item.get("strict_secondary_improvement_present"):
            reasons.append("strict secondary improvement missing")
        if not axes:
            reasons.append("secondary improvement axes missing")
        if not behavior_summary["before_after_evidence_present"]:
            reasons.append("behavior delta before/after evidence missing")
        if artifact_binding_status != "pass":
            reasons.append("confirmed run artifact binding incomplete")
        for artifact_id in missing_artifacts:
            reasons.append(f"confirmed run artifact missing: {artifact_id}")
        rows.append(
            {
                "run_id": run_id,
                "families": families,
                "telemetry_path": str(item.get("telemetry_path", "")).strip(),
                "decision": decision,
                "behavior_delta_path": behavior_delta_path,
                "behavior_delta_digest": str(item.get("behavior_delta_digest", "")).strip(),
                "behavior_delta_digest_source": digest_source,
                "behavior_delta_artifact_sha256": str(item.get("behavior_delta_artifact_sha256", "")).strip(),
                "behavior_delta_artifact_digest_match": bool(item.get("behavior_delta_artifact_digest_match")),
                "confirmed_run_artifacts": artifacts,
                "confirmed_run_artifact_binding_status": artifact_binding_status,
                "confirmed_run_artifact_missing_count": len(missing_artifacts),
                "confirmed_run_artifact_missing_ids": missing_artifacts,
                "legacy_reconstruction_status": str(
                    item.get("legacy_reconstruction_status", "not_applicable")
                ).strip()
                or "not_applicable",
                "legacy_reconstruction_selection_reason": str(
                    item.get("legacy_reconstruction_selection_reason", "")
                ).strip(),
                "legacy_reconstruction_reasons": _string_list(
                    item.get("legacy_reconstruction_reasons")
                ),
                "secondary_axis_evidence_source": str(
                    item.get("secondary_axis_evidence_source", "missing")
                ).strip()
                or "missing",
                "secondary_axis_evidence_detail": str(
                    item.get("secondary_axis_evidence_detail", "")
                ).strip(),
                "strict_secondary_improvement_present": bool(item.get("strict_secondary_improvement_present")),
                "secondary_improvement_axes": axes,
                **behavior_summary,
                "valid_for_confirmed_claim": valid,
                "status": "pass" if valid else "fail",
                "reasons": reasons,
            }
        )
    return rows


def _family_cohorts(run_rows: list[dict[str, Any]], min_run_count: int) -> list[dict[str, Any]]:
    families = sorted({family for row in run_rows for family in row.get("families", [])})
    cohorts: list[dict[str, Any]] = []
    for family in families:
        rows = [row for row in run_rows if family in row.get("families", [])]
        valid_run_ids = [
            str(row["run_id"])
            for row in rows
            if bool(row.get("valid_for_confirmed_claim"))
        ]
        status = "pass" if len(valid_run_ids) >= min_run_count else "fail"
        cohorts.append(
            {
                "family": family,
                "run_ids": [str(row["run_id"]) for row in rows],
                "run_count": len(rows),
                "valid_run_ids": valid_run_ids,
                "valid_run_count": len(valid_run_ids),
                "min_required_run_count": min_run_count,
                "status": status,
                "reason": (
                    "same-family confirmed evidence threshold satisfied"
                    if status == "pass"
                    else f"valid_run_count={len(valid_run_ids)} below min_required_run_count={min_run_count}"
                ),
            }
        )
    return cohorts


def _selected_valid_run_ids(
    run_rows: list[dict[str, Any]], eligible_families: list[dict[str, Any]]
) -> list[str]:
    selected_ids = {
        str(run_id).strip()
        for family in eligible_families
        for run_id in family.get("valid_run_ids", [])
        if str(run_id).strip()
    }
    return [
        str(row.get("run_id", "")).strip()
        for row in run_rows
        if bool(row.get("valid_for_confirmed_claim"))
        and str(row.get("run_id", "")).strip() in selected_ids
    ]


def _rejected_run_diagnostics(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for row in run_rows:
        if bool(row.get("valid_for_confirmed_claim")):
            continue
        diagnostics.append(
            {
                "run_id": str(row.get("run_id", "")).strip(),
                "decision": str(row.get("decision", "")).strip(),
                "families": _string_list(row.get("families")),
                "status": str(row.get("status", "fail")).strip() or "fail",
                "reasons": _string_list(row.get("reasons")),
                "missing_artifacts": _string_list(row.get("confirmed_run_artifact_missing_ids")),
            }
        )
    return diagnostics


def _legacy_reconstruction_summary(run_rows: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics = [
        {
            "run_id": str(row.get("run_id", "")).strip(),
            "families": _string_list(row.get("families")),
            "reconstruction_status": str(row.get("legacy_reconstruction_status", "not_applicable")).strip()
            or "not_applicable",
            "selection_reason": str(row.get("legacy_reconstruction_selection_reason", "")).strip(),
            "reconstruction_reasons": _string_list(row.get("legacy_reconstruction_reasons")),
            "secondary_axis_evidence_source": str(
                row.get("secondary_axis_evidence_source", "missing")
            ).strip()
            or "missing",
            "secondary_axis_evidence_detail": str(row.get("secondary_axis_evidence_detail", "")).strip(),
            "parsed_secondary_axes": _string_list(row.get("secondary_improvement_axes")),
        }
        for row in run_rows
        if str(row.get("legacy_reconstruction_status", "not_applicable")).strip() != "not_applicable"
    ]
    blocked_count = sum(1 for row in diagnostics if row["reconstruction_status"] == "blocked")
    reconstructed_count = sum(1 for row in diagnostics if row["reconstruction_status"] == "reconstructed")
    needed_count = sum(
        1
        for row in diagnostics
        if row["reconstruction_status"] in {"reconstructed", "blocked"}
    )
    status = "not_used"
    if diagnostics:
        status = "fail" if blocked_count else "pass"
    return {
        "status": status,
        "reconstruction_needed_count": needed_count,
        "reconstructed_run_count": reconstructed_count,
        "blocked_run_count": blocked_count,
        "run_diagnostics": diagnostics,
    }


def _identity_payload(
    *,
    policy: dict[str, Any],
    evidence_bundle_validation: dict[str, Any],
    run_rows: list[dict[str, Any]],
    family_cohorts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "payload_version": 1,
        "policy": {
            "version": policy.get("version"),
            "min_repeated_improvement_run_count": _policy_int(policy, "min_repeated_improvement_run_count", 3),
            "min_family_consistency_count": _policy_int(policy, "min_family_consistency_count", 1),
        },
        "evidence_bundle": {
            "path": evidence_bundle_validation.get("bundle_path", DEFAULT_EVIDENCE_BUNDLE_PATH),
            "sha256": evidence_bundle_validation.get("bundle_sha256", ""),
            "status": evidence_bundle_validation.get("revocation_status", "not_evaluated"),
        },
        "run_evidence": run_rows,
        "family_cohorts": family_cohorts,
    }


def _confirmed_cohort_thresholds(policy: dict[str, Any]) -> ConfirmedCohortThresholds:
    return ConfirmedCohortThresholds(
        min_run_count=_policy_int(policy, "min_repeated_improvement_run_count", 3),
        min_family_count=_policy_int(policy, "min_family_consistency_count", 1),
    )


def _bundle_telemetry_items(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    telemetry_items = bundle.get("confirmed_telemetry_evidence", [])
    if not telemetry_items:
        telemetry_items = bundle.get("telemetry_evidence", [])
    if not isinstance(telemetry_items, list):
        return []
    return [item for item in telemetry_items if isinstance(item, dict)]


def _bundle_run_artifact_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifact_rows = bundle.get("confirmed_run_artifacts", [])
    if not isinstance(artifact_rows, list):
        return {}
    return {
        str(row.get("run_id", "")).strip(): row
        for row in artifact_rows
        if isinstance(row, dict) and str(row.get("run_id", "")).strip()
    }


def _confirmed_cohort_status(
    *,
    bundle_status: str,
    eligible_family_count: int,
    thresholds: ConfirmedCohortThresholds,
) -> str:
    if bundle_status == "revoked":
        return "revoked"
    if eligible_family_count >= thresholds.min_family_count:
        return "auto_confirmed"
    return "not_ready"


def _cohort_predicate_results(
    *,
    bundle: dict[str, Any],
    bundle_status: str,
    evidence_bundle_path: str,
    eligible_families: list[dict[str, Any]],
    families: list[dict[str, Any]],
    max_valid_run_count: int,
    thresholds: ConfirmedCohortThresholds,
) -> list[dict[str, Any]]:
    artifact_readback = bundle.get("behavior_delta_artifact_readback", {})
    artifact_status = (
        str(artifact_readback.get("status", "")).strip()
        if isinstance(artifact_readback, dict)
        else ""
    )
    return [
        _predicate_result(
            "confirmed_evidence_bundle_active",
            "pass" if bundle_status == "active" else "fail",
            evidence_bundle_path,
            "learning_claim_evidence_bundle.revocation_status == active",
            f"revocation_status={bundle_status}",
            "Confirmed evidence cohort must bind an active learning claim evidence bundle.",
        ),
        _predicate_result(
            "repeated_same_family_evidence",
            "pass" if len(eligible_families) >= thresholds.min_family_count else "fail",
            DEFAULT_OUT,
            (
                "same proposal family valid before/after behavior-delta evidence count >= "
                f"{thresholds.min_run_count} and eligible family count >= {thresholds.min_family_count}"
            ),
            (
                f"eligible_family_count={len(eligible_families)}; "
                f"family_count={len(families)}; "
                f"max_valid_run_count={max_valid_run_count}"
            ),
            "Confirmed learning improvement requires repeated same-family before/after evidence.",
        ),
        _predicate_result(
            "behavior_delta_artifact_digest_readback",
            "pass" if artifact_status == "pass" else "fail",
            evidence_bundle_path,
            "behavior_delta_artifact_readback.status == pass",
            "status=" + (artifact_status or "missing"),
            "Confirmed learning improvement requires behavior-delta artifact digest readback.",
        ),
    ]


def _confirmed_cohort_path_group_inputs(run_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "confirmed_run_telemetry": [
            str(row["telemetry_path"])
            for row in run_rows
            if str(row.get("telemetry_path", "")).strip()
        ],
        "confirmed_behavior_delta": [
            str(row["behavior_delta_path"])
            for row in run_rows
            if str(row.get("behavior_delta_path", "")).strip()
        ],
        "confirmed_run_artifacts": [
            str(artifact["path"])
            for row in run_rows
            for artifact in row.get("confirmed_run_artifacts", [])
            if isinstance(artifact, dict) and str(artifact.get("path", "")).strip()
        ],
    }


def _confirmed_cohort_summary(inputs: ConfirmedCohortSummaryInputs) -> dict[str, Any]:
    return {
        "cohort_sha256": inputs.cohort_digest,
        "confirmed_evidence_status": inputs.confirmed_status,
        "confirmed_learning_improvement_allowed": inputs.confirmed_status == "auto_confirmed",
        "evidence_bundle_status": inputs.bundle_status,
        "run_count": len(inputs.run_rows),
        "valid_run_count": sum(1 for row in inputs.run_rows if row["valid_for_confirmed_claim"]),
        "selected_valid_run_ids": inputs.selected_valid_run_ids,
        "rejected_run_count": len(inputs.rejected_run_diagnostics),
        "rejected_run_diagnostics": inputs.rejected_run_diagnostics,
        "legacy_reconstruction_summary": inputs.legacy_reconstruction_summary,
        "family_count": len(inputs.families),
        "eligible_family_count": len(inputs.eligible_families),
        "eligible_family_ids": [str(item["family"]) for item in inputs.eligible_families],
        "max_valid_run_count": inputs.max_valid_run_count,
        "min_required_run_count": inputs.thresholds.min_run_count,
        "min_family_consistency_count": inputs.thresholds.min_family_count,
        "blocking_predicate_ids": [
            str(predicate["id"])
            for predicate in inputs.predicates
            if predicate["status"] != "pass"
        ],
    }


def _source_bundle_payload(
    *,
    evidence_bundle_validation: dict[str, Any],
    evidence_bundle_path: str,
    bundle_status: str,
) -> dict[str, Any]:
    return {
        "path": evidence_bundle_path,
        "bundle_sha256": str(evidence_bundle_validation.get("bundle_sha256", "")),
        "current_bundle_sha256": str(evidence_bundle_validation.get("current_bundle_sha256", "")),
        "bundle_status": str(evidence_bundle_validation.get("bundle_status", "missing")),
        "revocation_status": bundle_status,
        "fingerprint_match_status": str(
            evidence_bundle_validation.get("bundle_fingerprint_match_status", "missing")
        ),
    }


def build_report(
    vault: Path,
    *,
    out_path: str = DEFAULT_OUT,
    evidence_bundle_path: str = DEFAULT_EVIDENCE_BUNDLE_PATH,
    confirmed_policy_path: str = DEFAULT_CONFIRMED_POLICY_PATH,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    confirmed_policy = load_optional_json_object(vault / confirmed_policy_path)
    thresholds = _confirmed_cohort_thresholds(confirmed_policy)
    evidence_bundle_validation = validate_learning_claim_evidence_bundle(
        vault,
        bundle_path=evidence_bundle_path,
        context=context,
    )
    bundle = load_optional_json_object(vault / evidence_bundle_path)
    mutation_proposals = load_optional_json_object(vault / "ops/reports/mutation-proposals.json")
    run_rows = _run_evidence(
        vault,
        _bundle_telemetry_items(bundle),
        _run_family_map(mutation_proposals),
        _bundle_run_artifact_map(bundle),
    )
    families = _family_cohorts(run_rows, thresholds.min_run_count)
    eligible_families = [item for item in families if item["status"] == "pass"]
    selected_valid_run_ids = _selected_valid_run_ids(run_rows, eligible_families)
    rejected_run_diagnostics = _rejected_run_diagnostics(run_rows)
    legacy_reconstruction_summary = _legacy_reconstruction_summary(run_rows)
    max_valid_run_count = max((int(item["valid_run_count"]) for item in families), default=0)
    bundle_status = str(evidence_bundle_validation.get("revocation_status", "revoked"))
    confirmed_status = _confirmed_cohort_status(
        bundle_status=bundle_status,
        eligible_family_count=len(eligible_families),
        thresholds=thresholds,
    )
    predicates = _cohort_predicate_results(
        bundle=bundle,
        bundle_status=bundle_status,
        evidence_bundle_path=evidence_bundle_path,
        eligible_families=eligible_families,
        families=families,
        max_valid_run_count=max_valid_run_count,
        thresholds=thresholds,
    )
    identity_payload = _identity_payload(
        policy=confirmed_policy,
        evidence_bundle_validation=evidence_bundle_validation,
        run_rows=run_rows,
        family_cohorts=families,
    )
    cohort_digest = _canonical_sha256(identity_payload)
    status = "fail" if confirmed_status == "revoked" else "pass"
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="learning_confirmed_evidence_cohort",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/learning/learning_confirmed_evidence_cohort.py",
                "ops/scripts/learning/learning_claim_evidence_bundle.py",
                "ops/scripts/learning/learning_claim_unlock_review.py",
            ],
            file_inputs={
                "learning_claim_evidence_bundle": evidence_bundle_path,
                "confirmed_policy": confirmed_policy_path,
                "mutation_proposals": "ops/reports/mutation-proposals.json",
            },
            path_group_inputs=_confirmed_cohort_path_group_inputs(run_rows),
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "status": status,
        "summary": _confirmed_cohort_summary(
            ConfirmedCohortSummaryInputs(
                cohort_digest=cohort_digest,
                confirmed_status=confirmed_status,
                bundle_status=bundle_status,
                run_rows=run_rows,
                selected_valid_run_ids=selected_valid_run_ids,
                rejected_run_diagnostics=rejected_run_diagnostics,
                legacy_reconstruction_summary=legacy_reconstruction_summary,
                families=families,
                eligible_families=eligible_families,
                max_valid_run_count=max_valid_run_count,
                thresholds=thresholds,
                predicates=predicates,
            )
        ),
        "cohort_identity": {
            "digest_algorithm": "sha256",
            "cohort_payload_version": 1,
            "cohort_digest": cohort_digest,
        },
        "source_bundle": _source_bundle_payload(
            evidence_bundle_validation=evidence_bundle_validation,
            evidence_bundle_path=evidence_bundle_path,
            bundle_status=bundle_status,
        ),
        "run_evidence": run_rows,
        "family_cohorts": families,
        "predicate_results": predicates,
        "revocation": {
            "status": "revoked" if confirmed_status == "revoked" else "active",
            "reasons": [
                str(reason)
                for reason in evidence_bundle_validation.get("reasons", [])
                if str(reason).strip()
            ],
        },
    }


def validate_learning_confirmed_evidence_cohort(
    vault: Path,
    *,
    cohort_path: str = DEFAULT_OUT,
    evidence_bundle_path: str = DEFAULT_EVIDENCE_BUNDLE_PATH,
    confirmed_policy_path: str = DEFAULT_CONFIRMED_POLICY_PATH,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    stored = load_optional_json_object(vault / cohort_path)
    if not stored:
        return {
            "cohort_path": cohort_path,
            "cohort_status": "missing",
            "cohort_sha256": "",
            "current_cohort_sha256": "",
            "cohort_fingerprint_match_status": "missing",
            "revocation_status": "revoked",
            "confirmed_evidence_status": "revoked",
            "confirmed_learning_improvement_allowed": False,
            "confirmed_evidence_summary": {
                "confirmed_evidence_status": "revoked",
                "valid_run_count": 0,
                "min_required_run_count": 0,
                "eligible_family_count": 0,
                "selected_valid_run_ids": [],
                "blocking_predicate_ids": ["learning_confirmed_evidence_cohort_missing"],
                "rejected_run_count": 0,
                "rejected_run_diagnostics": [],
                "legacy_reconstruction_summary": _legacy_reconstruction_summary([]),
            },
            "predicate_results": [],
            "reasons": ["learning confirmed evidence cohort is missing"],
        }
    current = build_report(
        vault,
        evidence_bundle_path=evidence_bundle_path,
        confirmed_policy_path=confirmed_policy_path,
        context=context,
    )
    stored_identity = stored.get("cohort_identity")
    stored_digest = (
        str(stored_identity.get("cohort_digest", "")).strip()
        if isinstance(stored_identity, dict)
        else ""
    )
    current_digest = str(current["cohort_identity"]["cohort_digest"])
    current_revocation = str(current.get("revocation", {}).get("status", "revoked"))
    fingerprint_match = stored_digest == current_digest and bool(stored_digest)
    if current_revocation == "revoked":
        cohort_status = "revoked"
        revocation_status = "revoked"
        reasons = [
            str(reason)
            for reason in current.get("revocation", {}).get("reasons", [])
            if str(reason).strip()
        ]
    elif not fingerprint_match:
        cohort_status = "stale"
        revocation_status = "stale"
        reasons = ["learning confirmed evidence cohort digest no longer matches current evidence"]
    else:
        cohort_status = "active"
        revocation_status = "active"
        reasons = []
    return {
        "cohort_path": cohort_path,
        "cohort_status": cohort_status,
        "cohort_sha256": stored_digest,
        "current_cohort_sha256": current_digest,
        "cohort_fingerprint_match_status": "match" if fingerprint_match else "mismatch",
        "revocation_status": revocation_status,
        "confirmed_evidence_status": str(current["summary"]["confirmed_evidence_status"]),
        "confirmed_learning_improvement_allowed": bool(
            current["summary"]["confirmed_learning_improvement_allowed"]
        )
        and revocation_status == "active",
        "confirmed_evidence_summary": {
            "confirmed_evidence_status": str(current["summary"]["confirmed_evidence_status"]),
            "valid_run_count": int(current["summary"]["valid_run_count"]),
            "min_required_run_count": int(current["summary"]["min_required_run_count"]),
            "eligible_family_count": int(current["summary"]["eligible_family_count"]),
            "selected_valid_run_ids": [
                str(item)
                for item in current["summary"].get("selected_valid_run_ids", [])
                if str(item).strip()
            ],
            "blocking_predicate_ids": [
                str(item)
                for item in current["summary"].get("blocking_predicate_ids", [])
                if str(item).strip()
            ],
            "rejected_run_count": int(current["summary"].get("rejected_run_count", 0) or 0),
            "rejected_run_diagnostics": [
                item
                for item in current["summary"].get("rejected_run_diagnostics", [])
                if isinstance(item, dict)
            ],
            "legacy_reconstruction_summary": (
                current["summary"].get("legacy_reconstruction_summary")
                if isinstance(current["summary"].get("legacy_reconstruction_summary"), dict)
                else _legacy_reconstruction_summary([])
            ),
        },
        "predicate_results": current["predicate_results"],
        "reasons": reasons,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="learning confirmed evidence cohort schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build learning confirmed evidence cohort")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--evidence-bundle", default=DEFAULT_EVIDENCE_BUNDLE_PATH)
    parser.add_argument("--confirmed-policy", default=DEFAULT_CONFIRMED_POLICY_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        out_path=args.out,
        evidence_bundle_path=args.evidence_bundle,
        confirmed_policy_path=args.confirmed_policy,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
