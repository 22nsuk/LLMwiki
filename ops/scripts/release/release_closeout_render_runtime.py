from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.policy_runtime import report_path
from ops.scripts.schema_constants_runtime import RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH

from .release_authority_vocabulary import release_authority_vocabulary_payload
from .release_closeout_risk_runtime import risk_identity
from .release_status_v2 import decide_sealed_release_status, release_status_v2_payload

LEARNING_SIGNOFF_PATH = "ops/reports/learning-readiness-signoff.json"
LEARNING_DELTA_SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"
PRODUCER = "ops.scripts.release_closeout_summary"
SOURCE_COMMAND_TEMPLATE = "python -m ops.scripts.release_closeout_summary --vault . --profile {profile}"


@dataclass(frozen=True)
class CloseoutEnvelopeInputs:
    vault: Path
    resolved_policy_path: Path
    profile: str
    source_specs: tuple[Any, ...]
    generated_at: str
    gates: Any
    learning_signoff: dict[str, Any]
    learning_claim_context: dict[str, Any]
    dependency_reproducibility: dict[str, Any]


def closeout_file_inputs(
    vault: Path,
    source_specs: tuple[Any, ...],
    dependency_reproducibility: dict[str, Any],
) -> dict[str, str]:
    file_inputs = {spec.name: spec.path for spec in source_specs}
    file_inputs["release_risk_taxonomy"] = "ops/policies/release-risk-taxonomy.json"
    for dependency_file in dependency_reproducibility["dependency_files"]:
        if dependency_file["exists"]:
            file_inputs[f"dependency::{dependency_file['path']}"] = str(
                dependency_file["path"]
            )
    if (vault / LEARNING_DELTA_SCOREBOARD_PATH).exists():
        file_inputs["learning_delta_scoreboard"] = LEARNING_DELTA_SCOREBOARD_PATH
    return file_inputs


def closeout_envelope(inputs: CloseoutEnvelopeInputs) -> dict[str, Any]:
    return build_canonical_report_envelope(
        inputs.vault,
        generated_at=inputs.generated_at,
        artifact_kind="release_closeout_summary",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND_TEMPLATE.format(profile=inputs.profile),
        resolved_policy_path=inputs.resolved_policy_path,
        schema_path=RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/release/release_closeout_summary.py",
            "ops/scripts/release/release_closeout_envelope_runtime.py",
            "ops/scripts/release/release_closeout_gate_runtime.py",
            "ops/scripts/release/release_closeout_source_runtime.py",
            "ops/scripts/release/release_closeout_risk_runtime.py",
            "ops/scripts/release/release_closeout_render_runtime.py",
            "ops/scripts/release/release_dependency_reproducibility_runtime.py",
            "ops/scripts/release/release_freshness_gate_runtime.py",
        ],
        file_inputs=closeout_file_inputs(
            inputs.vault,
            inputs.source_specs,
            inputs.dependency_reproducibility,
        ),
        text_inputs={
            "profile": inputs.profile,
            "learning_signoff_path": LEARNING_SIGNOFF_PATH,
            "learning_signoff_status": str(inputs.learning_signoff["signoff_status"]),
            "learning_claim_context": (
                f"load_status={inputs.learning_claim_context['load_status']}; "
                f"claims_learning_improved={inputs.learning_claim_context['claims_learning_improved']}; "
                f"learning_claim_guard_status={inputs.learning_claim_context['learning_claim_guard_status']}"
            ),
            "test_failure_lane_count": str(len(inputs.gates.test_failure_lanes)),
        },
    )


@dataclass(frozen=True)
class CloseoutStatusDecision:
    status: str
    release_authority_status: str
    semantic_release_status: str
    sealed_release_status: str
    pre_distribution_package_binding_status: str
    source_closeout_distribution_binding_status: str
    release_authority_vocabulary: dict[str, Any]
    status_v2: dict[str, Any]


