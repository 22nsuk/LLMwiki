from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ops.scripts.policy_runtime import report_path
from .release_status_v2 import release_status_v2_view_with_readiness_fallback
from .release_workflow_order_guard import build_report as build_release_workflow_order_guard_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.workflow_dependency_planner import build_report as build_workflow_dependency_report


REFERENCE_MANIFEST = "external-reports/report-reference-manifest.json"
REPORT_EXTENSIONS = {".md", ".json"}
REFERENCE_MANIFEST_EXTENSIONS = {".md", ".pdf", ".docx"}
NARRATIVE_REPORT_EXTENSIONS = {".md"}
RELEASE_VERIFIED_ACTION_IDS = {
    "source_package_distribution_binding",
    "release_evidence_bundle_and_attestation",
    "full_suite_evidence_currentness",
    "promotion_truth_ladder",
}

ACTION_CATALOG: list[dict[str, Any]] = [
    {
        "action_id": "script_output_surfaces_currentness",
        "priority": "P0",
        "theme": "writer output surface currentness",
        "patterns": [r"script-output-surfaces", r"writer/output surface", r"writer output"],
        "evidence_paths": ["ops/script-output-surfaces.json"],
        "recommended_target": "script-output-surfaces",
    },
    {
        "action_id": "release_writer_dependency_single_source",
        "priority": "P0",
        "theme": "release writer ordering single source",
        "patterns": [r"workflow_dependency_planner", r"fixed-point", r"writer dependency", r"single source"],
        "evidence_paths": [
            "tmp/workflow-dependency-planner.json",
            "tmp/release-workflow-order-guard.json",
        ],
        "recommended_target": "release-workflow-order-guard",
    },
    {
        "action_id": "function_budget_proposal_adapter",
        "priority": "P1",
        "theme": "wiki_lint function-budget triage",
        "patterns": [r"function-budget", r"wiki_lint review", r"review candidate"],
        "evidence_paths": ["ops/reports/function-budget-refactor-proposals.json"],
        "recommended_target": "function-budget-refactor-proposals",
    },
    {
        "action_id": "windows_path_and_archive_alias_parity",
        "priority": "P1",
        "theme": "path portability and archive alias normalization",
        "patterns": [r"Windows", r"path alias", r"path portability", r"Info-ZIP", r"C locale", r"escaped path"],
        "evidence_paths": [
            "tests/test_writer_output_paths.py",
            "tests/test_planning_gate_validate_runtime.py",
            "tests/test_release_smoke.py",
        ],
        "recommended_target": "test-public",
    },
    {
        "action_id": "outcome_provenance_gate_policy",
        "priority": "P2",
        "theme": "outcome/provenance policy escalation",
        "patterns": [r"outcome", r"provenance", r"same-eval", r"rollback rehearsal", r"promotion gate"],
        "evidence_paths": ["ops/reports/outcome-provenance-gate-policy.json"],
        "recommended_target": "outcome-provenance-gate-policy",
    },
    {
        "action_id": "external_report_lifecycle",
        "priority": "P1",
        "theme": "active external report lifecycle",
        "patterns": [r"external report lifecycle", r"active external", r"report-reference-manifest", r"active report set"],
        "evidence_paths": [
            "external-reports/report-reference-manifest.json",
            "ops/reports/external-report-action-matrix.json",
        ],
        "recommended_target": "external-report-action-matrix",
    },
    {
        "action_id": "source_package_distribution_binding",
        "priority": "P0",
        "theme": "source package and distribution ZIP binding",
        "patterns": [r"source package", r"source ZIP", r"distribution ZIP", r"archive profile", r"package mode"],
        "evidence_paths": [
            "ops/reports/source-package-clean-extract.json",
            "ops/reports/release-smoke-report.json",
            "external-reports/report-reference-manifest.json",
        ],
        "recommended_target": "release-source-package-check",
    },
    {
        "action_id": "release_evidence_bundle_and_attestation",
        "priority": "P1",
        "theme": "release evidence bundle and attestation",
        "patterns": [
            r"evidence bundle",
            r"attestation",
            r"post-seal",
            r"audit pack",
            r"release[- ]evidence",
            r"release-closeout-batch-manifest",
            r"batch-manifest",
            r"finality",
            r"closeout self-check",
        ],
        "evidence_paths": [
            "ops/reports/release-closeout-finality-attestation.json",
            "ops/reports/release-closeout-batch-manifest.json",
        ],
        "recommended_target": "release-evidence-closeout-sealed-dry-run",
    },
    {
        "action_id": "full_suite_evidence_currentness",
        "priority": "P1",
        "theme": "full-suite evidence currentness",
        "patterns": [r"full-suite", r"full suite", r"test-execution-summary-full", r"collect-only", r"nodeid"],
        "evidence_paths": ["ops/reports/test-execution-summary-full.json"],
        "recommended_target": "test-execution-summary-full-refresh",
    },
    {
        "action_id": "promotion_truth_ladder",
        "priority": "P0",
        "theme": "live gate and promotion truth ladder",
        "patterns": [r"truth ladder", r"live gate", r"promotion_blockers", r"can_promote_result", r"machine_release"],
        "evidence_paths": [
            "ops/reports/auto-improve-readiness.json",
            "ops/reports/release-closeout-summary.json",
            "ops/reports/release-evidence-dashboard.json",
        ],
        "recommended_target": "auto-improve-readiness-report",
    },
    {
        "action_id": "goal_contract_schema",
        "priority": "P0",
        "theme": "goal contract schema for long-running auto-improve",
        "patterns": [
            r"goal contract",
            r"codex-goal-contract",
            r"GoalSpec",
            r"required_evidence",
            r"stop_conditions",
        ],
        "evidence_paths": [
            "ops/schemas/codex-goal-contract.schema.json",
            "tests/test_codex_goal_contract.py",
        ],
        "recommended_target": "codex-goal-contract",
    },
    {
        "action_id": "codex_goal_adapter",
        "priority": "P0",
        "theme": "local set_goal adapter and backend detection",
        "patterns": [
            r"set_goal",
            r"get_goal",
            r"update_goal",
            r"GoalBackend",
            r"feature detection",
            r"thread/goal",
            r"app-server",
        ],
        "evidence_paths": [
            "ops/scripts/core/codex_goal_client.py",
            "tests/test_codex_goal_client.py",
        ],
        "recommended_target": "codex-goal-client",
    },
    {
        "action_id": "goal_run_status_audit_resume",
        "priority": "P0",
        "theme": "goal run status, audit log, checkpoint, and resume contract",
        "patterns": [
            r"goal-run-status",
            r"audit-log",
            r"checkpoint",
            r"resume",
            r"status\.md",
            r"resume_from_checkpoint",
            r"--goal-contract",
            r"--resume-from-checkpoint",
        ],
        "evidence_paths": [
            "ops/schemas/goal-run-status.schema.json",
            "ops/scripts/mechanism/auto_improve_goal_runtime.py",
            "ops/scripts/mechanism/auto_improve_loop.py",
            "ops/scripts/mechanism/goal_run_status.py",
            "ops/reports/goal-run-status.json",
            "tests/test_goal_auto_improve_runtime.py",
            "tests/test_goal_run_status.py",
        ],
        "recommended_target": "auto-improve-goal-run",
    },
    {
        "action_id": "command_heartbeat_observability",
        "priority": "P1",
        "theme": "long command heartbeat and quiet-run observability",
        "patterns": [
            r"heartbeat",
            r"last_stdout_at",
            r"last_stderr_at",
            r"last_artifact_touch_at",
            r"quiet_seconds",
            r"budget_limited",
        ],
        "evidence_paths": [
            "ops/scripts/core/command_runtime.py",
            "ops/schemas/executor-report.schema.json",
            "tests/test_command_runtime_heartbeat.py",
        ],
        "recommended_target": "test-subprocess",
    },
    {
        "action_id": "selected_contract_currentness_gate",
        "priority": "P0",
        "theme": "selected contract currentness gate distinct from artifact freshness",
        "patterns": [
            r"selected contract",
            r"selected_contract_currentness",
            r"test_execution_summary_contract_drift",
            r"artifact freshness pass",
            r"operational currentness drift",
        ],
        "evidence_paths": [
            "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py",
            "tests/test_auto_improve_readiness_release_authority_runtime.py",
        ],
        "recommended_target": "auto-improve-readiness-report",
    },
    {
        "action_id": "sealed_preflight_canonicalization",
        "priority": "P0",
        "theme": "sealed authority preflight clean-required canonical evidence",
        "patterns": [
            r"sealed preflight",
            r"release authority",
            r"expected blocked",
            r"clean-required",
            r"sealed authority clean",
            r"binding_pass_authority_blocked",
        ],
        "evidence_paths": [
            "ops/scripts/release/release_closeout_sealed_rehearsal_check.py",
            "ops/schemas/release-closeout-sealed-rehearsal-check.schema.json",
            "tests/test_release_closeout_sealed_rehearsal_check.py",
        ],
        "recommended_target": "release-authority-sealed-preflight",
    },
    {
        "action_id": "negative_learning_ledger",
        "priority": "P2",
        "theme": "standalone negative learning ledger",
        "patterns": [
            r"negative learning",
            r"negative lessons",
            r"self-improvement-negative-lessons",
            r"same failure",
        ],
        "evidence_paths": [
            "ops/schemas/self-improvement-negative-lessons.schema.json",
            "ops/reports/self-improvement-negative-lessons.json",
            "tests/test_self_improvement_negative_lessons.py",
        ],
        "recommended_target": "self-improvement-negative-lessons",
    },
    {
        "action_id": "remediation_backlog",
        "priority": "P1",
        "theme": "remediation backlog for repeated blockers",
        "patterns": [
            r"remediation backlog",
            r"remediation-backlog",
            r"repeated blocker",
            r"blocked.*backlog",
        ],
        "evidence_paths": [
            "ops/schemas/remediation-backlog.schema.json",
            "ops/reports/remediation-backlog.json",
            "tests/test_remediation_backlog.py",
        ],
        "recommended_target": "remediation-backlog",
    },
    {
        "action_id": "git_worktree_goal_guard",
        "priority": "P1",
        "theme": "Git worktree and ZIP mode guard for long goal runs",
        "patterns": [
            r"Git worktree",
            r"ZIP extraction mode",
            r"git rev-parse",
            r"worktree path",
            r"private repo",
        ],
        "evidence_paths": [
            "ops/scripts/mechanism/goal_worktree_guard.py",
            "tests/test_goal_worktree_guard.py",
        ],
        "recommended_target": "auto-improve-goal-preflight",
    },
]

