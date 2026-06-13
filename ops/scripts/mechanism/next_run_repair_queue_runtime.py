from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.path_runtime import normalize_repo_path_text
from ops.scripts.proposal_scope_runtime import dedupe_preserve_order
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint

from .auto_improve_next_run_decision_runtime import (
    CARRY_FORWARD_DECISION,
    NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
    NEXT_RUN_FAILURE_REPAIR_FAMILY,
    NEXT_RUN_FAILURE_REPAIR_SOURCE_CANDIDATE_TYPE,
    OPEN_DECISION_STATUS,
    next_run_failure_repair_proposal_id,
)
from .current_target_path_runtime import current_repo_target_paths
from .failure_taxonomy_runtime import GENERATED_EVIDENCE_SETTLE_REQUIRED
from .noop_repair_classifier_runtime import (
    repair_decision_ended_as_noop_mutation_failure,
)

ARTIFACT_FRESHNESS_FAILURE_TAXONOMY_PREFIX = "artifact_freshness_"
STRUCTURAL_COMPLEXITY_FAILURE_TAXONOMY = "structural_complexity_non_regression"
STRUCTURAL_CLEAN_SUPPRESSIBLE_SOURCE_FAMILIES = frozenset(
    {
        NEXT_RUN_FAILURE_REPAIR_FAMILY,
        "queue_unblock",
    }
)
GENERATED_EVIDENCE_SETTLE_ISSUES = frozenset(
    {
        "missing_artifact_envelope",
        "missing_schema",
        "schema_validation_failed",
        "source_revision_mismatch",
        "source_revision_unknown",
        "source_tree_fingerprint_mismatch",
        "source_tree_fingerprint_unknown",
        "unknown_currentness",
    }
)
GENERATED_EVIDENCE_SETTLE_ACTIONS = frozenset(
    {
        "add_schema_or_exclude_noncanonical_json",
        "backfill_artifact_envelope",
        "backfill_currentness_metadata",
        "regenerate_artifact_from_current_schema",
        "regenerate_canonical_report",
        "regenerate_canonical_report_with_source_revision",
        "regenerate_canonical_report_with_source_tree_fingerprint",
    }
)
RAW_REGISTRY_REPAIR_EVIDENCE_MARKERS = (
    "ops/raw-registry.json",
    "ops/reports/raw-registry-preflight-report.json",
    "ops/reports/raw-registry-preflight-reproducibility.json",
    "ops/reports/raw-registry-cross-environment-matrix.json",
    "raw-registry-preflight-report",
    "raw-registry-preflight-reproducibility",
    "raw-registry-cross-environment-matrix",
    "raw_registry_content_sha256_mismatch",
    "raw_registry_export_stale",
    "raw_registry_export_check",
    "raw registry content_sha256",
)
RAW_REGISTRY_EVIDENCE_TEXT_SIZE_LIMIT = 256 * 1024
LOCAL_ONLY_INVENTORY_REPAIR_TARGETS = frozenset(
    {
        "ops/manifest.json",
        "ops/raw-registry.json",
    }
)
RAW_REGISTRY_REPAIR_PRIMARY_TARGET_FALLBACKS = (
    "ops/scripts/registry/raw_registry_export.py",
)
RAW_REGISTRY_REPAIR_SUPPORTING_TARGET_FALLBACKS = (
    "mk/registry.mk",
    "ops/scripts/registry/raw_registry_preflight.py",
    "ops/scripts/registry/raw_registry_runtime.py",
    "ops/schemas/raw-registry-export.schema.json",
    "ops/schemas/raw-registry-preflight-report.schema.json",
)
RAW_REGISTRY_REPAIR_TEST_FALLBACKS = (
    "tests/test_raw_registry_preflight.py",
    "tests/test_raw_registry_runtime.py",
)
SOURCE_SESSION_REPORT_DECISION_KEY = "_source_session_report"
NEXT_RUN_REPAIR_BACKTICK_PATH_RE = re.compile(r"`((?:ops|tests)/[^`\s]+)`")
NEXT_RUN_REPAIR_PLAIN_PATH_RE = re.compile(
    r"\b((?:ops|tests)/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:py|json|md))(?:[:]\d+)?"
)


@dataclass(frozen=True)
class NextRunRepairProposalDependencies:
    with_generated_supporting_targets: Callable[..., list[str]]
    must_change_test_paths: Callable[[Path, list[str]], list[str]]
    generated_must_change_tests: Callable[[Path, list[str]], list[str]]
    resolve_must_change_tests: Callable[..., list[str]]
    proposal_blast_radius_score: Callable[..., int]
    must_not_expand_apply_roots: Callable[..., bool]
    required_artifacts: Callable[[], list[str]]
    proposal_factory: Callable[..., Any]
    priority_breakdown_factory: Callable[[], Any]


