from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ops.scripts.mechanism.goal_contract_digest_runtime import (
    semantic_goal_contract_digest,
)

from .external_report_inventory_runtime import (
    as_dict,
    as_int,
    as_list,
    load_json_object,
)

CODEOWNERS_OWNER_RE = re.compile(
    r"^@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?$"
)
MARKDOWN_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
PLACEHOLDER_TEXT_RE = re.compile(
    r"\b(?:placeholder|todo|tbd|example only)\b",
    re.IGNORECASE,
)
REVIEW_HEADING_RE = re.compile(r"\breviews?\b", re.IGNORECASE)
POLICY_LANGUAGE_RE = re.compile(
    r"\b(?:must|should|required|requires|policy|taxonomy|governance)\b",
    re.IGNORECASE,
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


def implemented_artifact_report(vault: Path, rel_path: str, artifact_kind: str) -> bool:
    payload = load_json_object(vault / rel_path)
    return payload.get("artifact_kind") == artifact_kind and bool(payload.get("producer"))


def canonical_json_digest(payload: dict[str, Any]) -> str:
    return semantic_goal_contract_digest(payload)


def current_contract_digest(vault: Path) -> str:
    contract = load_json_object(vault / "ops/reports/codex-goal-contract.json")
    return semantic_goal_contract_digest(contract) if contract else ""


def goal_status_contract_digest(vault: Path, goal: dict[str, Any]) -> str:
    contract_path = str(goal.get("contract_path", "")).strip()
    if contract_path == "ops/reports/codex-goal-contract.json" or (
        contract_path.startswith("runs/goal-")
        and contract_path.endswith("/state/codex-goal-contract.json")
    ):
        contract = load_json_object(vault / contract_path)
        return semantic_goal_contract_digest(contract) if contract else ""
    return current_contract_digest(vault)


def goal_runtime_certificate_noncertifiable_closed_failure(
    vault: Path,
    goal_status_report: dict[str, Any],
) -> bool:
    certificate = load_json_object(vault / "ops/reports/goal-runtime-certificate.json")
    if (
        certificate.get("artifact_kind") != "goal_runtime_certificate"
        or certificate.get("producer") != "ops.scripts.goal_runtime_certificate_report"
    ):
        return False
    diagnosis = as_dict(certificate.get("diagnosis"))
    if diagnosis.get("certificate_failure_class") != "noncertifiable_closed_failure":
        return False
    run = as_dict(goal_status_report.get("run"))
    current_scope = as_dict(diagnosis.get("current_scope"))
    return bool(
        current_scope.get("run_id") == run.get("run_id")
        and current_scope.get("run_status") == run.get("status")
        and current_scope.get("runtime_mode") == run.get("runtime_mode")
    )


def all_evidence_status(existing_count: int, expected_count: int) -> str | None:
    if existing_count == 0:
        return "planned"
    if existing_count < expected_count:
        return "partially_automated"
    return None


def read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def contains_all(text: str, tokens: tuple[str, ...]) -> bool:
    return all(token in text for token in tokens)


def goal_contract_is_bounded(contract: dict[str, Any]) -> bool:
    budgets = as_dict(contract.get("budgets"))
    runtime = as_dict(contract.get("runtime"))
    goal_backend = as_dict(contract.get("goal_backend"))
    promotion_guard = as_dict(contract.get("promotion_guard"))
    return bool(
        contract.get("$schema") == "ops/schemas/codex-goal-contract.schema.json"
        and contract.get("schema_version") == 1
        and contract.get("status") in {"active", "completed"}
        and as_int(budgets.get("max_wall_clock_seconds")) > 0
        and as_int(budgets.get("max_proposals")) > 0
        and as_int(budgets.get("max_consecutive_failures")) > 0
        and as_int(budgets.get("heartbeat_interval_seconds")) > 0
        and as_int(budgets.get("checkpoint_interval_seconds")) > 0
        and runtime.get("mode") == "self_improvement_loop"
        and as_int(runtime.get("duration_seconds")) > 0
        and runtime.get("certificate_status") in {"unverified", "verified"}
        and bool(goal_backend.get("process_persistent"))
        and goal_backend.get("backend_type") in {"file", "run_local_file"}
        and as_list(contract.get("stop_conditions"))
        and as_list(contract.get("required_evidence"))
        and bool(promotion_guard.get("no_sustained_claim_before_certificate_verified"))
        and not bool(promotion_guard.get("sustained_runtime_claimed"))
    )


def release_authority_service_complete(vault: Path) -> bool:
    core_text = read_text_or_empty(vault / "ops/scripts/core/release_authority_state_runtime.py")
    facade_text = read_text_or_empty(vault / "ops/scripts/release/release_status_v2.py")
    mechanism_text = read_text_or_empty(
        vault / "ops/scripts/mechanism/auto_improve_readiness_release_authority_runtime.py"
    )
    lifecycle_text = read_text_or_empty(
        vault / "ops/scripts/release/external_report_lifecycle_runtime.py"
    )
    inventory_text = read_text_or_empty(vault / "ops/scripts/release/release_authority_inventory.py")
    facade_uses_service = (
        "from ops.scripts.core.release_authority_state_runtime import" in facade_text
        or "from ops.scripts.core import release_authority_state_runtime" in facade_text
    )
    return contains_all(
        core_text,
        (
            "release_status_v2_view",
            "machine_release_allowed_from_status_view",
            "clean_required_preflight_passes",
            "release_authority_reports_verified",
            "current_release_manifest_pass",
            "release_artifact_revision",
        ),
    ) and all(
        (
            facade_uses_service,
            "machine_release_allowed_from_status_view" in mechanism_text,
            "clean_required_preflight_passes" in mechanism_text,
            "release_authority_reports_verified" in lifecycle_text,
            "current_release_manifest_pass" in lifecycle_text,
            "release_artifact_revision" in inventory_text,
        )
    )


def release_currentness_service_complete(vault: Path) -> bool:
    currentness_text = read_text_or_empty(
        vault / "ops/scripts/core/release_currentness_state_runtime.py"
    )
    cohort_text = read_text_or_empty(vault / "ops/scripts/release/release_evidence_cohort.py")
    dashboard_text = read_text_or_empty(
        vault / "ops/scripts/release/release_evidence_dashboard.py"
    )
    dashboard_status_text = read_text_or_empty(
        vault / "ops/scripts/release/release_evidence_dashboard_status_runtime.py"
    )
    closeout_gate_text = read_text_or_empty(
        vault / "ops/scripts/release/release_closeout_gate_runtime.py"
    )
    dashboard_uses_currentness_service = (
        "from ops.scripts.core.release_currentness_state_runtime import" in dashboard_text
        or "from ops.scripts.core.release_currentness_state_runtime import" in dashboard_status_text
    )
    dashboard_uses_live_rerun_state = (
        "live_rerun_state(" in dashboard_text
        or "live_rerun_state(" in dashboard_status_text
    )
    return contains_all(
        currentness_text,
        ("def currentness_field", "def live_rerun_state", "def components_match_current_source_tree"),
    ) and all(
        (
            "from ops.scripts.core.release_currentness_state_runtime import" in cohort_text,
            "from ops.scripts.core.release_currentness_state_runtime import" in closeout_gate_text,
            dashboard_uses_currentness_service,
            dashboard_uses_live_rerun_state,
            "components_match_current_source_tree(" in closeout_gate_text,
        )
    )


def release_risk_service_complete(vault: Path) -> bool:
    risk_text = read_text_or_empty(vault / "ops/scripts/core/release_risk_state_runtime.py")
    closeout_risk_text = read_text_or_empty(
        vault / "ops/scripts/release/release_closeout_risk_runtime.py"
    )
    clean_blocker_text = read_text_or_empty(
        vault / "ops/scripts/release/release_clean_blocker_ledger.py"
    )
    return contains_all(
        risk_text,
        (
            "def release_risk_identity",
            "def release_risk_blocks_clean_lane",
            "def release_risk_list",
            "def release_blocker_entry",
        ),
    ) and all(
        (
            "from ops.scripts.core.release_risk_state_runtime import" in closeout_risk_text,
            "from ops.scripts.core.release_risk_state_runtime import" in clean_blocker_text,
            "release_risk_identity(" in closeout_risk_text,
            "release_risk_blocks_clean_lane(" in clean_blocker_text,
        )
    )


def learning_claim_service_complete(vault: Path) -> bool:
    learning_text = read_text_or_empty(vault / "ops/scripts/core/learning_claim_state_runtime.py")
    dashboard_learning_text = read_text_or_empty(
        vault / "ops/scripts/release/release_evidence_dashboard_learning_delta_runtime.py"
    )
    unlock_text = read_text_or_empty(
        vault / "ops/scripts/learning/learning_delta_scoreboard_unlock_runtime.py"
    )
    return contains_all(
        learning_text,
        (
            "def confirmed_evidence_summary",
            "def confirmed_predicate_results",
            "def confirmed_blocking_predicate_ids",
            "def confirmed_wording_allowed",
        ),
    ) and all(
        (
            "from ops.scripts.core.learning_claim_state_runtime import" in dashboard_learning_text,
            "from ops.scripts.core.learning_claim_state_runtime import" in unlock_text,
            "confirmed_evidence_summary(" in dashboard_learning_text,
            "confirmed_evidence_summary(" in unlock_text,
        )
    )


def workflow_uses_entries(vault: Path, rel_path: str) -> list[str]:
    entries: list[str] = []
    for line in read_text_or_empty(vault / rel_path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"-?\s*uses:\s+([^#\s]+)", stripped)
        if match:
            entries.append(match.group(1))
    return entries


def make_target_exists(vault: Path, rel_path: str, target: str) -> bool:
    text = read_text_or_empty(vault / rel_path)
    return bool(re.search(rf"(?m)^{re.escape(target)}\s*:", text))


def has_codeowners_review_owner(text: str) -> bool:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or PLACEHOLDER_TEXT_RE.search(line):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if any(CODEOWNERS_OWNER_RE.fullmatch(owner) for owner in parts[1:]):
            return True
    return False


def markdown_without_comments(text: str) -> str:
    return MARKDOWN_COMMENT_RE.sub("", text)


def meaningful_markdown_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or PLACEHOLDER_TEXT_RE.search(stripped):
        return ""
    return stripped


def has_pr_review_section(text: str) -> bool:
    in_review_section = False
    for raw_line in markdown_without_comments(text).splitlines():
        line = meaningful_markdown_line(raw_line)
        if not line:
            continue
        heading = MARKDOWN_HEADING_RE.match(line)
        if heading:
            in_review_section = bool(REVIEW_HEADING_RE.search(heading.group(1)))
            continue
        if in_review_section:
            return True
    return False


def has_contributing_commit_governance_policy(text: str) -> bool:
    in_commit_governance_section = False
    for raw_line in markdown_without_comments(text).splitlines():
        line = meaningful_markdown_line(raw_line)
        if not line:
            continue
        heading = MARKDOWN_HEADING_RE.match(line)
        if heading:
            heading_text = heading.group(1).casefold()
            in_commit_governance_section = "commit" in heading_text and (
                "governance" in heading_text
                or "policy" in heading_text
                or "taxonomy" in heading_text
            )
            continue
        if in_commit_governance_section and POLICY_LANGUAGE_RE.search(line):
            return True
    return False