def closeout_snapshot_phase(
    downstream_input_digest_mismatch: dict[str, Any],
    readiness: Any,
) -> str:
    if downstream_input_digest_mismatch["status"] == "mismatch":
        return "pre_finalization"
    if readiness.clean_release_ready and readiness.machine_release_allowed:
        return "sealed_snapshot"
    return "post_finalization"


def summary_distribution_package_placeholder() -> dict[str, Any]:
    return {
        "status": "not_provided",
        "pre_distribution_package_binding_status": "not_materialized_by_summary",
        "path": "",
        "sha256": "",
    }


def summary_batch_integrity_status(readiness: Any) -> str:
    return "pass" if readiness.checked_in_release_ready else "fail"


def status_semantics() -> dict[str, str]:
    return {
        "top_level_status_meaning": "legacy_checked_in_release_ready_claim",
        "release_authority_status_meaning": "semantic_release_authority_from_closeout",
        "sealed_release_status_meaning": "distribution_seal_state_not_materialized_by_summary",
        "next_migration_candidate": "new_consumers_use_status_v2_axes",
        "summary": (
            "release-closeout-summary status remains the legacy checked-in readiness "
            "alias; status_v2 separates semantic release authority from sealed "
            "distribution/package state."
        ),
    }


def closeout_status_decision(readiness: Any) -> CloseoutStatusDecision:
    status = "pass" if readiness.checked_in_release_ready else "fail"
    release_authority_status = readiness.release_readiness_state
    semantic_release_status = readiness.release_readiness_state
    batch_integrity_status = summary_batch_integrity_status(readiness)
    distribution_package = summary_distribution_package_placeholder()
    pre_distribution_package_binding_status = str(
        distribution_package["pre_distribution_package_binding_status"]
    )
    sealed_release_status = decide_sealed_release_status(
        batch_integrity_status=batch_integrity_status,
        distribution_unsealed_status="unsealed_distribution_not_provided",
        clean_release_ready=readiness.clean_release_ready,
        machine_release_allowed=readiness.machine_release_allowed,
        release_readiness_state=readiness.release_readiness_state,
    )
    source_closeout_distribution_binding_status = sealed_release_status
    vocabulary = release_authority_vocabulary_payload(
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        machine_release_allowed=readiness.machine_release_allowed,
        clean_release_ready=readiness.clean_release_ready,
        batch_integrity_status=batch_integrity_status,
        distribution_package=distribution_package,
    )
    status_v2 = release_status_v2_payload(
        status=status,
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        release_authority_vocabulary=vocabulary,
        sealed_status_field="source_closeout_distribution_binding_status",
        proposed_top_level_status_replacement="source_closeout_distribution_binding_status",
        recommended_consumer_fields=[
            "release_authority_status",
            "source_closeout_distribution_binding_status",
            "release_authority_vocabulary.blocker_reason_ids",
        ],
        extra_status_axes={
            "pre_distribution_package_binding_status": pre_distribution_package_binding_status,
            "source_closeout_distribution_binding_status": source_closeout_distribution_binding_status,
        },
    )
    return CloseoutStatusDecision(
        status=status,
        release_authority_status=release_authority_status,
        semantic_release_status=semantic_release_status,
        sealed_release_status=sealed_release_status,
        pre_distribution_package_binding_status=pre_distribution_package_binding_status,
        source_closeout_distribution_binding_status=source_closeout_distribution_binding_status,
        release_authority_vocabulary=vocabulary,
        status_v2=status_v2,
    )