@dataclass(frozen=True)
class _NextRunRepairScope:
    primary_targets: list[str]
    supporting_targets: list[str]
    must_change_tests: list[str]
    source_run_id: str
    failure_taxonomy: str
    evidence_paths: list[str]


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def safe_repo_relative_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = normalize_repo_path_text(value)
    if (
        normalized is None
        or normalized in {".", ".."}
        or normalized.startswith(("../", "/"))
    ):
        return None
    return normalized


def _artifact_validates_against_declared_schema(vault: Path, rel_path: str) -> bool:
    path = vault / rel_path
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    schema_path = str(payload.get("$schema", "")).strip()
    if not schema_path:
        return False
    try:
        schema = load_schema_with_vault_override(vault, schema_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    return not validate_with_schema(payload, schema)


def _artifact_freshness_settle_debt_paths(report: dict) -> set[str]:
    paths: set[str] = set()
    top_debt_files = report.get("top_debt_files", [])
    if not isinstance(top_debt_files, list):
        return paths
    for item in top_debt_files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        issues = {str(issue).strip() for issue in item.get("issues", [])}
        recommended_next_action = str(item.get("recommended_next_action", "")).strip()
        if (
            issues & GENERATED_EVIDENCE_SETTLE_ISSUES
            or recommended_next_action in GENERATED_EVIDENCE_SETTLE_ACTIONS
        ):
            paths.add(path)
    return paths


def _current_artifact_freshness_report(vault: Path) -> dict:
    from ops.scripts.artifact_freshness_runtime import build_report

    return build_report(vault)


def _artifact_freshness_settle_debt_now_clean(vault: Path, report: dict) -> bool:
    original_debt_paths = _artifact_freshness_settle_debt_paths(report)
    if not original_debt_paths:
        return False
    try:
        current_report = _current_artifact_freshness_report(vault)
    except (OSError, TypeError, ValueError):
        return False
    if str(current_report.get("status", "")).strip() == "pass":
        return True
    return original_debt_paths.isdisjoint(
        _artifact_freshness_settle_debt_paths(current_report)
    )


def _repo_health_artifact_freshness_failure_now_clean(vault: Path, source_run_id: str) -> bool:
    report_path = vault / "runs" / source_run_id / "repo-health-artifact-freshness-report-check.json"
    try:
        report = _read_json(report_path)
    except (OSError, json.JSONDecodeError):
        return False
    if str(report.get("status", "")).strip() not in {"attention", "fail"}:
        return False
    top_debt_files = report.get("top_debt_files", [])
    if not isinstance(top_debt_files, list):
        return False
    schema_invalid_files = [
        str(item.get("path", "")).strip()
        for item in top_debt_files
        if isinstance(item, dict)
        and "schema_validation_failed" in {
            str(issue).strip() for issue in item.get("issues", [])
        }
        and str(item.get("path", "")).strip()
    ]
    observed_source_tree_fingerprint = str(report.get("source_tree_fingerprint", "")).strip()
    source_tree_mismatch = (
        bool(observed_source_tree_fingerprint)
        and observed_source_tree_fingerprint != release_source_tree_fingerprint(vault)
    )
    if source_tree_mismatch and schema_invalid_files:
        return False
    if not schema_invalid_files:
        return _artifact_freshness_settle_debt_now_clean(vault, report)
    return all(
        _artifact_validates_against_declared_schema(vault, path)
        for path in schema_invalid_files
    ) or _artifact_freshness_settle_debt_now_clean(vault, report)


def _repair_decision_ended_as_clean_repo_health(vault: Path, decision: dict) -> bool:
    failure_taxonomy = str(decision.get("failure_taxonomy", "")).strip()
    if (
        failure_taxonomy
        not in {"repo_health_blocked", GENERATED_EVIDENCE_SETTLE_REQUIRED}
        and not failure_taxonomy.startswith(ARTIFACT_FRESHNESS_FAILURE_TAXONOMY_PREFIX)
    ):
        return False
    source_run_id = str(decision.get("source_run_id", "")).strip()
    if not source_run_id:
        return False
    return _repo_health_artifact_freshness_failure_now_clean(vault, source_run_id)


def _structural_complexity_targets_pass(vault: Path, targets: list[str]) -> bool:
    primary_targets = current_repo_target_paths(vault, targets)
    if not primary_targets:
        return False
    try:
        from ops.scripts.structural_complexity_budget_runtime import (
            DEFAULT_TARGET_PROFILES,
            build_report,
            touched_target_profiles,
        )

        report = build_report(
            vault,
            target_profiles=touched_target_profiles(
                DEFAULT_TARGET_PROFILES,
                primary_targets,
            ),
        )
    except (OSError, TypeError, ValueError):
        return False
    target_statuses = {
        str(target.get("path", "")).strip(): str(target.get("status", "")).strip()
        for target in report.get("targets", [])
        if isinstance(target, dict)
    }
    return all(target_statuses.get(target) == "pass" for target in primary_targets)


def _repair_decision_ended_as_clean_structural_complexity(
    vault: Path,
    decision: dict,
) -> bool:
    if str(decision.get("failure_taxonomy", "")).strip() != STRUCTURAL_COMPLEXITY_FAILURE_TAXONOMY:
        return False
    proposal_family = str(decision.get("proposal_family", "")).strip()
    failure_mode = str(decision.get("failure_mode", "")).strip()
    proposal_id = str(decision.get("proposal_id", "")).strip()
    if proposal_family == "contract_regression_signals":
        return False
    if (
        proposal_family not in STRUCTURAL_CLEAN_SUPPRESSIBLE_SOURCE_FAMILIES
        and failure_mode != NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
        and not proposal_id.startswith("next_run_failure_repair__")
    ):
        return False
    return _structural_complexity_targets_pass(
        vault,
        [str(target) for target in decision.get("primary_targets", [])],
    )


def _text_has_raw_registry_repair_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in RAW_REGISTRY_REPAIR_EVIDENCE_MARKERS)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _decision_declared_raw_registry_repair_evidence(decision: dict) -> bool:
    fields = [
        decision.get("reason", ""),
        decision.get("failure_taxonomy", ""),
        *_string_list(decision.get("primary_targets")),
        *_string_list(decision.get("supporting_targets")),
        *_string_list(decision.get("must_change_tests")),
        *_string_list(decision.get("evidence_paths")),
    ]
    return any(_text_has_raw_registry_repair_marker(str(value)) for value in fields)


