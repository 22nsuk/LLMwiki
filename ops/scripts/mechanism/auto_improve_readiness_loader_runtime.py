from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import canonical_report_loading_issue
from ops.scripts.core.artifact_io_runtime import (
    load_optional_json_object,
    read_json_object,
)
from ops.scripts.learning.learning_readiness_signoff_state import (
    SIGNOFF_REPORT_REL_PATH,
)

from .auto_improve_readiness_constants_runtime import (
    ARTIFACT_FRESHNESS_REPORT_REL_PATH,
    GOAL_WORKTREE_GUARD_REPORT_REL_PATH,
    MECHANISM_REVIEW_REPORT_REL_PATH,
    MUTATION_PROPOSAL_REPORT_REL_PATH,
    OUTCOME_METRICS_REPORT_REL_PATH,
    RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATHS,
    RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH,
    RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH,
    RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH,
    REMEDIATION_BACKLOG_REPORT_REL_PATH,
    SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH,
    SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH,
)


@dataclass(frozen=True)
class ReadinessReportPayloads:
    reports: dict[str, dict[str, Any]]
    reports_present: bool


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json_object(path)
    if canonical_report_loading_issue(path, payload):
        return {}
    return payload


def load_current_mutation_proposal_report(vault: Path) -> dict[str, Any]:
    return _load_json(vault / MUTATION_PROPOSAL_REPORT_REL_PATH)


def _load_selected_contract_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json_object(path)
    loading_issue = canonical_report_loading_issue(path, payload)
    if loading_issue and not loading_issue.startswith("currentness_status="):
        return {}
    return payload


def _load_optional_json(path: Path) -> dict[str, Any]:
    return load_optional_json_object(path)


def _load_release_authority_preflight_json(vault: Path) -> dict[str, Any]:
    for rel_path in RELEASE_AUTHORITY_PREFLIGHT_REPORT_REL_PATHS:
        payload = _load_optional_json(vault / rel_path)
        if payload:
            return {**payload, "_source_rel_path": rel_path}
    return {}


def _required_reports_present(reports: dict[str, dict[str, Any]]) -> bool:
    return all(
        bool(reports[name])
        for name in ("outcome_metrics", "mechanism_review", "mutation_proposal")
    )


def load_readiness_report_payloads(
    vault: Path,
    *,
    outcome_metrics_report: dict[str, Any] | None = None,
    mechanism_review_report: dict[str, Any] | None = None,
    mutation_proposal_report: dict[str, Any] | None = None,
    remediation_backlog_path: str = REMEDIATION_BACKLOG_REPORT_REL_PATH,
) -> ReadinessReportPayloads:
    reports = {
        "outcome_metrics": (
            outcome_metrics_report
            if isinstance(outcome_metrics_report, dict)
            else _load_json(vault / OUTCOME_METRICS_REPORT_REL_PATH)
        ),
        "mechanism_review": (
            mechanism_review_report
            if isinstance(mechanism_review_report, dict)
            else _load_json(vault / MECHANISM_REVIEW_REPORT_REL_PATH)
        ),
        "mutation_proposal": (
            mutation_proposal_report
            if isinstance(mutation_proposal_report, dict)
            else load_current_mutation_proposal_report(vault)
        ),
        "artifact_freshness": _load_json(vault / ARTIFACT_FRESHNESS_REPORT_REL_PATH),
        "selected_contract": _load_selected_contract_json(
            vault / SELECTED_CONTRACT_SUMMARY_REPORT_REL_PATH
        ),
        "source_package": _load_json(
            vault / SOURCE_PACKAGE_CLEAN_EXTRACT_REPORT_REL_PATH
        ),
        "release_closeout": _load_json(
            vault / RELEASE_CLOSEOUT_SUMMARY_REPORT_REL_PATH
        ),
        "release_batch_manifest": _load_json(
            vault / RELEASE_CLOSEOUT_BATCH_MANIFEST_REPORT_REL_PATH
        ),
        "release_finality": _load_json(
            vault / RELEASE_CLOSEOUT_FINALITY_ATTESTATION_REPORT_REL_PATH
        ),
        "release_evidence_cohort": _load_json(
            vault / RELEASE_EVIDENCE_COHORT_REPORT_REL_PATH
        ),
        "artifact_finalization": _load_json(
            vault / RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_REPORT_REL_PATH
        ),
        "release_authority_preflight": _load_release_authority_preflight_json(vault),
        "goal_worktree_guard": _load_optional_json(
            vault / GOAL_WORKTREE_GUARD_REPORT_REL_PATH
        ),
        "remediation_backlog": _load_json(vault / remediation_backlog_path),
        "learning_signoff": _load_optional_json(vault / SIGNOFF_REPORT_REL_PATH),
    }
    return ReadinessReportPayloads(
        reports=reports,
        reports_present=_required_reports_present(reports),
    )
