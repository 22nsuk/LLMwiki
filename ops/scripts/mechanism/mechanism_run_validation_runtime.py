from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.filesystem_runtime import manifest_apply_guard_state
from ops.scripts.path_runtime import normalize_repo_path_text
from ops.scripts.validation_check_types_runtime import (
    PhaseCheckResult,
    validation_check,
)

from .promotion_gate_common_runtime import (
    extract_policy_identity,
    ledger_artifact_targets,
    normalize_report_vault,
    report_target_list,
)

MECHANISM_EVALUATED_EVENT_SEQUENCE = [
    "created",
    "seed_frozen",
    "baseline_captured",
    "mutation_applied",
    "candidate_captured",
    "repo_health_checked",
    "promotion_evaluated",
]
MECHANISM_FINALIZED_EVENT_SEQUENCE = [
    *MECHANISM_EVALUATED_EVENT_SEQUENCE,
    "finalized",
]


@dataclass(frozen=True)
class MechanismArtifactBundle:
    baseline_eval_report: dict
    candidate_eval_report: dict
    baseline_lint_report: dict
    candidate_lint_report: dict
    baseline_mechanism_report: dict
    candidate_mechanism_report: dict
    changed_files_manifest_report: dict
    run_ledger_report: dict


@dataclass(frozen=True)
class DeclaredTargetSet:
    primary_targets: list[str]
    supporting_targets: list[str]
    test_files: list[str]


@dataclass(frozen=True)
class ChangedFilesScopeState:
    changed_paths: list[str]
    declared_scope: list[str]
    out_of_scope_changes: list[str]


@dataclass(frozen=True)
class EventSequenceState:
    observed_event_types: list[str]
    observed_required_event_types: list[str]
    missing_event_types: list[str]
    expected_sequence: list[str]
    expected_terminal_event: str
    order_pass: bool
    terminal_pass: bool


_BUNDLE_FIELDS = (
    "baseline_eval_report",
    "candidate_eval_report",
    "baseline_lint_report",
    "candidate_lint_report",
    "baseline_mechanism_report",
    "candidate_mechanism_report",
    "changed_files_manifest_report",
    "run_ledger_report",
)
_POLICY_AND_VAULT_REPORTS = (
    ("baseline_eval", "baseline_eval_report"),
    ("candidate_eval", "candidate_eval_report"),
    ("baseline_lint", "baseline_lint_report"),
    ("candidate_lint", "candidate_lint_report"),
    ("baseline_mechanism", "baseline_mechanism_report"),
    ("candidate_mechanism", "candidate_mechanism_report"),
)


def mechanism_gate_check(check_id: str, status: str, detail: str) -> dict:
    return {
        "id": check_id,
        "status": status,
        "detail": detail,
    }


def mechanism_phase_check(check_id: str, passed: bool, detail: str) -> PhaseCheckResult:
    return validation_check(check_id, passed, detail)


def normalize_mechanism_artifact_bundle(raw: Mapping[str, dict] | object) -> MechanismArtifactBundle:
    payload: dict[str, dict] = {}
    missing_fields: list[str] = []
    for field in _BUNDLE_FIELDS:
        value = raw.get(field) if isinstance(raw, Mapping) else getattr(raw, field, None)
        if not isinstance(value, dict):
            missing_fields.append(field)
            continue
        payload[field] = value
    if missing_fields:
        raise ValueError(
            "missing mechanism artifact bundle fields: " + ", ".join(sorted(missing_fields))
        )
    return MechanismArtifactBundle(**payload)


def declared_target_matches(path: str, target: str) -> bool:
    normalized_target = target.rstrip("/")
    return (
        not path.startswith("!invalid-repo-path:")
        and not normalized_target.startswith("!invalid-repo-path:")
        and (path == normalized_target or path.startswith(f"{normalized_target}/"))
    )


def path_in_declared_scope(path: str, declared_targets: list[str]) -> bool:
    return any(declared_target_matches(path, target) for target in declared_targets)


def normalize_changed_file_path(path: str) -> str:
    normalized = normalize_repo_path_text(path)
    normalized_path = path if normalized is None else normalized
    return (
        f"!invalid-repo-path:{normalized_path}"
        if normalized_path == ".." or normalized_path.startswith(("../", "/"))
        else normalized_path
    )