def _evidence_file_has_raw_registry_repair_marker(vault: Path, evidence_path: object) -> bool:
    rel_path = safe_repo_relative_path(evidence_path)
    if rel_path is None:
        return False
    path = vault / rel_path
    if not path.is_file():
        return False
    try:
        if path.stat().st_size > RAW_REGISTRY_EVIDENCE_TEXT_SIZE_LIMIT:
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _text_has_raw_registry_repair_marker(text)


def decision_evidence_mentions_raw_registry_repair(vault: Path, decision: dict) -> bool:
    if _decision_declared_raw_registry_repair_evidence(decision):
        return True
    return any(
        _evidence_file_has_raw_registry_repair_marker(vault, path)
        for path in _string_list(decision.get("evidence_paths"))
    )


def _decision_evidence_paths_are_all_missing(vault: Path, decision: dict) -> bool:
    evidence_paths = _string_list(decision.get("evidence_paths"))
    if not evidence_paths:
        return False
    normalized_paths = [
        rel_path
        for rel_path in (safe_repo_relative_path(path) for path in evidence_paths)
        if rel_path is not None
    ]
    if not normalized_paths:
        return False
    return not _existing_evidence_paths(vault, normalized_paths)


def _is_local_only_inventory_repair_target(path: str) -> bool:
    normalized = normalize_repo_path_text(path)
    return normalized in LOCAL_ONLY_INVENTORY_REPAIR_TARGETS


def _non_inventory_current_repo_target_paths(vault: Path, paths: list[str]) -> list[str]:
    return current_repo_target_paths(
        vault,
        [
            path
            for path in paths
            if str(path).strip() and not _is_local_only_inventory_repair_target(str(path))
        ],
    )


def _without_local_only_inventory_targets(paths: list[str]) -> list[str]:
    return [
        path
        for path in paths
        if not _is_local_only_inventory_repair_target(path)
    ]


def _raw_registry_currentness_evidence_clean(vault: Path) -> bool:
    try:
        from ops.scripts.raw_registry_export import raw_registry_export_check
        from ops.scripts.raw_registry_preflight import preflight
        from ops.scripts.registry_exceptions_runtime import RawRegistryRuntimeError

        export_report = raw_registry_export_check(vault)
        if (
            export_report.get("status") != "pass"
            or export_report.get("check_status") != "match"
        ):
            return False
        preflight_report = preflight(vault)
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, RawRegistryRuntimeError):
        return False
    return preflight_report.get("status") == "pass"