ARCHIVE_STATUS_RE = re.compile(
    r"(?im)^\s*(?:archive_status|lifecycle_status|report_status)\s*[:=]\s*"
    r"`?(closed|superseded|archived)`?\s*$"
)
SUPERSEDED_BY_RE = re.compile(r"(?im)^\s*(?:superseded_by|replaced_by)\s*[:=]\s*`?([^`\n]+)`?")
COVERAGE_MARKER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("actual_file_crosscheck", r"actual[-_ ]file|실제\s*파일|파일\s*대조"),
    ("integrated_review", r"integrated|consolidated|통합\s*리뷰|통합\s*검토|종합\s*검토"),
    ("final_conclusion", r"final\s+conclusion|최종\s*결론|최종\s*권고|최종\s*판정"),
    ("live_reverification", r"live\s+truth|재검증|직접\s*재실행|실제\s*재검증"),
)


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def active_report_paths(vault: Path) -> list[Path]:
    root = vault / "external-reports"
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in REPORT_EXTENSIONS:
            continue
        if path.parent.name in {"archive", "archived"}:
            continue
        paths.append(path)
    return paths


def active_reference_report_paths(vault: Path) -> list[Path]:
    root = vault / "external-reports"
    if not root.is_dir():
        return []
    manifest_path = (vault / REFERENCE_MANIFEST).resolve()
    paths: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in REFERENCE_MANIFEST_EXTENSIONS:
            continue
        if path.resolve() == manifest_path:
            continue
        paths.append(path)
    return paths