def display_report_vault(vault: Path, raw_vault: str | None) -> str:
    normalized = normalize_report_vault(vault, raw_vault)
    if normalized is None:
        return "<missing>"
    vault_root = vault.resolve()
    normalized_path = Path(normalized).resolve()
    if normalized_path == vault_root:
        return "."
    try:
        return normalized_path.relative_to(vault_root).as_posix()
    except ValueError:
        return "<outside-vault>"


def manifest_declared_targets(bundle: MechanismArtifactBundle) -> DeclaredTargetSet:
    declared_targets = bundle.changed_files_manifest_report.get("declared_targets", {})
    return DeclaredTargetSet(
        primary_targets=sorted(
            report_target_list(
                {"primary_targets": declared_targets.get("primary_targets", [])},
                "primary_targets",
            )
        ),
        supporting_targets=sorted(
            report_target_list(
                {"supporting_targets": declared_targets.get("supporting_targets", [])},
                "supporting_targets",
            )
        ),
        test_files=sorted(
            report_target_list(
                {"test_files": declared_targets.get("test_files", [])},
                "test_files",
            )
        ),
    )


def candidate_declared_targets(bundle: MechanismArtifactBundle) -> DeclaredTargetSet:
    return DeclaredTargetSet(
        primary_targets=sorted(
            report_target_list(bundle.candidate_mechanism_report, "primary_targets")
        ),
        supporting_targets=sorted(
            report_target_list(bundle.candidate_mechanism_report, "supporting_targets")
        ),
        test_files=sorted(report_target_list(bundle.candidate_mechanism_report, "test_files")),
    )


def changed_file_paths(bundle: MechanismArtifactBundle) -> list[str]:
    changed_files = bundle.changed_files_manifest_report.get("files", [])
    if not isinstance(changed_files, list):
        return []
    return sorted(
        normalize_changed_file_path(entry["path"])
        for entry in changed_files
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    )


def _behavior_delta_policy(policy: dict) -> dict:
    config = policy.get("behavior_delta", {})
    return config if isinstance(config, dict) else {}


def behavior_delta_requirement_reasons(
    policy: dict,
    *,
    auto_improve_run: bool,
    score_equal: bool,
) -> list[str]:
    behavior_policy = _behavior_delta_policy(policy)
    reasons: list[str] = []
    if behavior_policy.get("required_for_system_mechanism", False):
        reasons.append("policy.required_for_system_mechanism")
    if auto_improve_run and behavior_policy.get("required_for_auto_improve", True):
        reasons.append("auto_improve_run")
    if score_equal and behavior_policy.get("required_for_equal_score_promotion", True):
        reasons.append("equal_score_promotion")
    return reasons


def build_behavior_delta_presence_check(
    policy: dict,
    behavior_delta_report: dict | None,
    *,
    auto_improve_run: bool,
    score_equal: bool,
) -> dict:
    reasons = behavior_delta_requirement_reasons(
        policy,
        auto_improve_run=auto_improve_run,
        score_equal=score_equal,
    )
    if isinstance(behavior_delta_report, dict):
        detail = (
            "behavior-delta artifact present"
            if not reasons
            else "behavior-delta artifact present for required context: " + ", ".join(reasons)
        )
        return mechanism_gate_check("behavior_delta_presence", "PASS", detail)
    if reasons:
        return mechanism_gate_check(
            "behavior_delta_presence",
            "FAIL",
            "missing behavior-delta artifact for required context: " + ", ".join(reasons),
        )
    return mechanism_gate_check(
        "behavior_delta_presence",
        "WARN",
        "behavior_delta.required_for_system_mechanism=false and no auto-improve/equal-score requirement applies",
    )


