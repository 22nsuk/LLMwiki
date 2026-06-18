from __future__ import annotations

from pathlib import Path

from ops.scripts.core.validation_check_types_runtime import (
    ValidationCheckResult,
    validation_check,
)

from .mechanism_run_validation_runtime import (
    build_changed_files_scope_phase_check,
    build_event_sequence_phase_checks,
    build_manifest_alignment_phase_check,
    build_test_surface_phase_check,
)
from .planning_gate_phase_state_runtime import (
    CompletedMechanismInputsState,
    MechanismPhaseState,
    load_completed_mechanism_inputs,
)


def slugify_heading(text: str) -> str:
    slug = text.strip().lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else "" for ch in slug)
    slug = "-".join(part for part in slug.split())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def system_log_contains_entry_ref(vault: Path, entry_ref: str) -> bool:
    if "#" not in entry_ref:
        return False
    raw_path, anchor = entry_ref.split("#", 1)
    log_path = (vault / raw_path).resolve()
    if not log_path.exists():
        return False
    text = log_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("#") and slugify_heading(line.lstrip("# ").strip()) == anchor:
            return True
    return False


def completed_mechanism_phase_checks(
    phase_state: MechanismPhaseState,
    completed_inputs: CompletedMechanismInputsState,
) -> list[ValidationCheckResult]:
    phase_checks = list(
        build_event_sequence_phase_checks(
            completed_inputs.bundle_for_phase_checks,
            phase=phase_state.phase,
        )
    )
    phase_checks.append(
        validation_check(
            "mechanism_run_inputs_local",
            not completed_inputs.local_input_failures,
            (
                "all baseline/candidate report inputs stay under the same run directory"
                if not completed_inputs.local_input_failures
                else "; ".join(completed_inputs.local_input_failures)
            ),
        )
    )
    phase_checks.append(
        validation_check(
            "mechanism_run_inputs_complete",
            not completed_inputs.input_validation_failures,
            (
                "baseline/candidate eval, lint, mechanism, changed-files manifest, and policy-conditioned behavior-delta artifacts are schema-valid"
                if not completed_inputs.input_validation_failures
                else "; ".join(completed_inputs.input_validation_failures)
            ),
        )
    )
    phase_checks.append(
        build_test_surface_phase_check(
            completed_inputs.bundle_for_phase_checks,
            ready=completed_inputs.ready,
        )
    )
    phase_checks.append(
        build_manifest_alignment_phase_check(
            completed_inputs.bundle_for_phase_checks,
            ready=completed_inputs.ready,
        )
    )
    phase_checks.append(
        build_changed_files_scope_phase_check(
            completed_inputs.bundle_for_phase_checks,
            ready=completed_inputs.ready,
        )
    )
    return phase_checks


def finalized_only_phase_checks(
    vault: Path,
    phase_state: MechanismPhaseState,
) -> list[ValidationCheckResult]:
    phase_checks: list[ValidationCheckResult] = []
    log = phase_state.promotion_report.get("log", {})
    log_recorded = False
    if isinstance(log, dict):
        if log.get("required") is True:
            entry_ref = log.get("entry_ref")
            log_recorded = (
                log.get("status") == "recorded"
                and isinstance(entry_ref, str)
                and bool(entry_ref)
                and system_log_contains_entry_ref(vault, entry_ref)
            )
        elif log.get("required") is False:
            log_recorded = log.get("status") == "not_required" and not log.get("entry_ref")
    phase_checks.append(
        validation_check(
            "mechanism_run_log_recorded",
            log_recorded,
            (
                "promotion log state is finalized and consistent with current log policy"
                if log_recorded
                else "complete mechanism run requires either a recorded log entry with a resolvable entry_ref or log.status=not_required when log.required=false"
            ),
        )
    )

    finalized_event_present = any(
        isinstance(event, dict) and event.get("type") == "finalized"
        for event in phase_state.run_ledger.get("events", [])
    )
    phase_checks.append(
        validation_check(
            "mechanism_run_finalized_event_present",
            finalized_event_present,
            (
                "run-ledger includes a finalized event"
                if finalized_event_present
                else "complete mechanism run should append a finalized event to run-ledger.json"
            ),
        )
    )

    planning_validation = phase_state.planning_validation
    planning_validation_current = (
        isinstance(planning_validation, dict)
        and planning_validation.get("status") == "PASS"
        and planning_validation.get("next_action")
        == "Use this finalized run as future history input for mechanism_review and mutation_proposal."
    )
    phase_checks.append(
        validation_check(
            "mechanism_run_planning_validation_current",
            planning_validation_current,
            (
                "planning-validation.json reflects the finalized mechanism run state"
                if planning_validation_current
                else "complete mechanism run should refresh planning-validation.json to the finalized PASS snapshot"
            ),
        )
    )
    return phase_checks


def mechanism_phase_checks(
    vault: Path,
    phase_state: MechanismPhaseState | None,
) -> list[ValidationCheckResult]:
    if phase_state is None or phase_state.phase not in {"mechanism_evaluated", "mechanism_finalized"}:
        return []

    completed_inputs = load_completed_mechanism_inputs(vault, phase_state)
    phase_checks = completed_mechanism_phase_checks(phase_state, completed_inputs)
    if phase_state.phase == "mechanism_finalized":
        phase_checks.extend(finalized_only_phase_checks(vault, phase_state))

    return phase_checks