def _repair_decision_ended_as_clean_raw_registry(vault: Path, decision: dict) -> bool:
    if not decision_evidence_mentions_raw_registry_repair(vault, decision):
        return False
    return _raw_registry_currentness_evidence_clean(vault)


def _queue_unblock_decision_superseded_by_current_rotation(
    decision: dict,
    current_proposal_ids: set[str],
    *,
    recent_log_overlap_unblock_failure_mode: str,
    recent_log_overlap_unblock_family: str,
) -> bool:
    if str(decision.get("proposal_family", "")).strip() != recent_log_overlap_unblock_family:
        return False
    source_proposal_id = str(decision.get("proposal_id", "")).strip()
    if not source_proposal_id.startswith(f"{recent_log_overlap_unblock_failure_mode}__"):
        return False
    if source_proposal_id in current_proposal_ids:
        return False
    return any(
        proposal_id.startswith(f"{recent_log_overlap_unblock_failure_mode}__")
        for proposal_id in current_proposal_ids
    )


def _noop_repair_superseded_source_observed_at_by_key(
    vault: Path,
    decisions: list[dict],
    *,
    recent_log_overlap_unblock_family: str,
) -> dict[str, str]:
    superseded: dict[str, str] = {}
    for decision in decisions:
        if not repair_decision_ended_as_noop_mutation_failure(
            vault,
            decision,
            queue_unblock_family=recent_log_overlap_unblock_family,
        ):
            continue
        observed_at = str(decision.get("observed_at", "")).strip()
        for field in ("source_candidate_id", "proposal_id"):
            key = str(decision.get(field, "")).strip()
            if not key:
                continue
            previous = superseded.get(key)
            if previous is None or observed_at >= previous:
                superseded[key] = observed_at
    return superseded


def _decision_superseded_by_noop_repair(
    decision: dict,
    superseded_source_observed_at_by_key: dict[str, str],
) -> bool:
    if not superseded_source_observed_at_by_key:
        return False
    observed_at = str(decision.get("observed_at", "")).strip()
    for field in ("decision_id", "target_proposal_id", "proposal_id"):
        key = str(decision.get(field, "")).strip()
        if not key or key not in superseded_source_observed_at_by_key:
            continue
        superseded_at = superseded_source_observed_at_by_key[key]
        if not observed_at or not superseded_at or superseded_at >= observed_at:
            return True
    return False


def _normalized_carry_forward_decisions(next_run_decisions: list[dict]) -> list[dict]:
    normalized_decisions: list[dict] = []
    for decision in next_run_decisions:
        if str(decision.get("decision", "")).strip() != CARRY_FORWARD_DECISION:
            continue
        if str(decision.get("status", "")).strip() != OPEN_DECISION_STATUS:
            continue
        target_proposal_id = str(decision.get("target_proposal_id", "")).strip()
        if not target_proposal_id:
            primary_targets = [
                str(target).strip()
                for target in decision.get("primary_targets", [])
                if str(target).strip()
            ]
            failure_taxonomy = str(decision.get("failure_taxonomy", "")).strip()
            if not primary_targets or not failure_taxonomy:
                continue
            target_proposal_id = next_run_failure_repair_proposal_id(
                primary_targets,
                failure_taxonomy,
            )
        normalized_decisions.append({**decision, "target_proposal_id": target_proposal_id})
    return normalized_decisions


def _carry_forward_decision_currently_suppressed(
    decision: dict,
    *,
    vault: Path | None,
    consumed_decision_ids: set[str],
    current_proposal_ids: set[str],
    superseded_by_noop_repair: dict[str, str],
    recent_log_overlap_unblock_failure_mode: str,
    recent_log_overlap_unblock_family: str,
) -> bool:
    decision_id = str(decision.get("decision_id", "")).strip()
    if decision_id and decision_id in consumed_decision_ids:
        return True
    if _decision_superseded_by_noop_repair(decision, superseded_by_noop_repair):
        return True
    if vault is not None and repair_decision_ended_as_noop_mutation_failure(
        vault,
        decision,
        queue_unblock_family=recent_log_overlap_unblock_family,
    ):
        return True
    if vault is not None and _repair_decision_ended_as_clean_repo_health(vault, decision):
        return True
    if vault is not None and _repair_decision_ended_as_clean_structural_complexity(
        vault,
        decision,
    ):
        return True
    if vault is not None and _repair_decision_ended_as_clean_raw_registry(vault, decision):
        return True
    if vault is not None and _decision_evidence_paths_are_all_missing(vault, decision):
        return True
    return _queue_unblock_decision_superseded_by_current_rotation(
        decision,
        current_proposal_ids,
        recent_log_overlap_unblock_failure_mode=recent_log_overlap_unblock_failure_mode,
        recent_log_overlap_unblock_family=recent_log_overlap_unblock_family,
    )


