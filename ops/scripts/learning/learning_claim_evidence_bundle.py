from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.payload_field_runtime import dict_value
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext

DEFAULT_OUT = "ops/reports/learning-claim-evidence-bundle.json"
PRODUCER = "ops.scripts.learning_claim_evidence_bundle"
SCHEMA_PATH = "ops/schemas/learning-claim-evidence-bundle.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.learning_claim_evidence_bundle --vault ."
MECHANISM_REVIEW_CANDIDATES_PATH = "ops/reports/mechanism-review-candidates.json"
LEGACY_RECONSTRUCTION_PATH = "ops/reports/learning-confirmed-legacy-reconstruction.json"
CONFIRMED_RUN_ARTIFACT_SPECS = (
    ("baseline_mechanism_assessment", "baseline-mechanism-assessment.json"),
    ("candidate_mechanism_assessment", "candidate-mechanism-assessment.json"),
    ("promotion_report", "promotion-report.json"),
)
HEX_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")
SAME_EVAL_PROPOSAL_FAILURE_MODES = {
    "repeated_same_eval_or_discard",
    "repeated_same_eval_after_promote",
    "repeated_discard_runs",
}
REQUIRED_EVIDENCE_SPECS = (
    ("auto_improve_readiness", "ops/reports/auto-improve-readiness.json", "blocking"),
    ("mechanism_review_candidates", MECHANISM_REVIEW_CANDIDATES_PATH, "blocking"),
    ("mutation_proposals", "ops/reports/mutation-proposals.json", "blocking"),
    ("outcome_metrics", "ops/reports/outcome-metrics.json", "blocking"),
    ("public_check_summary", "ops/reports/public-check-summary.json", "blocking"),
    ("learning_confirmed_legacy_reconstruction", LEGACY_RECONSTRUCTION_PATH, "blocking"),
    ("external_report_reference_manifest", "external-reports/report-reference-manifest.json", "blocking"),
)


@dataclass(frozen=True)
class BehaviorDeltaReadback:
    telemetry_missing_count: int
    digest_missing_count: int
    digest_mismatch_count: int
    digest_missing_count_all: int
    digest_mismatch_count_all: int
    digest_readback_status: str
    artifact_missing_count: int
    artifact_mismatch_count: int
    artifact_readback_status: str


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _same_eval_proposals(mutation_proposals: dict[str, Any]) -> list[dict[str, Any]]:
    proposals = mutation_proposals.get("proposals", [])
    if not isinstance(proposals, list):
        return []
    return [
        proposal
        for proposal in proposals
        if isinstance(proposal, dict)
        and str(proposal.get("failure_mode", "")).strip() in SAME_EVAL_PROPOSAL_FAILURE_MODES
    ]


def _proposal_family(proposal: dict[str, Any]) -> str:
    failure_mode = str(proposal.get("failure_mode", "")).strip()
    if failure_mode:
        return failure_mode
    expected_change = str(proposal.get("expected_change", "")).strip()
    return expected_change or "unknown"


def _proposal_group_family(proposal: dict[str, Any]) -> str:
    family = str(proposal.get("family", "")).strip()
    if family:
        return family
    return _proposal_family(proposal)


def _proposal_run_ids(mutation_proposals: dict[str, Any]) -> list[str]:
    run_ids: list[str] = []
    for proposal in _same_eval_proposals(mutation_proposals):
        for run_id in proposal.get("run_ids", []):
            value = str(run_id).strip()
            if value and value not in run_ids:
                run_ids.append(value)
    return run_ids


def _proposal_families(mutation_proposals: dict[str, Any]) -> list[str]:
    families: list[str] = []
    for proposal in _same_eval_proposals(mutation_proposals):
        family = _proposal_group_family(proposal)
        if family not in families:
            families.append(family)
    return families