def reference_manifest_alignment(vault: Path) -> dict[str, Any]:
    manifest_path = vault / REFERENCE_MANIFEST
    expected_paths = sorted(report_path(vault, path) for path in active_reference_report_paths(vault))
    if not manifest_path.is_file():
        return {
            "status": "missing_manifest",
            "expected_reference_paths": expected_paths,
            "manifest_reference_paths": [],
            "missing_active_report_paths": expected_paths,
            "stale_reference_paths": [],
        }
    manifest = load_json_object(manifest_path)
    references = as_list(manifest.get("references"))
    manifest_paths = sorted(
        str(item.get("path"))
        for item in references
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    )
    if len(manifest_paths) != len(references):
        status = "unreadable_manifest"
    else:
        missing = sorted(set(expected_paths) - set(manifest_paths))
        stale = sorted(set(manifest_paths) - set(expected_paths))
        status = "current" if not missing and not stale else "drift"
    missing_paths = sorted(set(expected_paths) - set(manifest_paths))
    stale_paths = sorted(set(manifest_paths) - set(expected_paths))
    return {
        "status": status,
        "expected_reference_paths": expected_paths,
        "manifest_reference_paths": manifest_paths,
        "missing_active_report_paths": missing_paths,
        "stale_reference_paths": stale_paths,
    }