def open_carry_forward_decisions(
    next_run_decisions: list[dict],
    *,
    vault: Path | None = None,
    consumed_decision_ids: set[str] | None = None,
    current_proposal_ids: set[str] | None = None,
    recent_log_overlap_unblock_failure_mode: str,
    recent_log_overlap_unblock_family: str,
) -> list[dict]:
    latest_by_target: dict[str, dict] = {}
    consumed_decision_ids = consumed_decision_ids or set()
    current_proposal_ids = current_proposal_ids or set()
    normalized_decisions = _normalized_carry_forward_decisions(next_run_decisions)
    superseded_by_noop_repair = (
        _noop_repair_superseded_source_observed_at_by_key(
            vault,
            normalized_decisions,
            recent_log_overlap_unblock_family=recent_log_overlap_unblock_family,
        )
        if vault is not None
        else {}
    )

    for decision in normalized_decisions:
        if _carry_forward_decision_currently_suppressed(
            decision,
            vault=vault,
            consumed_decision_ids=consumed_decision_ids,
            current_proposal_ids=current_proposal_ids,
            superseded_by_noop_repair=superseded_by_noop_repair,
            recent_log_overlap_unblock_failure_mode=recent_log_overlap_unblock_failure_mode,
            recent_log_overlap_unblock_family=recent_log_overlap_unblock_family,
        ):
            continue
        target_proposal_id = str(decision.get("target_proposal_id", "")).strip()
        previous = latest_by_target.get(target_proposal_id)
        if previous is None or (
            str(decision.get("observed_at", "")),
            str(decision.get("decision_id", "")),
        ) >= (
            str(previous.get("observed_at", "")),
            str(previous.get("decision_id", "")),
        ):
            latest_by_target[target_proposal_id] = decision

    open_decisions = list(latest_by_target.values())
    return sorted(
        open_decisions,
        key=lambda item: (
            str(item.get("observed_at", "")),
            str(item.get("target_proposal_id", "")),
        ),
        reverse=True,
    )


def _changed_manifest_extra_scope(
    vault: Path,
    source_run_id: str,
    *,
    must_change_test_paths: Callable[[Path, list[str]], list[str]],
) -> tuple[list[str], list[str]]:
    manifest_path = vault / "runs" / source_run_id / "changed-files-manifest.json"
    if not manifest_path.is_file():
        return [], []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], []
    declared = manifest.get("declared_targets")
    declared = declared if isinstance(declared, dict) else {}
    declared_paths = set(
        current_repo_target_paths(
            vault,
            [
                *[str(path) for path in declared.get("primary_targets", [])],
                *[str(path) for path in declared.get("supporting_targets", [])],
                *[str(path) for path in declared.get("test_files", [])],
            ],
        )
    )
    supporting_targets: list[str] = []
    must_change_tests: list[str] = []
    files = manifest.get("files")
    if not isinstance(files, list):
        return [], []
    for item in files:
        if not isinstance(item, dict):
            continue
        normalized_path = normalize_repo_path_text(item.get("path"))
        if normalized_path is None or normalized_path in declared_paths:
            continue
        if normalized_path.startswith("tests/") and normalized_path.endswith(".py"):
            must_change_tests.append(normalized_path)
        elif normalized_path.startswith("ops/") and (vault / normalized_path).is_file():
            supporting_targets.append(normalized_path)
    return dedupe_preserve_order(supporting_targets), must_change_test_paths(
        vault,
        must_change_tests,
    )