def build_behavior_delta_consistency_check(
    bundle: MechanismArtifactBundle,
    behavior_delta_report: dict | None,
) -> dict:
    if not isinstance(behavior_delta_report, dict):
        return mechanism_gate_check(
            "behavior_delta_consistency",
            "WARN",
            "behavior-delta artifact not provided; consistency check skipped",
        )
    manifest_paths = changed_file_paths(bundle)
    delta_paths = sorted(
        item["target"]
        for item in behavior_delta_report.get("deltas", [])
        if isinstance(item, dict) and isinstance(item.get("target"), str)
    )
    summary = behavior_delta_report.get("summary", {})
    summary_total = summary.get("changed_file_count") if isinstance(summary, dict) else None
    problems: list[str] = []
    if manifest_paths != delta_paths:
        problems.append(f"manifest_paths={manifest_paths}, behavior_delta_targets={delta_paths}")
    if summary_total != len(manifest_paths):
        problems.append(f"summary.changed_file_count={summary_total}, manifest_count={len(manifest_paths)}")
    return mechanism_gate_check(
        "behavior_delta_consistency",
        "PASS" if not problems else "FAIL",
        "behavior-delta targets align with changed-files manifest"
        if not problems
        else "; ".join(problems),
    )


def build_behavior_delta_review_signal_check(
    behavior_delta_report: dict | None,
) -> dict:
    if not isinstance(behavior_delta_report, dict):
        return mechanism_gate_check(
            "behavior_delta_review_signal",
            "WARN",
            "behavior-delta artifact not provided; semantic/behavior review signal unavailable",
        )
    summary = behavior_delta_report.get("summary", {})
    if not isinstance(summary, dict):
        return mechanism_gate_check(
            "behavior_delta_review_signal",
            "FAIL",
            "behavior-delta summary is missing or invalid",
        )
    regression_count = int(summary.get("regression_count", 0))
    unexpected_count = int(summary.get("unexpected_change_count", 0))
    coverage_gap_count = int(summary.get("coverage_gap_count", 0))
    high_risk_count = int(summary.get("high_risk_delta_count", 0))
    if regression_count:
        return mechanism_gate_check(
            "behavior_delta_review_signal",
            "FAIL",
            f"behavior-delta reports regression_count={regression_count}",
        )
    status = "WARN" if unexpected_count or coverage_gap_count or high_risk_count else "PASS"
    return mechanism_gate_check(
        "behavior_delta_review_signal",
        status,
        (
            f"unexpected={unexpected_count}, coverage_gaps={coverage_gap_count}, "
            f"high_risk_deltas={high_risk_count}, risk_level={summary.get('risk_level', '')}"
        ),
    )


def changed_files_scope_state(
    bundle: MechanismArtifactBundle,
    declared_scope: list[str] | None = None,
) -> ChangedFilesScopeState:
    manifest_targets = manifest_declared_targets(bundle)
    raw_declared_scope = (
        declared_scope
        if declared_scope is not None
        else (
            manifest_targets.primary_targets
            + manifest_targets.supporting_targets
            + manifest_targets.test_files
        )
    )
    normalized_scope = sorted(
        set(normalize_changed_file_path(path) for path in raw_declared_scope)
    )
    changed_paths = changed_file_paths(bundle)
    return ChangedFilesScopeState(
        changed_paths=changed_paths,
        declared_scope=normalized_scope,
        out_of_scope_changes=[
            path for path in changed_paths if not path_in_declared_scope(path, normalized_scope)
        ],
    )