def archived_report_count(vault: Path) -> int:
    archive = vault / "external-reports" / "archive"
    if not archive.is_dir():
        return 0
    return sum(
        1
        for path in archive.iterdir()
        if path.is_file() and path.suffix.lower() in REPORT_EXTENSIONS
    )


def report_text(path: Path) -> str:
    if path.suffix.lower() not in NARRATIVE_REPORT_EXTENSIONS:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def content_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def priority_counts(text: str) -> dict[str, int]:
    return {
        priority: len(re.findall(rf"\b{priority}\b", text))
        for priority in ("P0", "P1", "P2")
    }


def matched_actions(text: str) -> list[str]:
    matches: list[str] = []
    for action in ACTION_CATALOG:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in action["patterns"]):
            matches.append(str(action["action_id"]))
    return matches


def coverage_markers(path: Path, text: str) -> list[str]:
    haystack = f"{path.name}\n{text}"
    return [
        marker
        for marker, pattern in COVERAGE_MARKER_PATTERNS
        if re.search(pattern, haystack, flags=re.IGNORECASE)
    ]


def release_run_verified(vault: Path) -> bool:
    closeout = load_json_object(vault / "ops/reports/release-closeout-summary.json")
    closeout_summary = as_dict(closeout.get("summary"))
    closeout_status_view = release_status_v2_view_with_readiness_fallback(closeout)
    release_authority_status = str(closeout_status_view["release_authority_status"])
    dashboard = load_json_object(vault / "ops/reports/release-evidence-dashboard.json")
    dashboard_summary = as_dict(dashboard.get("summary"))
    dashboard_status = str(dashboard.get("status", "")).strip()
    full_summary = load_json_object(vault / "ops/reports/test-execution-summary-full.json")
    full_counts = as_dict(full_summary.get("counts"))
    source_package = load_json_object(vault / "ops/reports/source-package-clean-extract.json")
    fixed_point = load_json_object(vault / "ops/reports/release-closeout-fixed-point.json")
    finality = load_json_object(vault / "ops/reports/release-closeout-finality-attestation.json")
    finality_fixed_point = as_dict(finality.get("fixed_point_report"))
    return (
        closeout.get("status") == "pass"
        and closeout_summary.get("live_make_check_status") == "pass"
        and bool(closeout_status_view["status_v2_available"])
        and release_authority_status in {"clean_pass", "conditional_pass"}
        and dashboard_status in {"pass", "attention"}
        and as_int(dashboard_summary.get("live_rerun_fail_count")) == 0
        and authoritative_live_rerun_not_run_count(dashboard) == 0
        and as_int(dashboard_summary.get("required_input_fail_count")) == 0
        and full_summary.get("status") == "pass"
        and as_int(full_counts.get("failed")) == 0
        and as_int(full_counts.get("errors")) == 0
        and source_package.get("status") == "pass"
        and fixed_point.get("status") == "pass"
        and bool(fixed_point.get("converged"))
        and finality_fixed_point.get("status") == "pass"
    )