def _evidence_report_paths(vault: Path, evidence_paths: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for evidence_path in evidence_paths:
        normalized_path = normalize_repo_path_text(evidence_path)
        if normalized_path is None:
            continue
        path = vault / normalized_path
        if path.is_file() and path.suffix == ".json":
            resolved.append(path)
    return resolved


def _diagnostic_note_extra_scope(
    vault: Path,
    evidence_paths: list[str],
    *,
    must_change_test_paths: Callable[[Path, list[str]], list[str]],
) -> tuple[list[str], list[str]]:
    supporting_targets: list[str] = []
    must_change_tests: list[str] = []
    for evidence_report_path in _evidence_report_paths(vault, evidence_paths):
        try:
            report = json.loads(evidence_report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        diagnostics = report.get("diagnostics")
        if not isinstance(diagnostics, dict):
            continue
        notes = diagnostics.get("notes")
        if not isinstance(notes, list):
            continue
        for note in notes:
            note_text = str(note)
            note_paths = [
                *NEXT_RUN_REPAIR_BACKTICK_PATH_RE.findall(note_text),
                *NEXT_RUN_REPAIR_PLAIN_PATH_RE.findall(note_text),
            ]
            for match in note_paths:
                normalized_path = normalize_repo_path_text(match)
                if normalized_path is None or not (vault / normalized_path).is_file():
                    continue
                if normalized_path.startswith("tests/") and normalized_path.endswith(".py"):
                    must_change_tests.append(normalized_path)
                elif normalized_path.startswith("ops/"):
                    supporting_targets.append(normalized_path)
    return dedupe_preserve_order(supporting_targets), must_change_test_paths(
        vault,
        must_change_tests,
    )


def _next_run_repair_extra_scope(
    vault: Path,
    *,
    decision: dict,
    source_run_id: str,
    failure_taxonomy: str,
    evidence_paths: list[str],
    must_change_test_paths: Callable[[Path, list[str]], list[str]],
) -> tuple[list[str], list[str]]:
    supporting_targets: list[str] = []
    must_change_tests: list[str] = []
    if failure_taxonomy == "changed_files_manifest_scope":
        manifest_supporting, manifest_tests = _changed_manifest_extra_scope(
            vault,
            source_run_id,
            must_change_test_paths=must_change_test_paths,
        )
        supporting_targets.extend(manifest_supporting)
        must_change_tests.extend(manifest_tests)
    diagnostic_supporting, diagnostic_tests = _diagnostic_note_extra_scope(
        vault,
        evidence_paths,
        must_change_test_paths=must_change_test_paths,
    )
    supporting_targets.extend(diagnostic_supporting)
    must_change_tests.extend(diagnostic_tests)
    original_primary = current_repo_target_paths(
        vault,
        [str(target) for target in decision.get("primary_targets", [])],
    )
    return (
        [
            path
            for path in dedupe_preserve_order(supporting_targets)
            if path not in original_primary
        ],
        dedupe_preserve_order(must_change_tests),
    )


def _source_session_report_targets(vault: Path, decision: dict) -> list[str]:
    source_report = safe_repo_relative_path(
        decision.get(SOURCE_SESSION_REPORT_DECISION_KEY)
    )
    if not source_report:
        return []
    return current_repo_target_paths(vault, [source_report])


def _existing_evidence_paths(vault: Path, evidence_paths: list[str]) -> list[str]:
    existing: list[str] = []
    for evidence_path in evidence_paths:
        rel_path = safe_repo_relative_path(evidence_path)
        if rel_path is None:
            continue
        if (vault / rel_path).is_file():
            existing.append(rel_path)
    return dedupe_preserve_order(existing)


def _source_session_report_path(vault: Path, decision: dict) -> str:
    source_report = safe_repo_relative_path(
        decision.get(SOURCE_SESSION_REPORT_DECISION_KEY)
    )
    if source_report and (vault / source_report).is_file():
        return source_report
    return ""


def _next_run_repair_evidence_fragment(
    vault: Path,
    decision: dict,
    *,
    evidence_paths: list[str],
) -> str:
    existing_paths = _existing_evidence_paths(vault, evidence_paths)
    source_session_report = _source_session_report_path(vault, decision)
    display_paths = dedupe_preserve_order(
        [*existing_paths, *([source_session_report] if source_session_report else [])]
    )
    missing_count = len(
        [
            path
            for path in evidence_paths
            if safe_repo_relative_path(path) is not None and path not in existing_paths
        ]
    )

    if display_paths:
        fragment = ", ".join(f"`{path}`" for path in display_paths[:3])
        if len(display_paths) > 3:
            fragment += f", +{len(display_paths) - 3} more"
    else:
        fragment = "the normalized next-run decision record"
    if missing_count:
        fragment += f" ({missing_count} missing leaf evidence path"
        fragment += "s" if missing_count != 1 else ""
        fragment += " omitted)"
    return fragment


def _next_run_repair_scope(
    vault: Path,
    policy: dict,
    decision: dict,
    *,
    dependencies: NextRunRepairProposalDependencies,
) -> _NextRunRepairScope | None:
    raw_registry_repair = decision_evidence_mentions_raw_registry_repair(vault, decision)
    primary_targets = _non_inventory_current_repo_target_paths(
        vault,
        [str(target).strip() for target in decision.get("primary_targets", []) if str(target).strip()],
    )
    if not primary_targets and raw_registry_repair:
        primary_targets = current_repo_target_paths(
            vault,
            list(RAW_REGISTRY_REPAIR_PRIMARY_TARGET_FALLBACKS),
        )
    if not primary_targets:
        return None
    failure_taxonomy = str(decision.get("failure_taxonomy", "")).strip()
    source_run_id = str(decision.get("source_run_id", "")).strip()
    evidence_paths = [
        str(path).strip()
        for path in decision.get("evidence_paths", [])
        if str(path).strip()
    ]
    supporting_targets = dependencies.with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=_non_inventory_current_repo_target_paths(
            vault,
            [
                str(target).strip()
                for target in decision.get("supporting_targets", [])
                if str(target).strip()
            ],
        ),
    )
    supporting_targets = dedupe_preserve_order(
        [
            *supporting_targets,
            *_source_session_report_targets(vault, decision),
        ]
    )
    extra_supporting_targets, extra_must_change_tests = _next_run_repair_extra_scope(
        vault,
        decision=decision,
        source_run_id=source_run_id,
        failure_taxonomy=failure_taxonomy,
        evidence_paths=evidence_paths,
        must_change_test_paths=dependencies.must_change_test_paths,
    )
    raw_registry_supporting_targets = (
        current_repo_target_paths(vault, list(RAW_REGISTRY_REPAIR_SUPPORTING_TARGET_FALLBACKS))
        if raw_registry_repair
        else []
    )
    supporting_targets = dependencies.with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=_without_local_only_inventory_targets(
            dedupe_preserve_order(
                [
                    *supporting_targets,
                    *extra_supporting_targets,
                    *raw_registry_supporting_targets,
                ]
            )
        ),
    )
    must_change_tests = dependencies.must_change_test_paths(
        vault,
        current_repo_target_paths(
            vault,
            [str(target).strip() for target in decision.get("must_change_tests", []) if str(target).strip()],
        ),
    )
    must_change_tests = dedupe_preserve_order(
        [
            *must_change_tests,
            *extra_must_change_tests,
            *(
                current_repo_target_paths(vault, list(RAW_REGISTRY_REPAIR_TEST_FALLBACKS))
                if raw_registry_repair
                else []
            ),
            *dependencies.generated_must_change_tests(vault, [*primary_targets, *supporting_targets]),
        ]
    )
    if not must_change_tests:
        must_change_tests = dependencies.resolve_must_change_tests(
            vault,
            policy,
            primary_targets=primary_targets,
            supporting_targets=supporting_targets,
        )
    return _NextRunRepairScope(
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        must_change_tests=must_change_tests,
        source_run_id=source_run_id,
        failure_taxonomy=failure_taxonomy,
        evidence_paths=evidence_paths,
    )