def _target_key(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _proposal_target_keys(mutation_proposals: dict[str, Any]) -> set[tuple[str, ...]]:
    return {
        key
        for proposal in _same_eval_proposals(mutation_proposals)
        for key in [_target_key(proposal.get("primary_targets"))]
        if key
    }


def _telemetry_path_for_run(vault: Path, run_id: str) -> Path | None:
    candidates = [
        vault / "runs" / run_id / "run-telemetry.json",
        vault / "runs" / "archive" / run_id / "run-telemetry.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted((vault / "runs").glob(f"**/{run_id}/run-telemetry.json"))
    return matches[0] if matches else None


def _promotion_report_path_for_run(vault: Path, run_id: str) -> Path | None:
    candidates = [
        vault / "runs" / run_id / "promotion-report.json",
        vault / "runs" / "archive" / run_id / "promotion-report.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted((vault / "runs").glob(f"**/{run_id}/promotion-report.json"))
    return matches[0] if matches else None


def _run_artifact_path_for_run(vault: Path, run_id: str, filename: str) -> Path | None:
    candidates = [
        vault / "runs" / run_id / filename,
        vault / "runs" / "archive" / run_id / filename,
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted((vault / "runs").glob(f"**/{run_id}/{filename}"))
    return matches[0] if matches else None


def _promotion_report_for_run(vault: Path, run_id: str) -> tuple[Path | None, dict[str, Any]]:
    path = _promotion_report_path_for_run(vault, run_id)
    payload = load_optional_json_object(path) if path else {}
    return path, payload


def _behavior_delta_path(telemetry: dict[str, Any], promotion_report: dict[str, Any]) -> str:
    telemetry_path = str(telemetry.get("behavior_delta", "")).strip()
    if telemetry_path:
        return telemetry_path
    inputs = promotion_report.get("inputs") if isinstance(promotion_report, dict) else {}
    if isinstance(inputs, dict):
        return str(inputs.get("behavior_delta", "")).strip()
    return ""


def _secondary_axes_from_text(value: str) -> list[str]:
    if "selected_axes=" not in value:
        return []
    tail = value.split("selected_axes=", 1)[1].strip()
    if tail.startswith("[") and "]" in tail:
        tail = tail[1:tail.index("]")]
    else:
        tail = tail.split(",", 1)[0].strip()
    tail = tail.strip("[](){}")
    return [
        item.strip().strip("'\"")
        for item in tail.split(",")
        if item.strip().strip("'\"")
    ]


def _promotion_secondary_improvement(promotion_report: dict[str, Any]) -> tuple[bool, list[str]]:
    axes = _string_list(promotion_report.get("secondary_improvement_axes"))
    strict = bool(promotion_report.get("strict_secondary_improvement_present"))
    checks = promotion_report.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict) or check.get("id") != "equal_score_secondary_eligibility":
                continue
            detail = str(check.get("detail", ""))
            inferred_axes = _secondary_axes_from_text(detail)
            if inferred_axes and not axes:
                axes = inferred_axes
            if "selected_any_improvement=true" in detail:
                strict = True
    return strict, axes


def _legacy_reconstruction_by_run(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("run_reconstructions", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("run_id", "")).strip(): row
        for row in rows
        if isinstance(row, dict) and str(row.get("run_id", "")).strip()
    }


def _telemetry_item(
    vault: Path,
    run_id: str,
    *,
    allow_artifact_digest_fallback: bool = False,
    legacy_reconstruction_by_run: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    legacy_reconstruction = (
        legacy_reconstruction_by_run.get(run_id, {}) if legacy_reconstruction_by_run is not None else {}
    )
    legacy_reconstruction_status = str(
        legacy_reconstruction.get("reconstruction_status", "not_applicable")
    ).strip() or "not_applicable"
    telemetry_path = _telemetry_path_for_run(vault, run_id)
    telemetry = load_optional_json_object(telemetry_path) if telemetry_path else {}
    promotion_path, promotion_report = _promotion_report_for_run(vault, run_id)
    digest = str(telemetry.get("behavior_delta_digest", "")).strip()
    digest_present = bool(digest)
    digest_valid = bool(HEX_SHA256_RE.fullmatch(digest))
    behavior_delta_path = _behavior_delta_path(telemetry, promotion_report)
    behavior_delta_artifact = vault / behavior_delta_path if behavior_delta_path else None
    artifact_exists = bool(behavior_delta_artifact and behavior_delta_artifact.is_file())
    artifact_sha256 = _sha256_file(behavior_delta_artifact) if behavior_delta_artifact and artifact_exists else ""
    digest_source = "telemetry_field" if digest_present else "missing"
    legacy_behavior_delta_sha256 = str(legacy_reconstruction.get("behavior_delta_artifact_sha256", "")).strip()
    if (
        not digest_valid
        and allow_artifact_digest_fallback
        and legacy_reconstruction_status in {"reconstructed", "not_needed"}
        and legacy_behavior_delta_sha256
    ):
        digest = legacy_behavior_delta_sha256
        digest_present = True
        digest_valid = True
        digest_source = "legacy_reconstruction_artifact"
    normalized_digest = digest.lower() if digest_valid else digest
    if (
        digest_valid
        and artifact_sha256
        and normalized_digest != artifact_sha256
        and allow_artifact_digest_fallback
        and legacy_reconstruction_status == "reconstructed"
        and legacy_behavior_delta_sha256 == artifact_sha256
    ):
        normalized_digest = legacy_behavior_delta_sha256
        digest = legacy_behavior_delta_sha256
        digest_source = "legacy_reconstruction_artifact"
    artifact_match = bool(digest_valid and artifact_sha256 and artifact_sha256 == normalized_digest)
    if not behavior_delta_path or not artifact_exists:
        artifact_status = "not_available"
    elif artifact_match:
        artifact_status = "pass"
    else:
        artifact_status = "mismatch"
    strict_secondary = bool(telemetry.get("strict_secondary_improvement_present", False))
    axes = _string_list(telemetry.get("secondary_improvement_axes"))
    secondary_axis_evidence_source = "telemetry_field" if strict_secondary and axes else "missing"
    secondary_axis_evidence_detail = ""
    if allow_artifact_digest_fallback and (not strict_secondary or not axes):
        legacy_strict = bool(legacy_reconstruction.get("parsed_strict_secondary_improvement_present"))
        legacy_axes = _string_list(legacy_reconstruction.get("parsed_secondary_axes"))
        legacy_evidence = dict_value(legacy_reconstruction.get("parsed_secondary_axis_evidence"))
        strict_secondary = strict_secondary or legacy_strict
        axes = axes or legacy_axes
        if legacy_strict or legacy_axes:
            secondary_axis_evidence_source = "legacy_reconstruction_artifact"
            secondary_axis_evidence_detail = str(legacy_evidence.get("detail", "")).strip()
    return {
        "run_id": run_id,
        "telemetry_path": report_path(vault, telemetry_path) if telemetry_path else "",
        "exists": bool(telemetry),
        "sha256": _sha256_file(telemetry_path) if telemetry_path and telemetry_path.is_file() else "",
        "decision": str(telemetry.get("decision", "")).strip(),
        "behavior_delta_path": behavior_delta_path,
        "behavior_delta_artifact_exists": artifact_exists,
        "behavior_delta_artifact_sha256": artifact_sha256,
        "behavior_delta_artifact_digest_match": artifact_match,
        "behavior_delta_artifact_readback_status": artifact_status,
        "same_eval_reason_code": str(telemetry.get("same_eval_reason_code", "")).strip(),
        "strict_secondary_improvement_present": strict_secondary,
        "secondary_improvement_axes": axes,
        "behavior_delta_digest": normalized_digest,
        "behavior_delta_digest_present": digest_present,
        "behavior_delta_digest_valid": digest_valid,
        "behavior_delta_digest_source": digest_source,
        "promotion_report_path": report_path(vault, promotion_path) if promotion_path else "",
        "legacy_reconstruction_path": LEGACY_RECONSTRUCTION_PATH if legacy_reconstruction else "",
        "legacy_reconstruction_status": legacy_reconstruction_status,
        "legacy_reconstruction_selection_reason": str(
            legacy_reconstruction.get("selection_reason", "")
        ).strip(),
        "legacy_reconstruction_reasons": _string_list(legacy_reconstruction.get("reasons")),
        "secondary_axis_evidence_source": secondary_axis_evidence_source,
        "secondary_axis_evidence_detail": secondary_axis_evidence_detail,
    }


def _evidence_item(vault: Path, item_id: str, rel_path: str, role: str) -> dict[str, Any]:
    path = vault / rel_path
    exists = path.is_file()
    sha256 = _sha256_file(path) if exists else ""
    return {
        "id": item_id,
        "path": rel_path,
        "role": role,
        "required": True,
        "exists": exists,
        "sha256": sha256,
        "status": "present" if exists else "missing",
        "revocation_effect": "none" if exists else "revoked",
    }


def _telemetry_evidence(
    vault: Path,
    run_ids: list[str],
    *,
    legacy_reconstruction_by_run: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in _telemetry_item(
                vault,
                run_id,
                allow_artifact_digest_fallback=True,
                legacy_reconstruction_by_run=legacy_reconstruction_by_run,
            ).items()
            if key != "promotion_report_path"
        }
        for run_id in run_ids
    ]


def _confirmed_run_family_map(
    mutation_proposals: dict[str, Any],
    mechanism_review: dict[str, Any],
) -> dict[str, list[str]]:
    active_families = set(_proposal_families(mutation_proposals))
    active_targets = _proposal_target_keys(mutation_proposals)
    mapping: dict[str, list[str]] = {}
    candidates = mechanism_review.get("candidates", [])
    if not isinstance(candidates, list):
        return mapping
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        family = str(candidate.get("family", "")).strip()
        primary_targets = _target_key(candidate.get("primary_targets"))
        if active_families and family not in active_families and primary_targets not in active_targets:
            continue
        if not family:
            family = "unknown"
        for run_id in _string_list(candidate.get("run_ids")):
            mapping.setdefault(run_id, [])
            if family not in mapping[run_id]:
                mapping[run_id].append(family)
    return mapping


def _confirmed_telemetry_evidence(
    vault: Path,
    run_families: dict[str, list[str]],
    *,
    legacy_reconstruction_by_run: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence = []
    for run_id, families in run_families.items():
        item = _telemetry_item(
            vault,
            run_id,
            allow_artifact_digest_fallback=True,
            legacy_reconstruction_by_run=legacy_reconstruction_by_run,
        )
        item["families"] = families
        evidence.append(item)
    return evidence


def _confirmed_run_artifacts(vault: Path, run_ids: list[str]) -> list[dict[str, Any]]:
    rows = []
    for run_id in run_ids:
        artifacts = []
        for artifact_id, filename in CONFIRMED_RUN_ARTIFACT_SPECS:
            path = _run_artifact_path_for_run(vault, run_id, filename)
            exists = bool(path and path.is_file())
            artifacts.append(
                {
                    "id": artifact_id,
                    "path": report_path(vault, path) if path else f"runs/{run_id}/{filename}",
                    "exists": exists,
                    "sha256": _sha256_file(path) if path and exists else "",
                    "required_for_confirmed": True,
                    "status": "present" if exists else "missing",
                }
            )
        missing_count = sum(1 for item in artifacts if item["required_for_confirmed"] and not item["exists"])
        rows.append(
            {
                "run_id": run_id,
                "artifacts": artifacts,
                "required_artifact_count": len(artifacts),
                "present_required_artifact_count": len(artifacts) - missing_count,
                "missing_required_artifact_count": missing_count,
                "status": "pass" if missing_count == 0 else "missing_required_artifact",
            }
        )
    return rows


def _revocation(
    evidence_items: list[dict[str, Any]],
    telemetry_evidence: list[dict[str, Any]],
    confirmed_telemetry_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    revoked_item_ids = [
        str(item["id"])
        for item in evidence_items
        if item["required"] and not item["exists"]
    ]
    reasons = [
        f"required evidence item missing: {item['id']}"
        for item in evidence_items
        if item["required"] and not item["exists"]
    ]
    for item in telemetry_evidence:
        run_id = str(item.get("run_id", "")).strip()
        if not item.get("exists"):
            revoked_item_ids.append(f"telemetry:{run_id}")
            reasons.append(f"run telemetry missing: {run_id}")
            continue
        if not item.get("behavior_delta_digest_present"):
            revoked_item_ids.append(f"behavior_delta_digest:{run_id}")
            reasons.append(f"behavior_delta_digest missing in run telemetry: {run_id}")
        elif not item.get("behavior_delta_digest_valid"):
            revoked_item_ids.append(f"behavior_delta_digest:{run_id}")
            reasons.append(f"behavior_delta_digest is not a sha256 digest in run telemetry: {run_id}")
        elif str(item.get("behavior_delta_artifact_readback_status", "")) == "mismatch":
            revoked_item_ids.append(f"behavior_delta_artifact_digest:{run_id}")
            reasons.append(f"behavior_delta artifact digest mismatch: {run_id}")
    for item in confirmed_telemetry_evidence:
        run_id = str(item.get("run_id", "")).strip()
        if not item.get("exists"):
            revoked_item_ids.append(f"confirmed_telemetry:{run_id}")
            reasons.append(f"confirmed run telemetry missing: {run_id}")
            continue
        if not item.get("behavior_delta_digest_present"):
            revoked_item_ids.append(f"confirmed_behavior_delta_digest:{run_id}")
            reasons.append(f"confirmed behavior_delta_digest missing after artifact readback: {run_id}")
        elif not item.get("behavior_delta_digest_valid"):
            revoked_item_ids.append(f"confirmed_behavior_delta_digest:{run_id}")
            reasons.append(f"confirmed behavior_delta_digest is not a sha256 digest: {run_id}")
        elif str(item.get("behavior_delta_artifact_readback_status", "")) == "mismatch":
            revoked_item_ids.append(f"confirmed_behavior_delta_artifact_digest:{run_id}")
            reasons.append(f"confirmed behavior_delta artifact digest mismatch: {run_id}")
    status = "revoked" if revoked_item_ids else "active"
    return {
        "status": status,
        "reasons": reasons,
        "stale_item_ids": [],
        "revoked_item_ids": revoked_item_ids,
    }


def _identity_payload(
    evidence_items: list[dict[str, Any]],
    run_set: dict[str, Any],
    telemetry_evidence: list[dict[str, Any]],
    confirmed_run_set: dict[str, Any],
    confirmed_telemetry_evidence: list[dict[str, Any]],
    confirmed_run_artifacts: list[dict[str, Any]],
    revocation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "bundle_payload_version": 1,
        "evidence_items": [
            {
                "id": item["id"],
                "path": item["path"],
                "role": item["role"],
                "required": item["required"],
                "exists": item["exists"],
                "sha256": item["sha256"],
                "status": item["status"],
            }
            for item in evidence_items
        ],
        "run_set": run_set,
        "telemetry_evidence": telemetry_evidence,
        "confirmed_run_set": confirmed_run_set,
        "confirmed_telemetry_evidence": confirmed_telemetry_evidence,
        "confirmed_run_artifacts": confirmed_run_artifacts,
        "revocation": {
            "status": revocation["status"],
            "reasons": revocation["reasons"],
            "revoked_item_ids": revocation["revoked_item_ids"],
        },
    }


def _learning_claim_run_set(mutation_proposals: dict[str, Any]) -> dict[str, Any]:
    run_ids = _proposal_run_ids(mutation_proposals)
    return {
        "source_path": "ops/reports/mutation-proposals.json",
        "run_ids": run_ids,
        "run_count": len(run_ids),
        "proposal_families": _proposal_families(mutation_proposals),
        "run_set_digest": _canonical_sha256({"run_ids": run_ids}),
    }


def _confirmed_run_set(confirmed_run_families: dict[str, list[str]]) -> dict[str, Any]:
    confirmed_run_ids = list(confirmed_run_families)
    return {
        "source_path": MECHANISM_REVIEW_CANDIDATES_PATH,
        "run_ids": confirmed_run_ids,
        "run_count": len(confirmed_run_ids),
        "proposal_families": sorted(
            {family for families in confirmed_run_families.values() for family in families}
        ),
        "run_families": [
            {"run_id": run_id, "families": confirmed_run_families[run_id]}
            for run_id in confirmed_run_ids
        ],
        "run_set_digest": _canonical_sha256(
            {"run_ids": confirmed_run_ids, "run_families": confirmed_run_families}
        ),
    }


def _behavior_delta_readback(
    telemetry: list[dict[str, Any]],
    confirmed_telemetry: list[dict[str, Any]],
) -> BehaviorDeltaReadback:
    digest_missing_count = sum(1 for item in telemetry if not item["behavior_delta_digest_present"])
    digest_mismatch_count = sum(
        1
        for item in telemetry
        if item["behavior_delta_digest_present"] and not item["behavior_delta_digest_valid"]
    )
    digest_readback_status = "not_applicable"
    if telemetry:
        digest_readback_status = "pass" if digest_missing_count == 0 and digest_mismatch_count == 0 else "revoked"
    combined_telemetry = [*telemetry, *confirmed_telemetry]
    digest_missing_count_all = sum(
        1 for item in combined_telemetry if not item["behavior_delta_digest_present"]
    )
    digest_mismatch_count_all = sum(
        1
        for item in combined_telemetry
        if item["behavior_delta_digest_present"] and not item["behavior_delta_digest_valid"]
    )
    if confirmed_telemetry:
        digest_readback_status = "pass" if digest_missing_count_all == 0 and digest_mismatch_count_all == 0 else "revoked"
    artifact_missing_count = sum(
        1
        for item in combined_telemetry
        if str(item.get("behavior_delta_artifact_readback_status", "")) == "not_available"
    )
    artifact_mismatch_count = sum(
        1
        for item in combined_telemetry
        if str(item.get("behavior_delta_artifact_readback_status", "")) == "mismatch"
    )
    artifact_readback_status = "not_applicable"
    if combined_telemetry:
        if artifact_mismatch_count:
            artifact_readback_status = "revoked"
        elif artifact_missing_count:
            artifact_readback_status = "not_available"
        else:
            artifact_readback_status = "pass"
    return BehaviorDeltaReadback(
        telemetry_missing_count=sum(1 for item in telemetry if not item["exists"]),
        digest_missing_count=digest_missing_count,
        digest_mismatch_count=digest_mismatch_count,
        digest_missing_count_all=digest_missing_count_all,
        digest_mismatch_count_all=digest_mismatch_count_all,
        digest_readback_status=digest_readback_status,
        artifact_missing_count=artifact_missing_count,
        artifact_mismatch_count=artifact_mismatch_count,
        artifact_readback_status=artifact_readback_status,
    )


def _evidence_item_sha256(evidence_items: list[dict[str, Any]], item_id: str) -> str:
    return next(
        (
            str(item["sha256"])
            for item in evidence_items
            if item["id"] == item_id
        ),
        "",
    )


def _learning_claim_evidence_summary(
    *,
    bundle_digest: str,
    evidence_items: list[dict[str, Any]],
    run_set: dict[str, Any],
    telemetry: list[dict[str, Any]],
    confirmed_telemetry: list[dict[str, Any]],
    confirmed_run_artifacts: list[dict[str, Any]],
    revocation: dict[str, Any],
    readback: BehaviorDeltaReadback,
    legacy_reconstruction: dict[str, Any],
) -> dict[str, Any]:
    legacy_summary = dict_value(legacy_reconstruction.get("summary"))
    return {
        "bundle_sha256": bundle_digest,
        "revocation_status": revocation["status"],
        "bundle_item_count": len(evidence_items),
        "missing_required_count": sum(1 for item in evidence_items if item["required"] and not item["exists"]),
        "stale_evidence_count": 0,
        "revoked_evidence_count": len(revocation["revoked_item_ids"]),
        "telemetry_run_count": len(telemetry),
        "telemetry_missing_count": readback.telemetry_missing_count,
        "behavior_delta_digest_missing_count": readback.digest_missing_count,
        "behavior_delta_digest_mismatch_count": readback.digest_mismatch_count,
        "confirmed_telemetry_run_count": len(confirmed_telemetry),
        "confirmed_telemetry_missing_count": sum(1 for item in confirmed_telemetry if not item["exists"]),
        "confirmed_behavior_delta_digest_missing_count": sum(
            1 for item in confirmed_telemetry if not item["behavior_delta_digest_present"]
        ),
        "confirmed_behavior_delta_artifact_mismatch_count": sum(
            1
            for item in confirmed_telemetry
            if str(item.get("behavior_delta_artifact_readback_status", "")) == "mismatch"
        ),
        "confirmed_run_artifact_missing_count": sum(
            int(row["missing_required_artifact_count"]) for row in confirmed_run_artifacts
        ),
        "behavior_delta_artifact_missing_count": readback.artifact_missing_count,
        "behavior_delta_artifact_mismatch_count": readback.artifact_mismatch_count,
        "behavior_delta_artifact_readback_status": readback.artifact_readback_status,
        "legacy_reconstruction_sha256": _evidence_item_sha256(
            evidence_items,
            "learning_confirmed_legacy_reconstruction",
        ),
        "legacy_reconstruction_status": str(
            legacy_reconstruction.get("status", "missing")
        ).strip()
        or "missing",
        "legacy_reconstruction_blocked_run_count": int(
            legacy_summary.get("blocked_run_count", 0)
        ),
        "legacy_reconstruction_operator_summary": legacy_summary.get(
            "operator_reconstruction_diagnostics",
            [],
        ),
        "external_manifest_sha256": _evidence_item_sha256(
            evidence_items,
            "external_report_reference_manifest",
        ),
        "run_set_digest": run_set["run_set_digest"],
    }


def _learning_claim_evidence_input_paths(
    evidence_items: list[dict[str, Any]],
    telemetry: list[dict[str, Any]],
    confirmed_telemetry: list[dict[str, Any]],
    confirmed_run_artifacts: list[dict[str, Any]],
) -> list[str]:
    return (
        [item["path"] for item in evidence_items]
        + [
            item["telemetry_path"]
            for item in [*telemetry, *confirmed_telemetry]
            if item["telemetry_path"]
        ]
        + [
            item["promotion_report_path"]
            for item in confirmed_telemetry
            if item.get("promotion_report_path")
        ]
        + [
            artifact["path"]
            for row in confirmed_run_artifacts
            for artifact in row["artifacts"]
            if artifact.get("path")
        ]
    )


def build_report(
    vault: Path,
    *,
    out_path: str = DEFAULT_OUT,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    mutation_proposals = load_optional_json_object(vault / "ops/reports/mutation-proposals.json")
    mechanism_review = load_optional_json_object(vault / MECHANISM_REVIEW_CANDIDATES_PATH)
    legacy_reconstruction = load_optional_json_object(vault / LEGACY_RECONSTRUCTION_PATH)
    legacy_reconstruction_rows = _legacy_reconstruction_by_run(legacy_reconstruction)
    evidence_items = [
        _evidence_item(vault, item_id, rel_path, role)
        for item_id, rel_path, role in REQUIRED_EVIDENCE_SPECS
    ]
    run_set = _learning_claim_run_set(mutation_proposals)
    confirmed_run_families = _confirmed_run_family_map(mutation_proposals, mechanism_review)
    confirmed_run_set = _confirmed_run_set(confirmed_run_families)
    telemetry = _telemetry_evidence(
        vault,
        run_set["run_ids"],
        legacy_reconstruction_by_run=legacy_reconstruction_rows,
    )
    confirmed_telemetry = _confirmed_telemetry_evidence(
        vault,
        confirmed_run_families,
        legacy_reconstruction_by_run=legacy_reconstruction_rows,
    )
    confirmed_run_artifacts = _confirmed_run_artifacts(vault, confirmed_run_set["run_ids"])
    revocation = _revocation(evidence_items, telemetry, confirmed_telemetry)
    identity_payload = _identity_payload(
        evidence_items,
        run_set,
        telemetry,
        confirmed_run_set,
        confirmed_telemetry,
        confirmed_run_artifacts,
        revocation,
    )
    bundle_digest = _canonical_sha256(identity_payload)
    readback = _behavior_delta_readback(telemetry, confirmed_telemetry)

    source_paths = [
        "ops/scripts/learning/learning_claim_evidence_bundle.py",
        "ops/scripts/learning/learning_confirmed_legacy_reconstruction.py",
        "ops/scripts/learning/learning_claim_unlock_review.py",
        "ops/scripts/learning/learning_delta_scoreboard.py",
    ]
    input_paths = _learning_claim_evidence_input_paths(
        evidence_items,
        telemetry,
        confirmed_telemetry,
        confirmed_run_artifacts,
    )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="learning_claim_evidence_bundle",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=source_paths,
            path_group_inputs={"learning_claim_evidence_bundle_inputs": input_paths},
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "status": "pass" if revocation["status"] == "active" else "fail",
        "summary": _learning_claim_evidence_summary(
            bundle_digest=bundle_digest,
            evidence_items=evidence_items,
            run_set=run_set,
            telemetry=telemetry,
            confirmed_telemetry=confirmed_telemetry,
            confirmed_run_artifacts=confirmed_run_artifacts,
            revocation=revocation,
            readback=readback,
            legacy_reconstruction=legacy_reconstruction,
        ),
        "bundle_identity": {
            "digest_algorithm": "sha256",
            "bundle_payload_version": 1,
            "evidence_bundle_digest": bundle_digest,
        },
        "evidence_items": evidence_items,
        "run_set": run_set,
        "telemetry_evidence": telemetry,
        "confirmed_run_set": confirmed_run_set,
        "confirmed_telemetry_evidence": confirmed_telemetry,
        "confirmed_run_artifacts": confirmed_run_artifacts,
        "behavior_delta_digest_readback": {
            "status": readback.digest_readback_status,
            "missing_count": readback.digest_missing_count_all,
            "mismatch_count": readback.digest_mismatch_count_all,
            "source": "run_telemetry.behavior_delta_digest or confirmed behavior_delta artifact readback",
        },
        "behavior_delta_artifact_readback": {
            "status": readback.artifact_readback_status,
            "missing_count": readback.artifact_missing_count,
            "mismatch_count": readback.artifact_mismatch_count,
            "source": "run_telemetry.behavior_delta -> behavior_delta_digest",
        },
        "revocation": revocation,
    }


def validate_learning_claim_evidence_bundle(
    vault: Path,
    *,
    bundle_path: str = DEFAULT_OUT,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    stored = load_optional_json_object(vault / bundle_path)
    if not stored:
        return {
            "bundle_path": bundle_path,
            "bundle_status": "missing",
            "bundle_sha256": "",
            "current_bundle_sha256": "",
            "bundle_fingerprint_match_status": "missing",
            "revocation_status": "revoked",
            "reasons": ["learning claim evidence bundle is missing"],
        }
    current = build_report(vault, context=context)
    stored_identity = stored.get("bundle_identity")
    stored_digest = (
        str(stored_identity.get("evidence_bundle_digest", "")).strip()
        if isinstance(stored_identity, dict)
        else ""
    )
    current_digest = str(current["bundle_identity"]["evidence_bundle_digest"])
    current_revocation = str(current.get("revocation", {}).get("status", "revoked"))
    fingerprint_match = stored_digest == current_digest and bool(stored_digest)
    if current_revocation == "revoked":
        bundle_status = "revoked"
        revocation_status = "revoked"
        reasons = [
            str(reason)
            for reason in current.get("revocation", {}).get("reasons", [])
            if str(reason).strip()
        ]
    elif not fingerprint_match:
        bundle_status = "stale"
        revocation_status = "stale"
        reasons = ["learning claim evidence bundle digest no longer matches current evidence"]
    else:
        bundle_status = "active"
        revocation_status = "active"
        reasons = []
    return {
        "bundle_path": bundle_path,
        "bundle_status": bundle_status,
        "bundle_sha256": stored_digest,
        "current_bundle_sha256": current_digest,
        "bundle_fingerprint_match_status": "match" if fingerprint_match else "mismatch",
        "revocation_status": revocation_status,
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
            context="learning claim evidence bundle schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build learning claim evidence bundle")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, out_path=args.out)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