def json_report_status(path: Path) -> str:
    payload = load_json_object(path)
    if not payload:
        return "planned"
    if payload.get("status") in {"pass", "ready"}:
        return "implemented"
    if payload.get("status") in {"attention", "conditional_pass"}:
        return "partially_automated"
    return "requires_release_run_verification"


def single_source_status(vault: Path) -> str:
    planner_path = vault / "tmp" / "workflow-dependency-planner.json"
    guard_path = vault / "tmp" / "release-workflow-order-guard.json"
    planner = load_json_object(planner_path)
    guard = load_json_object(guard_path)
    if not planner or not guard:
        makefile_path = vault / "Makefile"
        if not makefile_path.is_file():
            if guard.get("status") == "pass":
                return "partially_automated"
            return "planned"
    runtime_context = RuntimeContext(display_timezone=dt.timezone.utc)
    if not guard:
        guard = build_release_workflow_order_guard_report(vault, context=runtime_context)
    if not planner:
        planner = build_workflow_dependency_report(vault, context=runtime_context)
    rules = as_list(planner.get("workflow_rules"))
    planner_targets: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("workflow_id") != "workflow_dependency_planner_closeout":
            continue
        targets = rule.get("targets")
        if not isinstance(targets, list):
            continue
        planner_targets.extend(str(target) for target in targets)
    has_policy_targets = "generated-artifact-index-body" in planner_targets
    if guard.get("status") == "pass" and has_policy_targets:
        return "implemented"
    if guard:
        return "partially_automated"
    return "planned"


def authoritative_live_rerun_not_run_count(dashboard: dict[str, Any]) -> int:
    count = 0
    for gate in as_list(dashboard.get("gates")):
        gate_payload = as_dict(gate)
        live_rerun_state = as_dict(gate_payload.get("live_rerun_state"))
        if (
            bool(gate_payload.get("authoritative_for_release"))
            and str(live_rerun_state.get("status", "")).strip() == "not_run"
        ):
            count += 1
    return count


