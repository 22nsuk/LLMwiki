from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import (
    build_canonical_report_envelope,
    canonical_artifact_payload,
    canonical_report_loading_issue,
    format_artifact_mtime,
    load_zip_info_mtimes,
    mtime_for_artifact_source,
)
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.core.release_currentness_state_runtime import (
    CURRENTNESS_DOMAIN_MODE_REUSABLE,
    currentness_classification_record,
    currentness_field,
)
from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_ADVISORY,
    GATE_EFFECT_BLOCKS_PROMOTION,
    canonical_gate_effect,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import RELEASE_EVIDENCE_COHORT_SCHEMA_PATH
from ops.scripts.source_revision_runtime import resolve_source_revision
from ops.scripts.source_tree_fingerprint_runtime import (
    producer_input_fingerprint,
    release_source_tree_divergence_diagnostics,
    release_source_tree_fingerprint,
)

from .release_closeout_summary import (
    BASE_PROFILE,
    VALID_PROFILES,
    SourceSpec,
    source_specs_for_profile,
)

DEFAULT_OUT = "ops/reports/release-evidence-cohort.json"
PRODUCER = "ops.scripts.release_evidence_cohort"
SOURCE_COMMAND_TEMPLATE = (
    "python -m ops.scripts.release_evidence_cohort --vault . --profile {profile} "
    "--cohort-policy {policy} --provenance-mode {provenance_mode}"
)
STRICT_SAME_FINGERPRINT = "strict_same_fingerprint"
ALLOWED_DIVERGENCE_WITH_EXPLICIT_RISK = "allowed_divergence_with_explicit_risk"
COHORT_POLICIES = (STRICT_SAME_FINGERPRINT, ALLOWED_DIVERGENCE_WITH_EXPLICIT_RISK)
EMBEDDED_CURRENTNESS = "embedded_currentness"
FILESYSTEM_MTIME = "filesystem"
ZIP_INFO = "zip_info"
PROVENANCE_MODES = (EMBEDDED_CURRENTNESS, FILESYSTEM_MTIME, ZIP_INFO)
ARTIFACT_KIND = "release_evidence_cohort"
COHORT_RISK_ACCEPTED_BY = "release_evidence_cohort_policy"
COHORT_RISK_ACCEPTANCE_DAYS = 7
RELEASE_CLOSEOUT_CLEAN_PASS = "clean_pass"


@dataclass(frozen=True)
class CohortSourceSpec:
    target: str
    name: str
    path: str
    artifact_kind: str
    include_in_ordered_chain: bool = True


BASE_COHORT_SOURCE_SPECS = (
    CohortSourceSpec(
        "bootstrap-preflight",
        "bootstrap_preflight",
        "ops/reports/bootstrap-preflight-report.json",
        "bootstrap_preflight_report",
    ),
    CohortSourceSpec(
        "release-smoke-full",
        "release_smoke",
        "ops/reports/release-smoke-report.json",
        "release_smoke_report",
    ),
    CohortSourceSpec(
        "release-source-package-check",
        "source_package_clean_extract",
        "ops/reports/source-package-clean-extract.json",
        "source_package_clean_extract",
        include_in_ordered_chain=False,
    ),
    CohortSourceSpec(
        "registry-preflight",
        "raw_registry",
        "ops/reports/raw-registry-preflight-report.json",
        "raw_registry_preflight_report",
    ),
    CohortSourceSpec(
        "test-execution-summary",
        "test_summary",
        "ops/reports/test-execution-summary.json",
        "test_execution_summary",
    ),
    CohortSourceSpec(
        "test-execution-summary-full",
        "test_summary_full",
        "ops/reports/test-execution-summary-full.json",
        "test_execution_summary",
    ),
    CohortSourceSpec(
        "auto-improve-readiness",
        "auto_improve_readiness",
        "ops/reports/auto-improve-readiness.json",
        "auto_improve_readiness_report",
    ),
    CohortSourceSpec(
        "generated-artifact-index",
        "generated_index",
        "ops/reports/generated-artifact-index.json",
        "generated_artifact_index_report",
    ),
    CohortSourceSpec(
        "artifact-freshness",
        "artifact_freshness",
        "ops/reports/artifact-freshness-report.json",
        "artifact_freshness_report",
    ),
    CohortSourceSpec(
        "release-closeout-summary",
        "release_closeout_summary",
        "ops/reports/release-closeout-summary.json",
        "release_closeout_summary",
    ),
)


