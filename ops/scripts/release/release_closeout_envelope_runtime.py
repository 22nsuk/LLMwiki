from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import canonical_report_loading_issue
from ops.scripts.artifact_io_runtime import load_optional_json_object_with_diagnostics
from ops.scripts.learning_readiness_vocabulary import (
    LEARNING_REVIEW_REQUIRED_BLOCKER_ID,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import LEARNING_READINESS_SIGNOFF_SCHEMA_PATH
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

from .release_closeout_render_runtime import (
    CloseoutEnvelopeInputs,
    closeout_envelope,
)
from .release_closeout_source_runtime import (
    SourceSpec,
    load_closeout_source,
    source_specs_for_profile,
)
from .release_dependency_reproducibility_runtime import (
    dependency_reproducibility_record,
)
from .release_risk_taxonomy_runtime import load_release_risk_taxonomy

DEFAULT_OUT = "ops/reports/release-closeout-summary.json"
FIXED_POINT_POLICY_PATH = "ops/policies/release-closeout-fixed-point.json"
LEARNING_SIGNOFF_PATH = "ops/reports/learning-readiness-signoff.json"
LEARNING_DELTA_SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"
LEARNING_SIGNOFF_ARTIFACT_KIND = "learning_readiness_signoff"
PRODUCER = "ops.scripts.release_closeout_summary"
SOURCE_COMMAND_TEMPLATE = "python -m ops.scripts.release_closeout_summary --vault . --profile {profile}"


@dataclass(frozen=True)
class CloseoutLoadedSources:
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    profile: str
    source_specs: tuple[SourceSpec, ...]
    generated_at: str
    current_source_tree_fingerprint: str
    risk_taxonomy: dict[str, Any]
    learning_signoff: dict[str, Any]
    learning_claim_context: dict[str, Any]
    dependency_reproducibility: dict[str, Any]
    previous_closeout: dict[str, Any]


@dataclass(frozen=True)
class CloseoutPreparedState:
    collection: Any
    gates: Any
    risk_state: Any
    readiness: Any
    downstream_input_digest_mismatch: dict[str, Any]
    snapshot_phase: str
    envelope: dict[str, Any]


@dataclass(frozen=True)
class CloseoutRenderInputs:
    vault: Path
    policy: dict[str, Any]
    resolved_policy_path: Path
    profile: str
    source_specs: tuple[SourceSpec, ...]
    generated_at: str
    current_source_tree_fingerprint: str
    collection: Any
    gates: Any
    risk_state: Any
    readiness: Any
    learning_signoff: dict[str, Any]
    learning_claim_context: dict[str, Any]
    dependency_reproducibility: dict[str, Any]
    downstream_input_digest_mismatch: dict[str, Any]
    snapshot_phase: str
    envelope: dict[str, Any]


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


def _empty_learning_signoff(load_status: str = "missing", summary: str = "") -> dict[str, Any]:
    signoff_status = "missing" if load_status == "missing" else "invalid"
    if load_status == "template_only":
        signoff_status = "template_only"
    return {
        "path": LEARNING_SIGNOFF_PATH,
        "load_status": load_status,
        "signoff_status": signoff_status,
        "active": False,
        "linked_blocker_id": "",
        "accepted_by": "",
        "accepted_at": "",
        "expires_at": "",
        "risk_owner": "",
        "revalidation_condition": "",
        "rollback_trigger": "",
        "summary": summary or f"{LEARNING_SIGNOFF_PATH} not present",
    }


def _learning_signoff_template_marker(payload: dict[str, Any]) -> str:
    source_revision = str(payload.get("source_revision", "")).strip()
    artifact_status = str(payload.get("artifact_status", "")).strip()
    retention_policy = str(payload.get("retention_policy", "")).strip()
    if source_revision == "template":
        return "source_revision=template"
    if artifact_status == "template_only":
        return "artifact_status=template_only"
    if retention_policy == "template":
        return "retention_policy=template"
    return ""


def _learning_signoff_from_payload(
    vault: Path,
    payload: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    schema = load_schema_with_vault_override(vault, LEARNING_READINESS_SIGNOFF_SCHEMA_PATH)
    schema_errors = validate_with_schema(payload, schema)
    if schema_errors:
        summary = f"{LEARNING_SIGNOFF_PATH} failed schema validation: {'; '.join(schema_errors[:3])}"
        return _empty_learning_signoff("schema_invalid", summary)
    linked_blocker_id = str(payload.get("linked_blocker_id", "")).strip()
    expires_at = str(payload.get("expires_at", "")).strip()
    expires_at_dt = _parse_iso_z(expires_at)
    closeout_dt = _parse_iso_z(generated_at)
    signoff_status = "active"
    active = linked_blocker_id == LEARNING_REVIEW_REQUIRED_BLOCKER_ID
    if expires_at_dt is None or closeout_dt is None:
        signoff_status = "invalid"
        active = False
    elif expires_at_dt <= closeout_dt:
        signoff_status = "expired"
        active = False
    return {
        "path": LEARNING_SIGNOFF_PATH,
        "load_status": "ok",
        "signoff_status": signoff_status,
        "active": active,
        "linked_blocker_id": linked_blocker_id,
        "accepted_by": str(payload.get("accepted_by", "")).strip(),
        "accepted_at": str(payload.get("accepted_at", "")).strip(),
        "expires_at": expires_at,
        "risk_owner": str(payload.get("risk_owner", "")).strip(),
        "revalidation_condition": str(payload.get("revalidation_condition", "")).strip(),
        "rollback_trigger": str(payload.get("rollback_trigger", "")).strip(),
        "summary": (
            f"{LEARNING_SIGNOFF_PATH} {signoff_status} for linked_blocker_id={linked_blocker_id or '<missing>'}"
        ),
    }


def load_learning_signoff(vault: Path, *, generated_at: str) -> dict[str, Any]:
    path = vault / LEARNING_SIGNOFF_PATH
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return _empty_learning_signoff(load_status, str(diagnostics.get("message", "")))
    template_marker = _learning_signoff_template_marker(payload)
    if template_marker:
        return _empty_learning_signoff(
            "template_only",
            f"{LEARNING_SIGNOFF_PATH} is a template-only artifact ({template_marker}) and cannot accept release risk.",
        )
    loading_issue = canonical_report_loading_issue(path, payload)
    if loading_issue is not None:
        return _empty_learning_signoff("unusable", f"{LEARNING_SIGNOFF_PATH} is not usable: {loading_issue}")
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    if artifact_kind != LEARNING_SIGNOFF_ARTIFACT_KIND:
        return _empty_learning_signoff(
            "kind_mismatch",
            f"{LEARNING_SIGNOFF_PATH} declares artifact_kind={artifact_kind or '<missing>'}",
        )
    return _learning_signoff_from_payload(vault, payload, generated_at=generated_at)


def load_learning_claim_context(vault: Path) -> dict[str, Any]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / LEARNING_DELTA_SCOREBOARD_PATH)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return {
            "path": LEARNING_DELTA_SCOREBOARD_PATH,
            "load_status": load_status,
            "claims_learning_improved": False,
            "learning_claim_allowed": False,
            "learning_claim_guard_status": "unknown",
        }
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    guard = payload.get("learning_claim_guard")
    if not isinstance(guard, dict):
        guard = {}
    return {
        "path": LEARNING_DELTA_SCOREBOARD_PATH,
        "load_status": load_status,
        "claims_learning_improved": bool(summary.get("claims_learning_improved")),
        "learning_claim_allowed": bool(summary.get("learning_claim_allowed")),
        "learning_claim_guard_status": str(guard.get("status", payload.get("status", "unknown"))).strip()
        or "unknown",
    }


def previous_closeout(vault: Path) -> dict[str, Any]:
    previous_closeout_payload, load_status, _load_blockers = load_closeout_source(
        vault,
        SourceSpec("previous_closeout", DEFAULT_OUT, "release_closeout_summary"),
    )
    return previous_closeout_payload if load_status in {"ok", "unusable"} else {}


def downstream_input_digest_mismatch(
    previous_report: dict[str, Any],
    *,
    current_input_fingerprints: dict[str, Any],
    source_specs: tuple[SourceSpec, ...],
) -> dict[str, Any]:
    previous_input_fingerprints = previous_report.get("input_fingerprints")
    if not isinstance(previous_input_fingerprints, dict):
        return {
            "status": "no_previous_report",
            "compared_input_count": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "summary": "No previous closeout input digest snapshot was available for mismatch comparison.",
        }

    mismatches: list[dict[str, str]] = []
    for spec in source_specs:
        expected_digest = str(previous_input_fingerprints.get(spec.name, "")).strip() or "missing"
        actual_digest = str(current_input_fingerprints.get(spec.name, "")).strip() or "missing"
        if expected_digest == actual_digest:
            continue
        mismatches.append(
            {
                "input_name": spec.name,
                "source_path": spec.path,
                "expected_digest": expected_digest,
                "actual_digest": actual_digest,
            }
        )

    status = "mismatch" if mismatches else "match"
    return {
        "status": status,
        "compared_input_count": len(source_specs),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "summary": (
            f"downstream_input_digest_mismatch status={status}; "
            f"mismatch_count={len(mismatches)}; compared_input_count={len(source_specs)}"
        ),
    }


def load_closeout_sources(
    vault: Path,
    *,
    policy_path: str | None,
    context: RuntimeContext | None,
    profile: str,
) -> CloseoutLoadedSources:
    source_specs = source_specs_for_profile(profile)
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    return CloseoutLoadedSources(
        vault=vault,
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        profile=profile,
        source_specs=source_specs,
        generated_at=generated_at,
        current_source_tree_fingerprint=release_source_tree_fingerprint(vault),
        risk_taxonomy=load_release_risk_taxonomy(vault),
        learning_signoff=load_learning_signoff(vault, generated_at=generated_at),
        learning_claim_context=load_learning_claim_context(vault),
        dependency_reproducibility=dependency_reproducibility_record(vault),
        previous_closeout=previous_closeout(vault),
    )


def prepare_closeout_state(loaded: CloseoutLoadedSources) -> CloseoutPreparedState:
    from . import release_closeout_gate_runtime as gate_runtime
    from .release_closeout_render_runtime import closeout_snapshot_phase

    collection = gate_runtime.collect_closeout_components(
        loaded.vault,
        loaded.source_specs,
        loaded.risk_taxonomy,
        loaded.learning_claim_context,
    )
    gates = gate_runtime.closeout_gates(
        loaded.vault,
        collection,
        current_source_tree_fingerprint=loaded.current_source_tree_fingerprint,
    )
    risk_state = gate_runtime.closeout_risk_state(
        collection,
        gates,
        previous_closeout=loaded.previous_closeout,
        learning_signoff=loaded.learning_signoff,
        risk_taxonomy=loaded.risk_taxonomy,
        generated_at=loaded.generated_at,
        learning_signoff_path=LEARNING_SIGNOFF_PATH,
    )
    readiness = gate_runtime.closeout_readiness_state(
        collection,
        gates,
        risk_state,
        current_source_tree_fingerprint=loaded.current_source_tree_fingerprint,
    )
    envelope = closeout_envelope(
        CloseoutEnvelopeInputs(
            vault=loaded.vault,
            resolved_policy_path=loaded.resolved_policy_path,
            profile=loaded.profile,
            source_specs=loaded.source_specs,
            generated_at=loaded.generated_at,
            gates=gates,
            learning_signoff=loaded.learning_signoff,
            learning_claim_context=loaded.learning_claim_context,
            dependency_reproducibility=loaded.dependency_reproducibility,
        )
    )
    downstream_mismatch = downstream_input_digest_mismatch(
        loaded.previous_closeout,
        current_input_fingerprints=envelope.get("input_fingerprints", {}),
        source_specs=loaded.source_specs,
    )
    snapshot_phase = closeout_snapshot_phase(
        downstream_mismatch,
        readiness,
    )
    return CloseoutPreparedState(
        collection=collection,
        gates=gates,
        risk_state=risk_state,
        readiness=readiness,
        downstream_input_digest_mismatch=downstream_mismatch,
        snapshot_phase=snapshot_phase,
        envelope=envelope,
    )


def closeout_render_inputs(
    loaded: CloseoutLoadedSources,
    prepared: CloseoutPreparedState,
) -> CloseoutRenderInputs:
    return CloseoutRenderInputs(
        vault=loaded.vault,
        policy=loaded.policy,
        resolved_policy_path=loaded.resolved_policy_path,
        profile=loaded.profile,
        source_specs=loaded.source_specs,
        generated_at=loaded.generated_at,
        current_source_tree_fingerprint=loaded.current_source_tree_fingerprint,
        collection=prepared.collection,
        gates=prepared.gates,
        risk_state=prepared.risk_state,
        readiness=prepared.readiness,
        learning_signoff=loaded.learning_signoff,
        learning_claim_context=loaded.learning_claim_context,
        dependency_reproducibility=loaded.dependency_reproducibility,
        downstream_input_digest_mismatch=prepared.downstream_input_digest_mismatch,
        snapshot_phase=prepared.snapshot_phase,
        envelope=prepared.envelope,
    )