def status_from_evidence(vault: Path, action: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    evidence = []
    existing_count = 0
    for rel_path in action["evidence_paths"]:
        path = vault / str(rel_path)
        payload = load_json_object(path) if path.suffix == ".json" else {}
        exists = path.exists()
        existing_count += 1 if exists else 0
        evidence.append(
            {
                "path": str(rel_path),
                "exists": exists,
                "status": str(payload.get("status", "")) if payload else "",
                "producer": str(payload.get("producer", "")) if payload else "",
            }
        )
    action_id = str(action["action_id"])
    if action_id == "release_writer_dependency_single_source":
        status = single_source_status(vault)
    elif action_id == "outcome_provenance_gate_policy":
        status = json_report_status(vault / "ops/reports/outcome-provenance-gate-policy.json")
    elif action_id == "external_report_lifecycle":
        alignment = reference_manifest_alignment(vault)
        if alignment["status"] == "current":
            status = "implemented"
        elif (vault / REFERENCE_MANIFEST).exists():
            status = "partially_automated"
        else:
            status = "planned"
    elif action_id in {
        "script_output_surfaces_currentness",
        "function_budget_proposal_adapter",
        "windows_path_and_archive_alias_parity",
    }:
        status = "implemented" if existing_count == len(action["evidence_paths"]) else "planned"
    elif action_id in RELEASE_VERIFIED_ACTION_IDS and existing_count == len(action["evidence_paths"]):
        status = "implemented" if release_run_verified(vault) else "requires_release_run_verification"
    elif existing_count == len(action["evidence_paths"]):
        status = "requires_release_run_verification"
    elif existing_count:
        status = "partially_automated"
    else:
        status = "planned"
    return status, evidence


def action_statuses(vault: Path) -> dict[str, str]:
    return {
        str(action["action_id"]): status_from_evidence(vault, action)[0]
        for action in ACTION_CATALOG
    }


def report_coverage_item(vault: Path, path: Path) -> dict[str, Any]:
    rel_path = report_path(vault, path)
    text = report_text(path)
    action_ids = matched_actions(text) if text else ["external_report_lifecycle"]
    return {
        "path": rel_path,
        "report_type": "reference_manifest" if path.name == "report-reference-manifest.json" else "narrative_report",
        "priority_mentions": priority_counts(text),
        "matched_action_ids": action_ids,
        "matched_action_count": len(action_ids),
    }


def report_lifecycle_profiles(vault: Path, paths: list[Path]) -> list[dict[str, Any]]:
    profiles = []
    for path in paths:
        text = report_text(path)
        coverage = report_coverage_item(vault, path)
        rel_parts = Path(str(coverage["path"])).parts
        profiles.append(
            {
                **coverage,
                "lifecycle_namespace": "archive" if "archive" in rel_parts else "active_root",
                "line_count": len(text.splitlines()) if text else None,
                "content_sha256": content_sha256(path),
                "coverage_markers": coverage_markers(path, text),
                "explicit_archive_status": bool(ARCHIVE_STATUS_RE.search(text)),
                "explicit_successor_paths": sorted(
                    item.strip()
                    for item in SUPERSEDED_BY_RE.findall(text)
                    if item.strip()
                ),
            }
        )
    return profiles


def content_lifecycle_inventory(vault: Path) -> list[dict[str, Any]]:
    return report_lifecycle_profiles(vault, active_report_paths(vault))


def _unresolved_action_ids(profile: dict[str, Any], statuses: dict[str, str]) -> set[str]:
    return {
        str(action_id)
        for action_id in profile["matched_action_ids"]
        if statuses.get(str(action_id)) != "implemented"
    }


def _coverage_authority(profile: dict[str, Any], statuses: dict[str, str]) -> tuple[int, int, int, int]:
    unresolved = _unresolved_action_ids(profile, statuses)
    namespace_rank = 1 if profile.get("lifecycle_namespace") == "active_root" else 0
    return (
        namespace_rank,
        len(profile.get("coverage_markers", [])),
        len(unresolved),
        int(profile.get("matched_action_count") or 0),
    )


def lifecycle_decision(
    profile: dict[str, Any],
    *,
    profiles: list[dict[str, Any]],
    statuses: dict[str, str],
) -> dict[str, Any]:
    path = str(profile["path"])
    if profile["report_type"] != "narrative_report":
        return {
            "archive_recommended": False,
            "reason": "Reference manifest remains active lifecycle evidence.",
            "superseded_by": [],
        }
    action_ids = {str(action_id) for action_id in profile["matched_action_ids"]}
    if not action_ids:
        if profile.get("lifecycle_namespace") == "archive":
            return {
                "archive_recommended": True,
                "reason": "Archived external report has no structured action coverage; archive remains sticky.",
                "superseded_by": [],
            }
        return {
            "archive_recommended": False,
            "reason": "No structured action coverage was detected; keep active for operator review.",
            "superseded_by": [],
        }
    if bool(profile["explicit_archive_status"]):
        return {
            "archive_recommended": True,
            "reason": "External report carries an explicit closed/superseded archive lifecycle marker.",
            "superseded_by": list(profile["explicit_successor_paths"]),
        }

    unresolved = sorted(_unresolved_action_ids(profile, statuses))
    if not unresolved:
        return {
            "archive_recommended": True,
            "reason": "All structured action themes from this external report are implemented in canonical evidence.",
            "superseded_by": [],
        }

    unresolved_set = set(unresolved)
    covering_reports = []
    own_authority = _coverage_authority(profile, statuses)
    for other in profiles:
        other_path = str(other["path"])
        if other_path == path or other["report_type"] != "narrative_report":
            continue
        other_actions = {str(action_id) for action_id in other["matched_action_ids"]}
        other_authority = _coverage_authority(other, statuses)
        if unresolved_set.issubset(other_actions) and other_authority > own_authority:
            covering_reports.append(other_path)

    if covering_reports:
        return {
            "archive_recommended": True,
            "reason": (
                "External report has no unique unresolved action themes; remaining open themes are covered by "
                "a broader active external report."
            ),
            "superseded_by": sorted(covering_reports),
        }
    return {
        "archive_recommended": False,
        "reason": "External report still carries unique unresolved action themes not covered by another active report.",
        "superseded_by": [],
    }