def build_report_consistency_checks(
    vault: Path,
    bundle: MechanismArtifactBundle,
    *,
    run_id: str,
    expected_policy_path: str,
    expected_policy_version: int | None,
) -> list[dict]:
    run_id_consistent = bundle.run_ledger_report.get("run_id") == run_id
    changed_files_run_id_consistent = bundle.changed_files_manifest_report.get("run_id") == run_id
    report_policy_identities = {
        name: extract_policy_identity(getattr(bundle, field_name))
        for name, field_name in _POLICY_AND_VAULT_REPORTS
    }
    policy_consistent = all(
        path == expected_policy_path and version == expected_policy_version
        for path, version in report_policy_identities.values()
    )
    expected_vault = str(vault.resolve())
    report_vaults = {
        name: normalize_report_vault(vault, getattr(bundle, field_name).get("vault"))
        for name, field_name in _POLICY_AND_VAULT_REPORTS
    }
    displayed_report_vaults = {
        name: display_report_vault(vault, getattr(bundle, field_name).get("vault"))
        for name, field_name in _POLICY_AND_VAULT_REPORTS
    }
    vault_consistent = all(raw_vault == expected_vault for raw_vault in report_vaults.values())
    return [
        mechanism_gate_check(
            "run_id_consistency",
            "PASS" if run_id_consistent else "FAIL",
            (
                f"expected run_id={run_id}, "
                f"run_ledger={bundle.run_ledger_report.get('run_id', '')}"
            ),
        ),
        mechanism_gate_check(
            "changed_files_manifest_run_id_consistency",
            "PASS" if changed_files_run_id_consistent else "FAIL",
            (
                f"expected run_id={run_id}, "
                f"changed_files_manifest={bundle.changed_files_manifest_report.get('run_id', '')}"
            ),
        ),
        mechanism_gate_check(
            "report_policy_consistency",
            "PASS" if policy_consistent else "FAIL",
            (
                f"expected={expected_policy_path}@{expected_policy_version}, "
                + ", ".join(
                    f"{name}={path}@{version}"
                    for name, (path, version) in report_policy_identities.items()
                )
            ),
        ),
        mechanism_gate_check(
            "report_vault_consistency",
            "PASS" if vault_consistent else "FAIL",
            (
                "expected=., "
                + ", ".join(f"{name}={value}" for name, value in displayed_report_vaults.items())
            ),
        ),
    ]


def build_run_ledger_target_coverage_check(
    bundle: MechanismArtifactBundle,
    *,
    primary_targets: list[str],
) -> dict:
    run_ledger_targets = ledger_artifact_targets(bundle.run_ledger_report)
    uncovered_targets = sorted(
        target for target in primary_targets if target not in run_ledger_targets
    )
    return mechanism_gate_check(
        "run_ledger_target_coverage",
        "PASS" if not uncovered_targets else "FAIL",
        (
            "all primary targets are referenced in run-ledger event artifacts"
            if not uncovered_targets
            else f"uncovered primary targets: {', '.join(uncovered_targets)}"
        ),
    )


def build_mechanism_primary_target_check(
    bundle: MechanismArtifactBundle,
    *,
    primary_targets: list[str],
) -> dict:
    expected_primary_targets = sorted(primary_targets)
    baseline_mechanism_targets = sorted(
        report_target_list(bundle.baseline_mechanism_report, "primary_targets")
    )
    candidate_mechanism_targets = sorted(
        report_target_list(bundle.candidate_mechanism_report, "primary_targets")
    )
    mechanism_targets_consistent = (
        baseline_mechanism_targets == expected_primary_targets
        and candidate_mechanism_targets == expected_primary_targets
    )
    return mechanism_gate_check(
        "mechanism_report_primary_targets",
        "PASS" if mechanism_targets_consistent else "FAIL",
        (
            f"expected={expected_primary_targets}, "
            f"baseline={baseline_mechanism_targets}, candidate={candidate_mechanism_targets}"
        ),
    )


def build_manifest_declared_targets_check(
    bundle: MechanismArtifactBundle,
    *,
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
) -> dict:
    manifest_targets = manifest_declared_targets(bundle)
    expected_primary_targets = sorted(primary_targets)
    expected_supporting_targets = sorted(supporting_targets)
    expected_test_files = sorted(test_files)
    manifest_declared_targets_consistent = (
        manifest_targets.primary_targets == expected_primary_targets
        and manifest_targets.supporting_targets == expected_supporting_targets
        and manifest_targets.test_files == expected_test_files
    )
    return mechanism_gate_check(
        "changed_files_manifest_declared_targets",
        "PASS" if manifest_declared_targets_consistent else "FAIL",
        (
            f"expected_primary={expected_primary_targets}, manifest_primary={manifest_targets.primary_targets}; "
            f"expected_supporting={expected_supporting_targets}, manifest_supporting={manifest_targets.supporting_targets}; "
            f"expected_tests={expected_test_files}, manifest_tests={manifest_targets.test_files}"
        ),
    )