def closeout_summary_payload(inputs: Any) -> dict[str, Any]:
    gates = inputs.gates
    risk_state = inputs.risk_state
    return {
        "component_count": len(inputs.collection.components),
        "ready_component_count": sum(
            1 for item in inputs.collection.components if item["ready"]
        ),
        "blocker_count": len(risk_state.blockers),
        "source_clean_blocker_count": len(risk_state.source_clean_blockers),
        "accepted_risk_instance_count": len(risk_state.accepted_risks),
        "accepted_risk_family_count": len(
            {risk_identity(risk) for risk in risk_state.accepted_risks}
        ),
        "release_blocking_risk_family_count": risk_state.accepted_risk_scope_counts[
            "release_blocking_family_count"
        ],
        "conditional_operator_review_risk_family_count": risk_state.accepted_risk_scope_counts[
            "conditional_operator_review_family_count"
        ],
        "learning_claim_blocking_risk_family_count": risk_state.accepted_risk_scope_counts[
            "learning_claim_blocking_family_count"
        ],
        "advisory_lifecycle_risk_family_count": risk_state.accepted_risk_scope_counts[
            "advisory_lifecycle_family_count"
        ],
        "advisory_risk_family_count": risk_state.accepted_risk_scope_counts[
            "advisory_only_family_count"
        ],
        "source_tree_coherence_status": gates.source_tree_coherence["status"],
        "artifact_freshness_status": gates.artifact_freshness_gate["status"],
        "release_smoke_boundedness_status": gates.release_smoke_boundedness_gate[
            "status"
        ],
        "live_make_check_status": gates.live_make_check["status"],
        "artifact_freshness_schema_invalid_artifact_count": gates.artifact_freshness_gate[
            "schema_invalid_artifact_count"
        ],
        "test_failure_lane_fail_count": sum(
            1 for lane in gates.test_failure_lanes if lane["status"] == "fail"
        ),
        "test_failure_lane_not_run_count": sum(
            1 for lane in gates.test_failure_lanes if lane["status"] == "not_run"
        ),
    }


def render_closeout_report(inputs: Any) -> dict[str, Any]:
    readiness = inputs.readiness
    risk_state = inputs.risk_state
    status_decision = closeout_status_decision(readiness)
    return {
        **inputs.envelope,
        "vault": report_path(inputs.vault, inputs.vault),
        "policy": {
            "path": report_path(inputs.vault, inputs.resolved_policy_path),
            "version": inputs.policy.get("version"),
        },
        "profile": inputs.profile,
        "checked_in_release_ready": readiness.checked_in_release_ready,
        "live_rerun_release_ready": readiness.live_rerun_release_ready,
        "conditional_release_ready": readiness.conditional_release_ready,
        "clean_release_ready": readiness.clean_release_ready,
        "release_readiness_state": readiness.release_readiness_state,
        "machine_release_allowed": readiness.machine_release_allowed,
        "operator_release_allowed": readiness.operator_release_allowed,
        "requires_accepted_risk_review": readiness.requires_accepted_risk_review,
        "artifact_freshness_gate": inputs.gates.artifact_freshness_gate,
        "live_make_check": inputs.gates.live_make_check,
        "dependency_reproducibility": inputs.dependency_reproducibility,
        "accepted_risk_count_by_scope": risk_state.accepted_risk_scope_counts,
        "clean_lane_blocking_risk_family_count": (
            risk_state.clean_lane_blocking_risk_count
        ),
        "snapshot_phase": inputs.snapshot_phase,
        "status": status_decision.status,
        "status_semantics": status_semantics(),
        "status_v2": status_decision.status_v2,
        "status_v2_preview": status_decision.status_v2,
        "summary": closeout_summary_payload(inputs),
        "release_authority_status": status_decision.release_authority_status,
        "semantic_release_status": status_decision.semantic_release_status,
        "pre_distribution_package_binding_status": (
            status_decision.pre_distribution_package_binding_status
        ),
        "source_closeout_distribution_binding_status": (
            status_decision.source_closeout_distribution_binding_status
        ),
        "sealed_release_status": status_decision.sealed_release_status,
        "release_authority_vocabulary": status_decision.release_authority_vocabulary,
        "learning_readiness_signoff": inputs.learning_signoff,
        "source_tree_coherence": inputs.gates.source_tree_coherence,
        "release_smoke_boundedness_gate": inputs.gates.release_smoke_boundedness_gate,
        "downstream_input_digest_mismatch": inputs.downstream_input_digest_mismatch,
        "test_failure_lanes": inputs.gates.test_failure_lanes,
        "accepted_risk_delta": risk_state.accepted_risk_delta,
        "components": inputs.collection.components,
        "blockers": risk_state.blockers,
        "accepted_risks": risk_state.accepted_risks,
    }
