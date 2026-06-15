from __future__ import annotations

from typing import Any

from ops.scripts.release.auto_promotion_manifest_sections import RequirementSpec


def goal_runtime_verification_requirements(
    checks: dict[str, bool],
    inputs: dict[str, dict[str, Any]],
    *,
    selected_goal_run_id: str,
    goal_run_status: dict[str, Any],
    goal_runtime_certificate: dict[str, Any],
    fingerprint: str,
) -> list[RequirementSpec]:
    status_input = inputs["goal_run_status"]
    certificate_input = inputs["goal_runtime_certificate"]
    return [
        *_goal_run_status_requirements(
            checks,
            status_input=status_input,
            selected_goal_run_id=selected_goal_run_id,
            goal_run_status=goal_run_status,
            fingerprint=fingerprint,
        ),
        *_goal_runtime_certificate_requirements(
            checks,
            certificate_input=certificate_input,
            selected_goal_run_id=selected_goal_run_id,
            goal_runtime_certificate=goal_runtime_certificate,
            fingerprint=fingerprint,
        ),
    ]


def _goal_run_status_requirements(
    checks: dict[str, bool],
    *,
    status_input: dict[str, Any],
    selected_goal_run_id: str,
    goal_run_status: dict[str, Any],
    fingerprint: str,
) -> list[RequirementSpec]:
    return [
        RequirementSpec(
            checks["goal_run_status_load_ok"],
            "goal_run_status_not_loadable",
            "goal_run_status",
            "$.load_status",
            status_input["load_status"],
            "ok",
            "Goal-run status evidence is missing or invalid.",
            "Publish goal-run status for the selected run before unattended promotion.",
        ),
        RequirementSpec(
            checks["goal_run_status_artifact_kind_ok"],
            "goal_run_status_artifact_kind_invalid",
            "goal_run_status",
            "$.artifact_kind",
            status_input["artifact_kind"],
            "goal_run_status",
            "Goal-run status evidence has an unexpected artifact kind.",
            "Regenerate goal-run status evidence for the selected run.",
        ),
        RequirementSpec(
            checks["goal_run_status_current"],
            "goal_run_status_stale",
            "goal_run_status",
            "$.source_revision|$.source_tree_fingerprint",
            (
                f"source_revision={status_input['source_revision']};"
                f"source_tree_fingerprint={status_input['source_tree_fingerprint']}"
            ),
            f"source_revision=current;source_tree_fingerprint={fingerprint}",
            "Goal-run status evidence does not describe the current source tree.",
            "Refresh goal-run status evidence for the current source tree.",
        ),
        RequirementSpec(
            checks["goal_run_status_run_id_match"],
            "goal_run_status_run_id_mismatch",
            "goal_run_status",
            "$.run.run_id",
            goal_run_status["run_id"],
            selected_goal_run_id,
            "Goal-run status does not match the selected release goal run.",
            "Publish status evidence for the GOAL_RUN_ID bound by preflight and preseal.",
        ),
        RequirementSpec(
            checks["goal_run_status_completed"],
            "goal_run_status_not_completed",
            "goal_run_status",
            "$.run.status",
            goal_run_status["run_status"],
            "completed",
            "The selected goal run is not completed.",
            "Complete the selected goal run before claiming unattended promotion readiness.",
        ),
        RequirementSpec(
            checks["goal_run_status_report_accepted"],
            "goal_run_status_report_not_accepted",
            "goal_run_status",
            "$.status",
            goal_run_status["status"],
            "pass or attention",
            "Goal-run status report is not an accepted completed-run diagnostic.",
            "Regenerate goal-run status for the completed selected run.",
        ),
    ]


def _goal_runtime_certificate_requirements(
    checks: dict[str, bool],
    *,
    certificate_input: dict[str, Any],
    selected_goal_run_id: str,
    goal_runtime_certificate: dict[str, Any],
    fingerprint: str,
) -> list[RequirementSpec]:
    return [
        RequirementSpec(
            checks["goal_runtime_certificate_load_ok"],
            "goal_runtime_certificate_not_loadable",
            "goal_runtime_certificate",
            "$.load_status",
            certificate_input["load_status"],
            "ok",
            "Goal-runtime certificate evidence is missing or invalid.",
            "Run GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate for the selected completed run.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_artifact_kind_ok"],
            "goal_runtime_certificate_artifact_kind_invalid",
            "goal_runtime_certificate",
            "$.artifact_kind",
            certificate_input["artifact_kind"],
            "goal_runtime_certificate",
            "Goal-runtime certificate evidence has an unexpected artifact kind.",
            "Regenerate selected completed run certificate evidence with GOAL_RUN_ID=<completed-run-id>.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_current"],
            "goal_runtime_certificate_stale",
            "goal_runtime_certificate",
            "$.source_revision|$.source_tree_fingerprint",
            (
                f"source_revision={certificate_input['source_revision']};"
                f"source_tree_fingerprint={certificate_input['source_tree_fingerprint']}"
            ),
            f"source_revision=current;source_tree_fingerprint={fingerprint}",
            "Goal-runtime certificate evidence does not describe the current source tree.",
            "Refresh the selected completed run certificate with GOAL_RUN_ID=<completed-run-id>.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_run_id_match"],
            "goal_runtime_certificate_run_id_mismatch",
            "goal_runtime_certificate",
            "$.run.run_id",
            goal_runtime_certificate["run_id"],
            selected_goal_run_id,
            "Goal-runtime certificate does not match the selected release goal run.",
            "Regenerate with GOAL_RUN_ID bound to the completed run selected by preflight and preseal.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_completed"],
            "goal_runtime_certificate_run_not_completed",
            "goal_runtime_certificate",
            "$.run.run_status",
            goal_runtime_certificate["run_status"],
            "completed",
            "Goal-runtime certificate does not describe a completed run.",
            "Regenerate the certificate after the selected goal run completes.",
        ),
        RequirementSpec(
            checks["goal_runtime_certificate_verified"],
            "goal_runtime_certificate_not_verified",
            "goal_runtime_certificate",
            "$.status|$.certificate.verification_status|$.certificate.eligible",
            (
                f"status={goal_runtime_certificate['status']};"
                f"verification_status={goal_runtime_certificate['verification_status']};"
                f"eligible={goal_runtime_certificate['eligible']}"
            ),
            "status=pass; verification_status in eligible,already_verified; eligible=true",
            "The selected goal run does not have verified certificate evidence.",
            "Run GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate after certifiable completed run evidence exists.",
        ),
    ]