def next_run_repair_proposal(
    vault: Path,
    policy: dict,
    decision: dict,
    *,
    dependencies: NextRunRepairProposalDependencies,
) -> Any | None:
    allowed_failure_modes = set(policy["mutation_proposal"]["allowed_failure_modes"])
    if NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE not in allowed_failure_modes:
        return None

    scope = _next_run_repair_scope(
        vault,
        policy,
        decision,
        dependencies=dependencies,
    )
    if scope is None:
        return None

    target_proposal_id = str(decision.get("target_proposal_id", "")).strip()
    proposal_id = target_proposal_id or next_run_failure_repair_proposal_id(
        scope.primary_targets,
        scope.failure_taxonomy,
    )
    blocking_role = str(decision.get("blocking_role", "")).strip()
    role_fragment = f" from {blocking_role}" if blocking_role else ""
    source_proposal_id = str(decision.get("proposal_id", "")).strip()
    scoped_targets = ", ".join(f"`{target}`" for target in scope.primary_targets)
    evidence_fragment = _next_run_repair_evidence_fragment(
        vault,
        decision,
        evidence_paths=scope.evidence_paths,
    )

    pseudo_candidate = {
        "candidate_id": proposal_id,
        "primary_targets": scope.primary_targets,
        "supporting_targets": scope.supporting_targets,
        "tier": str(decision.get("proposal_tier", "supporting")).strip() or "supporting",
    }
    priority_breakdown = dependencies.priority_breakdown_factory()
    return dependencies.proposal_factory(
        proposal_id=proposal_id,
        source_candidate_id=str(decision.get("decision_id", "")).strip() or proposal_id,
        source_candidate_type=NEXT_RUN_FAILURE_REPAIR_SOURCE_CANDIDATE_TYPE,
        family=NEXT_RUN_FAILURE_REPAIR_FAMILY,
        tier="supporting",
        priority=priority_breakdown.final_priority,
        primary_targets=scope.primary_targets,
        supporting_targets=scope.supporting_targets,
        metrics_triggered=[NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE, scope.failure_taxonomy],
        run_ids=[scope.source_run_id or "next-run-decision"],
        failure_mode=NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE,
        single_mechanism_scope=(
            f"repair the `{scope.failure_taxonomy}` failure{role_fragment} on {scoped_targets}; "
            "keep the next mutation bounded to the failed run evidence and do not resume unrelated queue work first"
        ),
        change_hypothesis=(
            f"If the next run addresses `{scope.failure_taxonomy}` from `{scope.source_run_id}` before broad discovery, "
            "the same target set can reach a finalized outcome or expose a narrower follow-up reason."
        ),
        expected_binary_signal=(
            f"the next auto-improve attempt for `{source_proposal_id or proposal_id}` no longer records "
            f"`{scope.failure_taxonomy}` as its failure_taxonomy"
        ),
        blast_radius_score=dependencies.proposal_blast_radius_score(
            pseudo_candidate,
            must_change_tests=scope.must_change_tests,
        ),
        must_change_tests=scope.must_change_tests,
        must_change_budget_signal={
            "signal": f"auto_improve_session.next_run_decisions.{scope.failure_taxonomy}",
            "expected_change": "resolved_or_superseded",
        },
        must_not_expand_apply_roots=dependencies.must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*scope.primary_targets, *scope.supporting_targets],
            must_change_tests=scope.must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=dependencies.required_artifacts(),
        blocked_by=[],
        why_now=(
            f"`{scope.source_run_id}` failed with `{scope.failure_taxonomy}` and the session decision marked it "
            f"carry_forward. Evidence: {evidence_fragment}."
        ),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=[],
    )