OPTIONAL_COHORT_SOURCE_SPECS = {
    "supply_chain_gate": CohortSourceSpec(
        "supply-chain-check",
        "supply_chain_gate",
        "ops/reports/supply-chain-gate-report.json",
        "supply_chain_gate_report",
    ),
    "sbom_readiness": CohortSourceSpec(
        "sbom-readiness-check",
        "sbom_readiness",
        "ops/reports/sbom-readiness-gate-report.json",
        "sbom_readiness_gate_report",
    ),
}


def _cohort_source_specs_for_profile(profile: str) -> tuple[CohortSourceSpec, ...]:
    closeout_specs = source_specs_for_profile(profile)
    base_names = {item.name for item in BASE_COHORT_SOURCE_SPECS}
    extras = [
        OPTIONAL_COHORT_SOURCE_SPECS[item.name]
        for item in closeout_specs
        if item.name not in base_names and item.name in OPTIONAL_COHORT_SOURCE_SPECS
    ]
    return (*BASE_COHORT_SOURCE_SPECS[:-1], *extras, BASE_COHORT_SOURCE_SPECS[-1])


def _parse_iso_z(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _coerce_non_negative_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value >= 0 else default
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("+"):
            stripped = stripped[1:]
        if stripped.isdigit():
            return int(stripped)
    return default


def _file_mtime_iso_z(path: Path) -> str:
    if not path.exists():
        return ""
    modified_at = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
    return modified_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _modified_after_generated_at(report_mtime: str, generated_at: str) -> bool:
    modified_at = _parse_iso_z(report_mtime)
    generated = _parse_iso_z(generated_at)
    if modified_at is None or generated is None:
        return False
    return modified_at > generated


def _issue(
    *,
    source: str,
    source_path: str,
    code: str,
    message: str,
    severity: str = "blocker",
    gate_effect: str = GATE_EFFECT_BLOCKS_PROMOTION,
    required_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_path": source_path,
        "code": code,
        "severity": severity,
        "gate_effect": canonical_gate_effect(
            gate_effect,
            active_default=GATE_EFFECT_BLOCKS_PROMOTION,
        ),
        "message": message,
        "required_evidence": required_evidence or [],
    }


def _format_iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _expires_after(generated_at: str, *, days: int) -> str:
    generated = _parse_iso_z(generated_at)
    if generated is None:
        return generated_at
    return _format_iso_z(generated + dt.timedelta(days=days))


def _accepted_cohort_risk(issue: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    accepted = dict(issue)
    accepted["severity"] = "warn"
    accepted["gate_effect"] = GATE_EFFECT_ADVISORY
    code = str(issue.get("code", "")).strip()
    if code == "cohort_modified_after_generated_at":
        revalidation_condition = "Regenerate affected reports and rerun release-evidence-cohort before release."
        rollback_trigger = "Treat mtime drift as a blocker if affected reports cannot be regenerated or explained."
    else:
        revalidation_condition = "Rerun the ordered release evidence chain before the next release closeout."
        rollback_trigger = "Treat cohort fingerprint divergence as a blocker if policy requires strict same-fingerprint evidence."
    accepted["risk_acceptance"] = {
        "accepted_by": COHORT_RISK_ACCEPTED_BY,
        "accepted_at": generated_at,
        "expires_at": _expires_after(generated_at, days=COHORT_RISK_ACCEPTANCE_DAYS),
        "risk_owner": "runtime-maintainer",
        "revalidation_condition": revalidation_condition,
        "rollback_trigger": rollback_trigger,
        "acceptance_source": "cohort_policy",
    }
    return accepted


def _component_from_payload(
    spec: SourceSpec | CohortSourceSpec,
    payload: dict[str, Any],
    *,
    load_status: str,
    issues: list[dict[str, Any]],
    path: Path,
    provenance_mode: str,
    report_mtime: str,
    modified_after_generated_at: bool,
    head_revision: str,
    current_source_tree_fingerprint: str,
) -> dict[str, Any]:
    payload = canonical_artifact_payload(payload)
    generated_at = str(payload.get("generated_at", "")).strip()
    deselected_tests = payload.get("deselected_tests")
    accepted_risks = payload.get("accepted_risks")
    accepted_risk_scope = payload.get("accepted_risk_count_by_scope")
    if not isinstance(accepted_risk_scope, dict):
        accepted_risk_scope = {}
    evidence_artifacts = payload.get("evidence_artifacts")
    if not isinstance(evidence_artifacts, list):
        evidence_artifacts = []
    source_revision = str(payload.get("source_revision", "")).strip()
    currentness_status = currentness_field(payload, "status") or "unknown"
    currentness_checked_at = currentness_field(payload, "checked_at")
    currentness_record = currentness_classification_record(
        report_path=spec.path,
        self_declared_status=currentness_status,
        source_revision=source_revision,
        head_revision=head_revision,
        source_tree_fingerprint=str(payload.get("source_tree_fingerprint", "")).strip(),
        current_source_tree_fingerprint=current_source_tree_fingerprint,
        domain_current_check_passes=not modified_after_generated_at,
        domain_mode=CURRENTNESS_DOMAIN_MODE_REUSABLE,
    )
    raw_clean_lane_blocking_count = payload.get("clean_lane_blocking_risk_family_count")
    if raw_clean_lane_blocking_count is None:
        raw_clean_lane_blocking_count = len(accepted_risks) if isinstance(accepted_risks, list) else 0
    clean_lane_blocking_risk_family_count = _coerce_non_negative_int(raw_clean_lane_blocking_count, default=0)
    return {
        "name": spec.name,
        "path": spec.path,
        "expected_artifact_kind": spec.artifact_kind,
        "load_status": load_status,
        "source_status": str(payload.get("status", "")).strip() or "unknown",
        "generated_at": generated_at,
        "source_revision": source_revision,
        "source_tree_fingerprint": str(payload.get("source_tree_fingerprint", "")).strip(),
        "producer_input_fingerprint": producer_input_fingerprint(payload),
        "artifact_status": str(payload.get("artifact_status", "")).strip() or "unknown",
        "currentness_status": currentness_status,
        "currentness_checked_at": currentness_checked_at,
        "source_revision_matches_head": currentness_record["source_revision_matches_head"],
        "source_tree_fingerprint_matches": currentness_record["source_tree_fingerprint_matches"],
        "domain_current_check_passes": currentness_record["domain_current_check_passes"],
        "operator_facing_classification": currentness_record[
            "operator_facing_classification"
        ],
        "classification_reason": currentness_record["classification_reason"],
        "provenance_mode": provenance_mode,
        "report_mtime_source": provenance_mode,
        "report_mtime": report_mtime,
        "modified_after_generated_at": modified_after_generated_at,
        "deselected_test_count": len(deselected_tests) if isinstance(deselected_tests, list) else 0,
        "accepted_risk_family_count": len(accepted_risks) if isinstance(accepted_risks, list) else 0,
        "clean_lane_blocking_risk_family_count": clean_lane_blocking_risk_family_count,
        "learning_claim_blocking_risk_family_count": _coerce_non_negative_int(
            accepted_risk_scope.get("learning_claim_blocking_family_count", 0),
            default=0,
        ),
        "advisory_lifecycle_risk_family_count": _coerce_non_negative_int(
            accepted_risk_scope.get("advisory_lifecycle_family_count", 0),
            default=0,
        ),
        "release_readiness_state": str(payload.get("release_readiness_state", "")).strip(),
        "machine_release_allowed": bool(payload.get("machine_release_allowed", False)),
        "evidence_artifact_count": len(evidence_artifacts),
        "evidence_artifacts": [
            item for item in evidence_artifacts if isinstance(item, dict)
        ],
        "issue_count": len(issues),
    }


def _empty_component(
    spec: SourceSpec | CohortSourceSpec,
    *,
    load_status: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": spec.name,
        "path": spec.path,
        "expected_artifact_kind": spec.artifact_kind,
        "load_status": load_status,
        "source_status": "unknown",
        "generated_at": "",
        "source_revision": "",
        "source_tree_fingerprint": "",
        "producer_input_fingerprint": "",
        "artifact_status": "unknown",
        "currentness_status": "unknown",
        "currentness_checked_at": "",
        "source_revision_matches_head": False,
        "source_tree_fingerprint_matches": False,
        "domain_current_check_passes": False,
        "operator_facing_classification": "artifact_current_but_head_stale",
        "classification_reason": "source_tree_fingerprint_mismatch",
        "provenance_mode": "",
        "report_mtime_source": "",
        "report_mtime": "",
        "modified_after_generated_at": False,
        "deselected_test_count": 0,
        "accepted_risk_family_count": 0,
        "clean_lane_blocking_risk_family_count": 0,
        "learning_claim_blocking_risk_family_count": 0,
        "advisory_lifecycle_risk_family_count": 0,
        "release_readiness_state": "",
        "machine_release_allowed": False,
        "evidence_artifact_count": 0,
        "evidence_artifacts": [],
        "issue_count": len(issues),
    }


def _component_report_mtime(
    path: Path,
    rel_path: str,
    *,
    provenance_mode: str,
    zip_mtimes: dict[str, dt.datetime],
) -> str:
    return format_artifact_mtime(
        mtime_for_artifact_source(
            path,
            rel_path,
            mtime_source=provenance_mode,
            zip_mtimes=zip_mtimes,
        )
    )


def _load_component(
    vault: Path,
    spec: SourceSpec | CohortSourceSpec,
    *,
    provenance_mode: str,
    zip_mtimes: dict[str, dt.datetime],
    head_revision: str,
    current_source_tree_fingerprint: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = vault / spec.path
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        load_issues = [
            _issue(
                source=spec.name,
                source_path=spec.path,
                code=f"{spec.name}_report_{load_status}",
                message=f"{spec.path} could not be loaded: {diagnostics.get('message', load_status)}",
                required_evidence=[f"Regenerate {spec.path} before release evidence cohort closeout."],
            )
        ]
        return _empty_component(spec, load_status=load_status, issues=load_issues), load_issues

    normalized_payload = canonical_artifact_payload(payload)
    generated_at = str(normalized_payload.get("generated_at", "")).strip()
    report_mtime = _component_report_mtime(
        path,
        spec.path,
        provenance_mode=provenance_mode,
        zip_mtimes=zip_mtimes,
    )
    modified_after_generated_at = _modified_after_generated_at(report_mtime, generated_at)
    loading_issue = canonical_report_loading_issue(path, payload)
    if loading_issue is not None:
        currentness_issues = [
            _issue(
                source=spec.name,
                source_path=spec.path,
                code=f"{spec.name}_report_not_current",
                message=f"{spec.path} is not usable cohort evidence: {loading_issue}.",
                required_evidence=[f"Regenerate {spec.path} with a current canonical artifact envelope."],
            )
        ]
        return (
            _component_from_payload(
                spec,
                normalized_payload,
                load_status="unusable",
                issues=currentness_issues,
                path=path,
                provenance_mode=provenance_mode,
                report_mtime=report_mtime,
                modified_after_generated_at=modified_after_generated_at,
                head_revision=head_revision,
                current_source_tree_fingerprint=current_source_tree_fingerprint,
            ),
            currentness_issues,
        )

    artifact_kind = str(normalized_payload.get("artifact_kind", "")).strip()
    if artifact_kind != spec.artifact_kind:
        kind_issues = [
            _issue(
                source=spec.name,
                source_path=spec.path,
                code=f"{spec.name}_artifact_kind_mismatch",
                message=(
                    f"{spec.path} declares artifact_kind={artifact_kind or '<missing>'}; "
                    f"expected {spec.artifact_kind}."
                ),
                required_evidence=[f"Regenerate {spec.path} from the expected producer."],
            )
        ]
        return (
            _component_from_payload(
                spec,
                normalized_payload,
                load_status="kind_mismatch",
                issues=kind_issues,
                path=path,
                provenance_mode=provenance_mode,
                report_mtime=report_mtime,
                modified_after_generated_at=modified_after_generated_at,
                head_revision=head_revision,
                current_source_tree_fingerprint=current_source_tree_fingerprint,
            ),
            kind_issues,
        )

    component_issues: list[dict[str, Any]] = []
    if not str(normalized_payload.get("source_tree_fingerprint", "")).strip():
        component_issues.append(
            _issue(
                source=spec.name,
                source_path=spec.path,
                code=f"{spec.name}_missing_source_tree_fingerprint",
                message=f"{spec.path} is missing source_tree_fingerprint.",
                required_evidence=[f"Regenerate {spec.path} with the canonical artifact envelope."],
            )
        )
    return (
        _component_from_payload(
            spec,
            normalized_payload,
            load_status="ok",
            issues=component_issues,
            path=path,
            provenance_mode=provenance_mode,
            report_mtime=report_mtime,
            modified_after_generated_at=modified_after_generated_at,
            head_revision=head_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
        ),
        component_issues,
    )


def _ordered_chain(cohort_specs: tuple[CohortSourceSpec, ...]) -> list[dict[str, Any]]:
    return [
        {"order": order, "target": spec.target, "primary_report": spec.path}
        for order, spec in enumerate(
            (item for item in cohort_specs if item.include_in_ordered_chain),
            start=1,
        )
    ]


def _cohort_issues(
    vault: Path,
    components: list[dict[str, Any]],
    *,
    cohort_policy: str,
    generated_at: str,
    provenance_mode: str,
    current_source_tree_fingerprint: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    loaded_components = [item for item in components if item["load_status"] == "ok"]
    fingerprints = sorted(
        {
            str(item.get("source_tree_fingerprint", "")).strip()
            for item in loaded_components
            if str(item.get("source_tree_fingerprint", "")).strip()
        }
    )
    missing_fingerprint_components = [
        str(item["name"])
        for item in loaded_components
        if not str(item.get("source_tree_fingerprint", "")).strip()
    ]
    modified_after_components = [
        str(item["name"]) for item in loaded_components if bool(item.get("modified_after_generated_at"))
    ]
    strict_same_fingerprint = (
        len(fingerprints) == 1 and not missing_fingerprint_components and not modified_after_components
    )
    blockers: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    if missing_fingerprint_components:
        blockers.append(
            _issue(
                source="release_evidence_cohort",
                source_path=DEFAULT_OUT,
                code="cohort_missing_source_tree_fingerprint",
                message=(
                    "release evidence components are missing source_tree_fingerprint: "
                    + ", ".join(missing_fingerprint_components)
                ),
                required_evidence=[
                    "Regenerate each release evidence component with a canonical artifact envelope."
                ],
            )
        )

    fingerprint_drift = len(fingerprints) > 1
    if fingerprint_drift:
        fingerprint_issue = _issue(
            source="release_evidence_cohort",
            source_path=DEFAULT_OUT,
            code="cohort_not_strict_same_fingerprint",
            message="release evidence components have more than one source_tree_fingerprint.",
            required_evidence=[
                "Regenerate release evidence in one ordered closeout chain, or keep explicit fingerprint divergence risk visible."
            ],
        )
        if cohort_policy == STRICT_SAME_FINGERPRINT:
            blockers.append(fingerprint_issue)
        else:
            risks.append(_accepted_cohort_risk(fingerprint_issue, generated_at=generated_at))

    if modified_after_components:
        modified_issue = _issue(
            source="release_evidence_cohort",
            source_path=DEFAULT_OUT,
            code="cohort_modified_after_generated_at",
            message=(
                "release evidence component files were modified after their embedded generated_at timestamps: "
                + ", ".join(modified_after_components)
            ),
            required_evidence=[
                "Regenerate affected reports so filesystem mtime is not newer than embedded generated_at, "
                "or keep explicit mtime drift risk visible."
            ],
        )
        if cohort_policy == STRICT_SAME_FINGERPRINT:
            blockers.append(modified_issue)
        else:
            risks.append(_accepted_cohort_risk(modified_issue, generated_at=generated_at))

    divergence_diagnostics = release_source_tree_divergence_diagnostics(
        vault,
        loaded_components,
        current_source_tree_fingerprint=current_source_tree_fingerprint,
    )

    status = "pass"
    if blockers:
        status = "fail"
    elif risks:
        status = "attention"
    return (
        {
            "status": status,
            "policy": cohort_policy,
            "provenance_mode": provenance_mode,
            "strict_same_fingerprint": strict_same_fingerprint,
            "component_count": len(components),
            "loaded_component_count": len(loaded_components),
            "component_fingerprint_count": len(fingerprints),
            "fingerprints": fingerprints,
            "missing_fingerprint_components": missing_fingerprint_components,
            "modified_after_generated_at_components": modified_after_components,
            "divergence_diagnostics": divergence_diagnostics,
        },
        blockers,
        risks,
    )


def _check_expired_risks(components: list[dict[str, Any]]) -> tuple[bool, int]:
    """Check if any accepted risks in closeout components have expired.

    Returns (expired_present, expired_count).
    """
    closeout_components = [item for item in components if item.get("name") == "release_closeout_summary"]
    if not closeout_components:
        return False, 0
    expired_count = 0
    for component in closeout_components:
        risks = component.get("accepted_risks")
        if not isinstance(risks, list):
            continue
        for risk in risks:
            acceptance = risk.get("risk_acceptance")
            if not isinstance(acceptance, dict):
                expired_count += 1
                continue
            expires_at = str(acceptance.get("expires_at", "")).strip()
            if not expires_at:
                expired_count += 1
                continue
            expires_dt = _parse_iso_z(expires_at)
            if expires_dt is None or expires_dt <= dt.datetime.now(tz=dt.UTC):
                expired_count += 1
    return expired_count > 0, expired_count


def _clean_lane_contract(
    *,
    cohort: dict[str, Any],
    components: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    cohort_risks: list[dict[str, Any]],
) -> dict[str, Any]:
    deselected_test_count = sum(
        _coerce_non_negative_int(item.get("deselected_test_count", 0), default=0)
        for item in components
    )
    accepted_risk_family_count = sum(
        _coerce_non_negative_int(item.get("accepted_risk_family_count", 0), default=0)
        for item in components
    )
    clean_lane_blocking_risk_family_count = sum(
        _coerce_non_negative_int(
            item.get(
                "clean_lane_blocking_risk_family_count",
                item.get("accepted_risk_family_count", 0),
            ),
            default=0,
        )
        for item in components
    )
    learning_claim_blocking_risk_family_count = sum(
        _coerce_non_negative_int(item.get("learning_claim_blocking_risk_family_count", 0), default=0)
        for item in components
    )
    advisory_lifecycle_risk_family_count = sum(
        _coerce_non_negative_int(item.get("advisory_lifecycle_risk_family_count", 0), default=0)
        for item in components
    )
    closeout_components = [item for item in components if item.get("name") == "release_closeout_summary"]
    release_closeout_clean = bool(closeout_components) and all(
        item.get("release_readiness_state") == RELEASE_CLOSEOUT_CLEAN_PASS
        and bool(item.get("machine_release_allowed"))
        for item in closeout_components
    )
    strict_cohort_pass = (
        cohort.get("status") == "pass"
        and bool(cohort.get("strict_same_fingerprint"))
        and not issues
        and not cohort_risks
    )
    zero_deselection = deselected_test_count == 0
    zero_accepted_risk_family = clean_lane_blocking_risk_family_count == 0 and not cohort_risks
    expired_risk_present, expired_risk_count = _check_expired_risks(components)
    failed_conditions: list[str] = []
    if not zero_deselection:
        failed_conditions.append("zero_deselection")
    if not zero_accepted_risk_family:
        failed_conditions.append("zero_accepted_risk_family")
    if not strict_cohort_pass:
        failed_conditions.append("strict_cohort_pass")
    if not release_closeout_clean:
        failed_conditions.append("release_closeout_clean")
    if expired_risk_present:
        failed_conditions.append("expired_risk_present")
    return {
        "status": "pass" if not failed_conditions else "fail",
        "zero_deselection": zero_deselection,
        "zero_accepted_risk_family": zero_accepted_risk_family,
        "strict_cohort_pass": strict_cohort_pass,
        "release_closeout_clean": release_closeout_clean,
        "expired_risk_present": expired_risk_present,
        "expired_risk_count": expired_risk_count,
        "deselected_test_count": deselected_test_count,
        "clean_lane_blocking_family_count": clean_lane_blocking_risk_family_count,
        "learning_claim_blocking_family_count": learning_claim_blocking_risk_family_count,
        "advisory_lifecycle_family_count": advisory_lifecycle_risk_family_count,
        "total_accepted_risk_family_count": accepted_risk_family_count,
        "cohort_risk_count": len(cohort_risks),
        "failed_conditions": failed_conditions,
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    profile: str = BASE_PROFILE,
    cohort_policy: str = ALLOWED_DIVERGENCE_WITH_EXPLICIT_RISK,
    provenance_mode: str = EMBEDDED_CURRENTNESS,
    zip_metadata: str | None = None,
) -> dict[str, Any]:
    if cohort_policy not in COHORT_POLICIES:
        raise ValueError(f"unsupported cohort policy: {cohort_policy}")
    if provenance_mode not in PROVENANCE_MODES:
        raise ValueError(f"unsupported provenance mode: {provenance_mode}")
    if provenance_mode == ZIP_INFO and not zip_metadata:
        raise ValueError("--zip-metadata is required when --provenance-mode=zip_info")
    cohort_specs = _cohort_source_specs_for_profile(profile)
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)
    head_revision = resolve_source_revision(vault).revision
    zip_metadata_path = None
    if zip_metadata:
        zip_metadata_path = Path(zip_metadata)
        if not zip_metadata_path.is_absolute():
            zip_metadata_path = vault / zip_metadata_path
        zip_metadata_path = zip_metadata_path.resolve()
    zip_mtimes = load_zip_info_mtimes(zip_metadata_path)

    components: list[dict[str, Any]] = []
    component_issues: list[dict[str, Any]] = []
    for spec in cohort_specs:
        component, issues = _load_component(
            vault,
            spec,
            provenance_mode=provenance_mode,
            zip_mtimes=zip_mtimes,
            head_revision=head_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
        )
        components.append(component)
        component_issues.extend(issues)

    cohort, cohort_blockers, cohort_risks = _cohort_issues(
        vault,
        components,
        cohort_policy=cohort_policy,
        generated_at=generated_at,
        provenance_mode=provenance_mode,
        current_source_tree_fingerprint=current_source_tree_fingerprint,
    )
    blockers = [*component_issues, *cohort_blockers]
    status = "fail" if blockers else cohort["status"]
    input_paths = [spec.path for spec in cohort_specs]
    clean_lane_contract = _clean_lane_contract(
        cohort=cohort,
        components=components,
        issues=blockers,
        cohort_risks=cohort_risks,
    )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind=ARTIFACT_KIND,
            producer=PRODUCER,
            source_command=SOURCE_COMMAND_TEMPLATE.format(
                profile=profile,
                policy=cohort_policy,
                provenance_mode=provenance_mode,
            ),
            resolved_policy_path=resolved_policy_path,
            schema_path=RELEASE_EVIDENCE_COHORT_SCHEMA_PATH,
            source_paths=input_paths,
            file_inputs={spec.name: spec.path for spec in cohort_specs},
            text_inputs={
                "profile": profile,
                "cohort_policy": cohort_policy,
                "provenance_mode": provenance_mode,
                "zip_metadata": str(zip_metadata or ""),
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "profile": profile,
        "status": status,
        "cohort_policy": cohort_policy,
        "provenance_mode": provenance_mode,
        "summary": {
            "component_count": len(components),
            "loaded_component_count": sum(1 for item in components if item["load_status"] == "ok"),
            "issue_count": len(blockers),
            "risk_count": len(cohort_risks),
            "strict_same_fingerprint": bool(cohort["strict_same_fingerprint"]),
            "component_fingerprint_count": int(cohort["component_fingerprint_count"]),
            "modified_after_generated_at_count": len(cohort["modified_after_generated_at_components"]),
            "deselected_test_count": int(clean_lane_contract["deselected_test_count"]),
            "accepted_risk_family_count": int(clean_lane_contract["clean_lane_blocking_family_count"]),
            "expired_risk_count": int(clean_lane_contract.get("expired_risk_count", 0)),
            "evidence_artifact_count": sum(
                _coerce_non_negative_int(item.get("evidence_artifact_count", 0), default=0)
                for item in components
            ),
            "clean_lane_contract_status": str(clean_lane_contract["status"]),
        },
        "ordered_chain": _ordered_chain(cohort_specs),
        "cohort": cohort,
        "clean_lane_contract": clean_lane_contract,
        "components": components,
        "issues": blockers,
        "cohort_risks": cohort_risks,
    }


def write_report(vault: Path, report: dict[str, Any], out: str) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_EVIDENCE_COHORT_SCHEMA_PATH,
            out_path=out,
            default_relative_path=DEFAULT_OUT,
            context="release evidence cohort report",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a release evidence cohort manifest.")
    parser.add_argument("--vault", default=".", help="Vault/repo root")
    parser.add_argument("--policy", default=None, help="Policy path relative to the vault")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output path relative to the vault")
    parser.add_argument("--profile", default=BASE_PROFILE, choices=VALID_PROFILES)
    parser.add_argument(
        "--cohort-policy",
        default=ALLOWED_DIVERGENCE_WITH_EXPLICIT_RISK,
        choices=COHORT_POLICIES,
    )
    parser.add_argument(
        "--provenance-mode",
        default=EMBEDDED_CURRENTNESS,
        choices=PROVENANCE_MODES,
        help="How to evaluate report modification provenance for cohort freshness.",
    )
    parser.add_argument("--zip-metadata", default=None, help="ZIP file to read mtimes from in zip_info mode.")
    parser.add_argument(
        "--fail-on-attention",
        action="store_true",
        help="Exit nonzero when the cohort is attention instead of pass.",
    )
    parser.add_argument(
        "--require-clean-lane",
        action="store_true",
        help="Exit nonzero unless zero deselections, zero accepted risks, and strict cohort pass all hold.",
    )
    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        policy_path=args.policy,
        profile=args.profile,
        cohort_policy=args.cohort_policy,
        provenance_mode=args.provenance_mode,
        zip_metadata=args.zip_metadata,
    )
    output_path = write_report(vault, report, args.out)
    print(display_path(vault, output_path))
    if report["status"] == "fail":
        return 1
    if args.fail_on_attention and report["status"] == "attention":
        return 1
    if args.require_clean_lane and report["clean_lane_contract"]["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