def build_changed_files_scope_gate_check(bundle: MechanismArtifactBundle) -> dict:
    scope_state = changed_files_scope_state(bundle)
    return mechanism_gate_check(
        "changed_files_manifest_scope",
        "PASS" if not scope_state.out_of_scope_changes else "FAIL",
        (
            "all changed files stay within the declared primary/supporting/test target set"
            if not scope_state.out_of_scope_changes
            else f"out-of-scope changed files: {', '.join(scope_state.out_of_scope_changes)}"
        ),
    )


def build_changed_files_allowed_apply_roots_check(
    bundle: MechanismArtifactBundle,
    *,
    allowed_apply_roots: list[str],
) -> dict:
    try:
        guard_state = manifest_apply_guard_state(
            bundle.changed_files_manifest_report,
            allowed_apply_roots,
        )
    except ValueError as exc:
        return mechanism_gate_check(
            "changed_files_manifest_allowed_apply_roots",
            "FAIL",
            str(exc),
        )

    problems: list[str] = []
    if guard_state.invalid_paths:
        problems.append("invalid paths: " + ", ".join(guard_state.invalid_paths))
    if guard_state.disallowed_paths:
        problems.append(
            "paths outside allowed_apply_roots: "
            + ", ".join(guard_state.disallowed_paths)
        )
    if not problems:
        return mechanism_gate_check(
            "changed_files_manifest_allowed_apply_roots",
            "PASS",
            "all changed files stay within auto_improve_policy.allowed_apply_roots: "
            + ", ".join(guard_state.allowed_apply_roots),
        )
    return mechanism_gate_check(
        "changed_files_manifest_allowed_apply_roots",
        "FAIL",
        "; ".join(problems)
        + " | allowed_apply_roots="
        + ", ".join(guard_state.allowed_apply_roots),
    )


def build_changed_files_nonempty_check(bundle: MechanismArtifactBundle) -> dict:
    changed_paths = changed_file_paths(bundle)
    return mechanism_gate_check(
        "changed_files_manifest_nonempty",
        "PASS" if changed_paths else "WARN",
        (
            f"captured changed files: {', '.join(changed_paths)}"
            if changed_paths
            else "mutation workspace produced no tracked file changes"
        ),
    )


def build_changed_files_primary_target_touched_check(
    bundle: MechanismArtifactBundle,
    *,
    primary_targets: list[str],
) -> dict:
    changed_paths = changed_file_paths(bundle)
    touched_targets = sorted(
        target
        for target in primary_targets
        if any(declared_target_matches(path, target) for path in changed_paths)
    )
    return mechanism_gate_check(
        "changed_files_manifest_primary_targets_touched",
        "PASS" if touched_targets else "FAIL",
        (
            "changed files touch primary targets: " + ", ".join(touched_targets)
            if touched_targets
            else (
                "changed files do not touch any primary target; "
                f"expected_primary_targets={primary_targets}; changed_files={changed_paths}; "
                "test/report/generated-only changes require a scoped mechanism change"
            )
        ),
    )


def event_sequence_state(run_ledger_report: dict, *, phase: str) -> EventSequenceState:
    expected_sequence = (
        MECHANISM_FINALIZED_EVENT_SEQUENCE
        if phase == "mechanism_finalized"
        else MECHANISM_EVALUATED_EVENT_SEQUENCE
    )
    observed_event_types = [
        event_type
        for event in run_ledger_report.get("events", [])
        if isinstance(event, dict)
        if isinstance(event_type := event.get("type"), str)
    ]
    missing_event_types = [
        event_type for event_type in expected_sequence if event_type not in observed_event_types
    ]
    observed_required_event_types = [
        event_type for event_type in observed_event_types if event_type in expected_sequence
    ]
    expected_terminal_event = "finalized" if phase == "mechanism_finalized" else "promotion_evaluated"
    return EventSequenceState(
        observed_event_types=observed_event_types,
        observed_required_event_types=observed_required_event_types,
        missing_event_types=missing_event_types,
        expected_sequence=expected_sequence,
        expected_terminal_event=expected_terminal_event,
        order_pass=observed_required_event_types == expected_sequence,
        terminal_pass=(
            bool(observed_required_event_types)
            and observed_required_event_types[-1] == expected_terminal_event
            and not (phase != "mechanism_finalized" and "finalized" in observed_event_types)
        ),
    )