def next_run_repair_proposal_models(
    vault: Path,
    policy: dict,
    next_run_decisions: list[dict],
    *,
    consumed_decision_ids: set[str],
    current_proposal_ids: set[str],
    dependencies: NextRunRepairProposalDependencies,
    recent_log_overlap_unblock_failure_mode: str,
    recent_log_overlap_unblock_family: str,
) -> list[Any]:
    models: list[Any] = []
    for decision in open_carry_forward_decisions(
        next_run_decisions,
        vault=vault,
        consumed_decision_ids=consumed_decision_ids,
        current_proposal_ids=current_proposal_ids,
        recent_log_overlap_unblock_failure_mode=recent_log_overlap_unblock_failure_mode,
        recent_log_overlap_unblock_family=recent_log_overlap_unblock_family,
    ):
        proposal = next_run_repair_proposal(
            vault,
            policy,
            decision,
            dependencies=dependencies,
        )
        if proposal is not None:
            models.append(proposal)
    return models


def next_run_decision_queue_diagnostics(
    next_run_decisions: list[dict],
    proposals: list[dict],
    *,
    vault: Path,
    session_report_paths: list[str],
    consumed_decision_ids: set[str],
    recent_log_overlap_unblock_failure_mode: str,
    recent_log_overlap_unblock_family: str,
) -> dict:
    current_proposal_ids = {
        str(proposal.get("proposal_id", "")).strip()
        for proposal in proposals
        if str(proposal.get("failure_mode", "")).strip()
        != NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
        and str(proposal.get("proposal_id", "")).strip()
    }
    open_carry_forward = open_carry_forward_decisions(
        next_run_decisions,
        vault=vault,
        consumed_decision_ids=consumed_decision_ids,
        current_proposal_ids=current_proposal_ids,
        recent_log_overlap_unblock_failure_mode=recent_log_overlap_unblock_failure_mode,
        recent_log_overlap_unblock_family=recent_log_overlap_unblock_family,
    )
    repair_proposals = [
        proposal
        for proposal in proposals
        if proposal.get("failure_mode") == NEXT_RUN_FAILURE_REPAIR_FAILURE_MODE
    ]
    decision_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    for decision in next_run_decisions:
        decision_name = str(decision.get("decision", "")).strip()
        action_name = str(decision.get("next_run_action", "")).strip()
        if decision_name:
            decision_counts[decision_name] = decision_counts.get(decision_name, 0) + 1
        if action_name:
            action_counts[action_name] = action_counts.get(action_name, 0) + 1
    return {
        "session_reports_scanned": len(session_report_paths),
        "decisions_considered": len(next_run_decisions),
        "open_carry_forward_decisions": len(open_carry_forward),
        "repair_proposals_emitted": len(repair_proposals),
        "decision_counts": decision_counts,
        "action_counts": action_counts,
        "selected_target_proposal_ids": [
            str(proposal.get("proposal_id", "")).strip()
            for proposal in repair_proposals
            if str(proposal.get("proposal_id", "")).strip()
        ],
    }