def build_event_sequence_phase_checks(
    bundle: MechanismArtifactBundle,
    *,
    phase: str,
) -> list[PhaseCheckResult]:
    state = event_sequence_state(bundle.run_ledger_report, phase=phase)
    return [
        mechanism_phase_check(
            "mechanism_run_required_events_present",
            not state.missing_event_types,
            (
                f"run-ledger includes required event sequence through {state.expected_terminal_event}"
                if not state.missing_event_types
                else f"missing event types: {', '.join(state.missing_event_types)}"
            ),
        ),
        mechanism_phase_check(
            "mechanism_run_event_order",
            state.order_pass,
            (
                f"run-ledger event order matches canonical sequence through {state.expected_terminal_event}"
                if state.order_pass
                else f"observed required event order={state.observed_required_event_types}"
            ),
        ),
        mechanism_phase_check(
            "mechanism_run_terminal_event",
            state.terminal_pass,
            (
                f"last required run-ledger event is {state.expected_terminal_event}"
                if state.terminal_pass
                else (
                    f"expected terminal event {state.expected_terminal_event}, "
                    f"observed {state.observed_required_event_types[-1] if state.observed_required_event_types else 'none'}; "
                    f"all events: {', '.join(state.observed_event_types) or 'none'}"
                )
            ),
        ),
    ]


def build_test_surface_phase_check(
    bundle: MechanismArtifactBundle,
    *,
    ready: bool,
) -> PhaseCheckResult:
    baseline_test_files = bundle.baseline_mechanism_report.get("test_files", [])
    candidate_test_files = bundle.candidate_mechanism_report.get("test_files", [])
    test_surface_present = (
        isinstance(baseline_test_files, list)
        and isinstance(candidate_test_files, list)
        and len(baseline_test_files) >= 1
        and len(candidate_test_files) >= 1
    )
    return mechanism_phase_check(
        "mechanism_run_test_surface_present",
        True if not ready else test_surface_present,
        (
            "skipped until baseline/candidate mechanism artifacts are complete"
            if not ready
            else (
                "baseline and candidate mechanism assessments both include at least one focused test file"
                if test_surface_present
                else (
                    "completed mechanism runs should capture at least one focused test file in both "
                    "baseline and candidate mechanism assessments"
                )
            )
        ),
    )


def build_manifest_alignment_phase_check(
    bundle: MechanismArtifactBundle,
    *,
    ready: bool,
) -> PhaseCheckResult:
    manifest_targets = manifest_declared_targets(bundle)
    candidate_targets = candidate_declared_targets(bundle)
    manifest_declared_targets_align = (
        manifest_targets.primary_targets == candidate_targets.primary_targets
        and manifest_targets.supporting_targets == candidate_targets.supporting_targets
        and manifest_targets.test_files == candidate_targets.test_files
    )
    return mechanism_phase_check(
        "mechanism_run_changed_files_declared_targets_align",
        True if not ready else manifest_declared_targets_align,
        (
            "skipped until mechanism inputs are complete"
            if not ready
            else (
                "changed-files manifest declared targets align with the candidate mechanism assessment"
                if manifest_declared_targets_align
                else (
                    f"manifest primary={manifest_targets.primary_targets}, candidate primary={candidate_targets.primary_targets}; "
                    f"manifest supporting={manifest_targets.supporting_targets}, candidate supporting={candidate_targets.supporting_targets}; "
                    f"manifest tests={manifest_targets.test_files}, candidate tests={candidate_targets.test_files}"
                )
            )
        ),
    )


def build_changed_files_scope_phase_check(
    bundle: MechanismArtifactBundle,
    *,
    ready: bool,
) -> PhaseCheckResult:
    scope_state = changed_files_scope_state(bundle)
    return mechanism_phase_check(
        "mechanism_run_changed_files_in_scope",
        True if not ready else not scope_state.out_of_scope_changes,
        (
            "skipped until mechanism inputs are complete"
            if not ready
            else (
                "changed-files manifest stays within the declared primary/supporting/test target set"
                if not scope_state.out_of_scope_changes
                else f"out-of-scope changed files: {', '.join(scope_state.out_of_scope_changes)}"
            )
        ),
    )
