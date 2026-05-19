from __future__ import annotations

import ast
import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.artifact_freshness_runtime import (
    build_canonical_report_envelope,
    canonical_report_loading_issue,
)
from .auto_improve_readiness_runtime import (
    FALLBACK_PRIMARY_TARGETS,
    FALLBACK_SUPPORTING_TARGETS,
    FALLBACK_TEST_FILES,
)
from ops.scripts.filesystem_runtime import manifest_apply_guard_state
from .current_target_path_runtime import current_repo_target_paths
from .mechanism_candidate_registry_runtime import (
    MECHANISM_CANDIDATE_REGISTRY,
    proposal_fields_for_candidate,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.path_runtime import normalize_repo_path_text
from ops.scripts.policy_runtime import report_path
from ops.scripts.proposal_scope_runtime import resolve_focus_tests
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    MECHANISM_REVIEW_SCHEMA_PATH,
    MUTATION_PROPOSAL_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema_with_vault_override, validate_with_schema

MECHANISM_REVIEW_SCHEMA = MECHANISM_REVIEW_SCHEMA_PATH
MUTATION_PROPOSAL_SCHEMA = MUTATION_PROPOSAL_SCHEMA_PATH
DEFAULT_MECHANISM_REVIEW_REPORT = "ops/reports/mechanism-review-candidates.json"
DEFAULT_OUTCOME_METRICS_REPORT = "ops/reports/outcome-metrics.json"
DEFAULT_SYSTEM_LOG = "system/system-log.md"
QUEUE_PRESSURE_SUMMARY_TOP_N = 3
PRODUCER = "ops.scripts.mutation_proposal_runtime"
SOURCE_COMMAND = (
    "python -m ops.scripts.mutation_proposal "
    "--vault . "
    "--policy-path ops/policies/wiki-maintainer-policy.yaml"
)
BOOTSTRAP_FAILURE_MODE = "bootstrap_history_insufficient"
BOOTSTRAP_SOURCE_CANDIDATE_TYPE = "mechanism_bootstrap_history_candidate"
BOOTSTRAP_FAMILY = "bootstrap_queue_unblock"
BOOTSTRAP_NO_HISTORY_BLOCKER = "no_history"
BOOTSTRAP_NO_HISTORY_RUN_ID = "bootstrap-no-history"
RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE = "recent_log_overlap_queue_blocked"
RECENT_LOG_OVERLAP_UNBLOCK_SOURCE_CANDIDATE_TYPE = (
    "mechanism_recent_log_overlap_queue_unblock_candidate"
)
RECENT_LOG_OVERLAP_UNBLOCK_FAMILY = "queue_unblock"
RECENT_LOG_OVERLAP_UNBLOCK_PRIMARY_TARGETS = [
    "ops/scripts/mechanism/mutation_proposal_runtime.py"
]
RECENT_LOG_OVERLAP_UNBLOCK_TEST_FILES = [
    "tests/test_mutation_proposal.py",
    "tests/test_report_generation_smoke.py",
]
RECENT_LOG_OVERLAP_UNBLOCK_TARGET_OPTIONS = [
    {
        "primary_targets": RECENT_LOG_OVERLAP_UNBLOCK_PRIMARY_TARGETS,
        "test_files": RECENT_LOG_OVERLAP_UNBLOCK_TEST_FILES,
    },
    {
        "primary_targets": [
            "ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py"
        ],
        "test_files": ["tests/test_auto_improve_readiness_runtime.py"],
    },
]
RECENT_LOG_OVERLAP_UNBLOCK_RUN_ID = "recent-log-overlap-queue-blocked"
RECENT_OUTCOME_REWORK_BLOCKER = "recent_outcome_rework"
RECENT_OUTCOME_REWORK_MIN_ATTEMPTS = 2
RESOLVED_PROMOTION_HISTORY_STATUSES = {"archived", "quarantined"}
SCRIPT_OUTPUT_SURFACES_TARGET = "ops/script-output-surfaces.json"


@dataclass(frozen=True)
class RecentLogSection:
    heading: str
    text: str
    source_order: int


@dataclass(frozen=True)
class RecentLogOverlapMatch:
    matched_marker: str
    matched_log_heading: str
    unblock_condition: str

    def to_wire(self, *, proposal_id: str, source_candidate_id: str) -> dict:
        return {
            "proposal_id": proposal_id,
            "source_candidate_id": source_candidate_id,
            "matched_marker": self.matched_marker,
            "matched_log_heading": self.matched_log_heading,
            "unblock_condition": self.unblock_condition,
        }


@dataclass(frozen=True)
class PriorityBreakdown:
    base_priority: int
    historical_calibration_delta: int
    session_calibration_delta: int
    review_candidate_priority: int
    recent_log_overlap_penalty: int
    final_priority: int

    def to_wire(self) -> dict[str, int]:
        return {
            "base_priority": self.base_priority,
            "historical_calibration_delta": self.historical_calibration_delta,
            "session_calibration_delta": self.session_calibration_delta,
            "review_candidate_priority": self.review_candidate_priority,
            "recent_log_overlap_penalty": self.recent_log_overlap_penalty,
            "final_priority": self.final_priority,
        }


@dataclass(frozen=True)
class MutationProposal:
    proposal_id: str
    source_candidate_id: str
    source_candidate_type: str
    family: str
    tier: str
    priority: int
    primary_targets: list[str]
    supporting_targets: list[str]
    metrics_triggered: list[str]
    run_ids: list[str]
    failure_mode: str
    single_mechanism_scope: str
    change_hypothesis: str
    expected_binary_signal: str
    blast_radius_score: int
    must_change_tests: list[str]
    must_change_budget_signal: dict[str, str]
    must_not_expand_apply_roots: bool
    must_not_increase_untyped_surface: bool
    required_artifacts: list[str]
    blocked_by: list[str]
    why_now: str
    priority_breakdown: PriorityBreakdown
    recent_log_overlap_matches: list[RecentLogOverlapMatch]

    def to_wire(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "source_candidate_id": self.source_candidate_id,
            "source_candidate_type": self.source_candidate_type,
            "family": self.family,
            "tier": self.tier,
            "priority": self.priority,
            "primary_targets": self.primary_targets,
            "supporting_targets": self.supporting_targets,
            "metrics_triggered": self.metrics_triggered,
            "run_ids": self.run_ids,
            "failure_mode": self.failure_mode,
            "single_mechanism_scope": self.single_mechanism_scope,
            "change_hypothesis": self.change_hypothesis,
            "expected_binary_signal": self.expected_binary_signal,
            "blast_radius_score": self.blast_radius_score,
            "must_change_tests": self.must_change_tests,
            "must_change_budget_signal": self.must_change_budget_signal,
            "must_not_expand_apply_roots": self.must_not_expand_apply_roots,
            "must_not_increase_untyped_surface": self.must_not_increase_untyped_surface,
            "required_artifacts": self.required_artifacts,
            "blocked_by": self.blocked_by,
            "why_now": self.why_now,
            "priority_breakdown": self.priority_breakdown.to_wire(),
        }


@dataclass(frozen=True)
class QueueSelectionDiagnostics:
    available_proposal_count: int
    selected_proposal_count: int
    runnable_available_count: int
    blocked_available_count: int
    selected_runnable_count: int
    selected_blocked_count: int
    blocked_reason_counts: list[dict]

    def to_wire(self) -> dict:
        return {
            "available_proposal_count": self.available_proposal_count,
            "selected_proposal_count": self.selected_proposal_count,
            "runnable_available_count": self.runnable_available_count,
            "blocked_available_count": self.blocked_available_count,
            "selected_runnable_count": self.selected_runnable_count,
            "selected_blocked_count": self.selected_blocked_count,
            "blocked_reason_counts": self.blocked_reason_counts,
        }


@dataclass(frozen=True)
class _MutationReportInputs:
    runtime_context: RuntimeContext
    effective_policy: dict
    mutation_policy: dict
    mechanism_review_path: Path
    mechanism_review_report: dict
    outcome_metrics_path: Path
    outcome_metrics_report: dict
    system_log: Path
    recent_log_sections: list[RecentLogSection]
    recent_log_section_ordering: str


@dataclass(frozen=True)
class _MutationProposalAssembly:
    available_proposal_models: list[MutationProposal]
    proposal_models: list[MutationProposal]
    available_proposals: list[dict]
    proposals: list[dict]
    skipped_candidates: list[dict]


@dataclass(frozen=True)
class _MutationDiagnosticsAssembly:
    family_session_calibration: dict
    source_evidence_gaps: list[str]
    empty_queue_blockers: list[dict]
    reported_blocked_proposals: int
    status: str
    diagnostics: dict


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_report(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"expected object report at {path}")
    return payload


def _safe_repo_relative_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = normalize_repo_path_text(value)
    if (
        normalized is None
        or normalized == "."
        or normalized == ".."
        or normalized.startswith("../")
        or normalized.startswith("/")
    ):
        return None
    return normalized


def _parse_log_heading_timestamp(heading: str) -> tuple[int, int, int, int, int] | None:
    matched = re.match(r"\[(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})(?: [A-Z]+)?\]", heading)
    if not matched:
        return None
    year, month, day, hour, minute = matched.groups()
    return (int(year), int(month), int(day), int(hour), int(minute))


def _log_heading_datetime(
    heading: str,
    *,
    display_timezone: dt.tzinfo,
) -> dt.datetime | None:
    timestamp = _parse_log_heading_timestamp(heading)
    if timestamp is None:
        return None
    year, month, day, hour, minute = timestamp
    return dt.datetime(year, month, day, hour, minute, tzinfo=display_timezone)


def _filter_recent_log_sections_by_age(
    sections: list[RecentLogSection],
    *,
    runtime_context: RuntimeContext,
    max_age_days: int,
    section_ordering: str,
) -> list[RecentLogSection]:
    if max_age_days <= 0 or section_ordering != "timestamp":
        return sections
    cutoff = runtime_context.utcnow() - dt.timedelta(days=max_age_days)
    filtered: list[RecentLogSection] = []
    for section in sections:
        heading_time = _log_heading_datetime(
            section.heading,
            display_timezone=runtime_context.display_timezone,
        )
        if heading_time is None or heading_time.astimezone(dt.timezone.utc) >= cutoff:
            filtered.append(section)
    return filtered


def _read_log_sections(
    path: Path,
    *,
    max_entries: int,
    max_age_days: int,
    runtime_context: RuntimeContext,
) -> tuple[list[RecentLogSection], str]:
    if max_entries <= 0 or not path.exists():
        return [], "file_order_fallback"

    text = path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", text)
    entries: list[RecentLogSection] = []
    for index, entry in enumerate(section.strip() for section in sections[1:] if section.strip()):
        heading = entry.splitlines()[0].strip() if entry.splitlines() else ""
        entries.append(RecentLogSection(heading=heading, text=entry, source_order=index))
    if not entries:
        return [], "file_order_fallback"

    timestamped = [
        (_parse_log_heading_timestamp(entry.heading), entry.source_order, entry)
        for entry in entries
    ]
    parsed_entries = [
        (timestamp, source_order, entry)
        for timestamp, source_order, entry in timestamped
        if timestamp is not None
    ]
    if len(parsed_entries) == len(entries) or len(parsed_entries) >= max_entries:
        ordered = [
            item
            for _, _, item in sorted(
                parsed_entries,
                key=lambda item: (item[0], item[1]),
            )
        ]
        recent_entries = ordered[-max_entries:]
        return (
            _filter_recent_log_sections_by_age(
                recent_entries,
                runtime_context=runtime_context,
                max_age_days=max_age_days,
                section_ordering="timestamp",
            ),
            "timestamp",
        )
    return (
        _filter_recent_log_sections_by_age(
            entries[-max_entries:],
            runtime_context=runtime_context,
            max_age_days=max_age_days,
            section_ordering="file_order_fallback",
        ),
        "file_order_fallback",
    )


def _log_heading_summary(recent_log_sections: list[RecentLogSection]) -> list[str]:
    return [section.heading for section in recent_log_sections if section.heading]


def _load_mechanism_review_report(vault: Path, path: Path) -> dict:
    schema = load_schema_with_vault_override(vault, MECHANISM_REVIEW_SCHEMA)
    report = _read_json(path)
    loading_issue = canonical_report_loading_issue(path, report)
    if loading_issue:
        raise ValueError(
            "mechanism review report is not current primary evidence: "
            f"{loading_issue}"
        )
    errors = validate_with_schema(report, schema)
    if errors:
        raise ValueError(
            "mechanism review report schema validation failed: "
            f"{errors[0]}"
        )
    return report


def _priority_breakdown(candidate: dict, blocked_by: list[str]) -> PriorityBreakdown:
    historical = candidate.get("historical_calibration", {})
    session = candidate.get("session_calibration", {})
    historical_delta = int(historical.get("priority_delta", 0))
    session_delta = int(session.get("priority_delta", 0))
    base_priority = int(
        historical.get(
            "priority_before_calibration",
            session.get("priority_before_calibration", candidate["priority"]),
        )
    )
    review_candidate_priority = int(candidate["priority"])
    recent_log_overlap_penalty = -15 if blocked_by else 0
    final_priority = max(0, min(100, review_candidate_priority + recent_log_overlap_penalty))
    return PriorityBreakdown(
        base_priority=base_priority,
        historical_calibration_delta=historical_delta,
        session_calibration_delta=session_delta,
        review_candidate_priority=review_candidate_priority,
        recent_log_overlap_penalty=recent_log_overlap_penalty,
        final_priority=final_priority,
    )


def _overlap_markers(primary_targets: list[str], candidate_id: str) -> set[str]:
    markers = {candidate_id.lower()}
    for target in primary_targets:
        normalized = normalize_repo_path_text(target)
        if normalized:
            markers.add(normalized.lower())
            markers.add(Path(normalized).name.lower())
    return markers


def _recent_log_overlap_matches(
    candidate: dict,
    recent_log_sections: list[RecentLogSection],
) -> list[RecentLogOverlapMatch]:
    haystacks = [(section.heading, section.text.lower()) for section in recent_log_sections]
    markers = _overlap_markers(candidate["primary_targets"], candidate["candidate_id"])
    matches: list[RecentLogOverlapMatch] = []
    for marker in sorted(markers):
        if not marker:
            continue
        for heading, section_text in haystacks:
            if marker in section_text:
                matches.append(
                    RecentLogOverlapMatch(
                        matched_marker=marker,
                        matched_log_heading=heading,
                        unblock_condition=(
                            "advance chronology beyond the configured dedupe window "
                            "or max age window, or rotate to a non-overlapping target set"
                        ),
                    )
                )
                return matches
    return matches


def _required_artifacts() -> list[str]:
    return [
        "runs/<run-id>/promotion-report.json",
        "runs/<run-id>/baseline-mechanism-assessment.json",
        "runs/<run-id>/candidate-mechanism-assessment.json",
    ]


def _must_change_budget_signal(fields: dict) -> dict[str, str]:
    failure_mode = str(fields["failure_mode"])
    if failure_mode == "branch_growth_without_test_growth":
        return {
            "signal": "python_branch_node_count",
            "expected_change": "decrease_or_hold",
        }
    if failure_mode == "high_complexity_low_test_pressure":
        return {
            "signal": "test_case_count",
            "expected_change": "increase",
        }
    if failure_mode == "schema_change_without_test_guardrails":
        return {
            "signal": "test_case_count",
            "expected_change": "increase",
        }
    if failure_mode == "policy_surface_growth_without_eval_gain":
        return {
            "signal": "nonempty_line_count_total",
            "expected_change": "decrease_or_hold",
        }
    if failure_mode == "repeated_discard_runs":
        return {
            "signal": "outcome_metrics.moving_averages.discard",
            "expected_change": "decrease_after_finalized_attempt",
        }
    if failure_mode == "repeated_same_eval_after_promote":
        return {
            "signal": "strict_secondary_improvement_present",
            "expected_change": "true_for_equal_score_promotion",
        }
    return {
        "signal": "candidate_eval.total_score",
        "expected_change": "increase_or_equal_score_secondary",
    }


def _target_module_name(target: str) -> str | None:
    normalized_target = normalize_repo_path_text(target)
    if normalized_target is None or not normalized_target.endswith(".py"):
        return None

    target_path = Path(normalized_target)
    return ".".join(target_path.with_suffix("").parts)


def _test_imports_target_module(test_path: Path, target: str) -> bool:
    module_name = _target_module_name(target)
    if module_name is None:
        return False

    leaf_module = module_name.rsplit(".", 1)[-1]
    tree = ast.parse(test_path.read_text(encoding="utf-8"), filename=test_path.as_posix())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name == module_name or imported.name.endswith(f".{leaf_module}"):
                    return True
        if not isinstance(node, ast.ImportFrom):
            continue
        imported_from = node.module or ""
        if imported_from == module_name or imported_from.endswith(f".{leaf_module}"):
            return True
        if imported_from and any(alias.name == leaf_module for alias in node.names):
            if f"{imported_from}.{leaf_module}" == module_name:
                return True
    return False


def _content_evidence_tests(vault: Path, primary_targets: list[str]) -> list[str]:
    resolved: list[str] = []
    for test_path in sorted(vault.glob("tests/test_*.py")):
        if not test_path.is_file():
            continue
        if any(_test_imports_target_module(test_path, target) for target in primary_targets):
            resolved.append(test_path.relative_to(vault).as_posix())
    return resolved


def _resolve_must_change_tests(
    vault: Path,
    policy: dict,
    *,
    primary_targets: list[str],
    supporting_targets: list[str],
) -> list[str]:
    scoped_tests = resolve_focus_tests(
        vault,
        policy,
        primary_targets,
        supporting_targets,
    )
    if scoped_tests:
        return scoped_tests
    return _content_evidence_tests(vault, primary_targets)


def _generated_supporting_targets(vault: Path, primary_targets: list[str]) -> list[str]:
    if not (vault / SCRIPT_OUTPUT_SURFACES_TARGET).is_file():
        return []
    for target in primary_targets:
        normalized_target = normalize_repo_path_text(target)
        if normalized_target and normalized_target.startswith("ops/scripts/") and normalized_target.endswith(".py"):
            return [SCRIPT_OUTPUT_SURFACES_TARGET]
    return []


def _with_generated_supporting_targets(
    vault: Path,
    *,
    primary_targets: list[str],
    supporting_targets: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for target in [*supporting_targets, *_generated_supporting_targets(vault, primary_targets)]:
        if target in seen:
            continue
        seen.add(target)
        ordered.append(target)
    return ordered


def _proposal_blast_radius_score(
    candidate: dict,
    *,
    must_change_tests: list[str],
) -> int:
    score = 10
    distinct_targets = list(dict.fromkeys([*candidate["primary_targets"], *candidate["supporting_targets"]]))
    for path in distinct_targets:
        if path.startswith("ops/policies/"):
            score += 15
        elif path.startswith("ops/schemas/"):
            score += 12
        elif path.startswith("system/"):
            score += 12
        elif path.startswith("ops/scripts/"):
            score += 5
        elif path.startswith("tests/"):
            score += 3
        else:
            score += 10
    score += max(len(candidate["primary_targets"]) - 1, 0) * 10
    score += len(candidate["supporting_targets"]) * 3
    score += max(len(must_change_tests) - 1, 0) * 2
    if str(candidate.get("tier", "")) == "core":
        score += 5
    return max(0, min(100, score))


def _must_not_expand_apply_roots(
    vault: Path,
    policy: dict,
    *,
    proposal_targets: list[str],
    must_change_tests: list[str],
) -> bool:
    guard_state = manifest_apply_guard_state(
        {
            "files": [
                {"path": path, "change_type": "modified"}
                for path in [*proposal_targets, *must_change_tests]
            ]
        },
        policy["auto_improve_policy"]["allowed_apply_roots"],
    )
    return not guard_state.invalid_paths and not guard_state.disallowed_paths


def _why_now(candidate: dict, run_ids: list[str], blocked_by: list[str]) -> str:
    metrics = ", ".join(candidate["metrics_triggered"])
    message = (
        f"{candidate['family']} family에서 `{metrics}` 신호가 최근 {len(run_ids)}개 run 기준으로 누적돼 "
        "지금 한 번의 단일 mechanism 실험으로 국소화할 가치가 있다."
    )
    if blocked_by:
        message += " 다만 최근 chronology와 target overlap이 보여 우선순위는 한 단계 낮춘다."
    return message


def _target_slug(primary_targets: list[str]) -> str:
    target_slug = "-".join(Path(target).stem for target in primary_targets)
    target_slug = re.sub(r"[^a-z0-9]+", "-", target_slug.lower()).strip("-")
    return target_slug


def _proposal_id(candidate: dict, failure_mode: str) -> str:
    target_slug = _target_slug(candidate["primary_targets"])
    return f"{failure_mode}__{target_slug or candidate['candidate_id']}"


def _proposal_metrics_triggered(candidate: dict, failure_mode: str) -> list[str]:
    metrics = [str(item).strip() for item in candidate.get("metrics_triggered", []) if str(item).strip()]
    failure_mode_metrics = {
        "repeated_discard_runs": ["repeated_discard_runs"],
        "repeated_same_eval_after_promote": ["stage1_same_eval_rate"],
    }.get(failure_mode)
    if failure_mode_metrics is None:
        return metrics
    selected = [metric for metric in failure_mode_metrics if metric in metrics]
    return selected or metrics


def _proposal_run_ids(candidate: dict, failure_mode: str, *, lookback_runs: int) -> list[str]:
    all_run_ids = [str(run_id).strip() for run_id in candidate.get("run_ids", []) if str(run_id).strip()]
    signal_run_ids = candidate.get("signal_run_ids")
    if isinstance(signal_run_ids, dict):
        selected_run_ids = [
            str(run_id).strip()
            for run_id in signal_run_ids.get(failure_mode, [])
            if str(run_id).strip()
        ]
        if selected_run_ids:
            return list(dict.fromkeys(selected_run_ids))[-lookback_runs:]
    return all_run_ids[-lookback_runs:]


def _bootstrap_priority(group: dict) -> int:
    blocked_types = list(group.get("blocked_candidate_types", []))
    additional_runs_needed = min(
        (
            int(item.get("additional_runs_needed", 0))
            for item in blocked_types
            if int(item.get("additional_runs_needed", 0)) > 0
        ),
        default=1,
    )
    comparable_runs = int(group.get("comparable_runs", 0))
    priority = 70
    if additional_runs_needed <= 1:
        priority += 15
    elif additional_runs_needed == 2:
        priority += 8
    priority += min(comparable_runs, 3) * 2
    priority += min(len(blocked_types), 3)
    return max(0, min(100, priority))


def _bootstrap_priority_breakdown(priority: int) -> PriorityBreakdown:
    return PriorityBreakdown(
        base_priority=priority,
        historical_calibration_delta=0,
        session_calibration_delta=0,
        review_candidate_priority=priority,
        recent_log_overlap_penalty=0,
        final_priority=priority,
    )


def _bootstrap_blocked_candidate_types(group: dict) -> list[str]:
    blocked_types: list[str] = []
    for item in group.get("blocked_candidate_types", []):
        if not isinstance(item, dict):
            continue
        candidate_type = str(item.get("candidate_type", "")).strip()
        if candidate_type:
            blocked_types.append(candidate_type)
    return blocked_types


def _bootstrap_additional_runs_needed(group: dict) -> int:
    additional_runs = [
        int(item.get("additional_runs_needed", 0))
        for item in group.get("blocked_candidate_types", [])
        if isinstance(item, dict) and int(item.get("additional_runs_needed", 0)) > 0
    ]
    return min(additional_runs, default=1)


def _bootstrap_scope(primary_targets: list[str], additional_runs_needed: int) -> str:
    target_scope = ", ".join(f"`{target}`" for target in primary_targets)
    if additional_runs_needed == 1:
        additional = "one additional"
    else:
        additional = f"{additional_runs_needed} additional"
    return (
        f"keep the next system_mechanism run scoped to {target_scope} and finalize {additional} "
        "comparable run on the same primary target set without expanding apply roots"
    )


def _bootstrap_change_hypothesis(
    primary_targets: list[str],
    blocked_candidate_types: list[str],
    additional_runs_needed: int,
) -> str:
    blocked_summary = ", ".join(blocked_candidate_types) or "trend-based mechanism review candidates"
    if additional_runs_needed == 1:
        run_summary = "one more finalized comparable run"
    else:
        run_summary = f"{additional_runs_needed} more finalized comparable runs"
    return (
        f"If {run_summary} is captured for {', '.join(primary_targets)}, the current bootstrap gate can open "
        f"and {blocked_summary} will become eligible for mechanism review evaluation."
    )


def _bootstrap_expected_binary_signal(primary_targets: list[str]) -> str:
    targets = ", ".join(primary_targets)
    return (
        "mechanism-review bootstrap diagnostics reduce the additional comparable-run requirement for "
        f"{targets}, and candidate-backed mutation proposals appear for the same primary target set"
    )


def _bootstrap_why_now(group: dict, latest_run_id: str) -> str:
    comparable_runs = int(group.get("comparable_runs", 0))
    additional_runs_needed = _bootstrap_additional_runs_needed(group)
    blocked_candidate_types = _bootstrap_blocked_candidate_types(group)
    blocked_summary = ", ".join(blocked_candidate_types) or "trend-based candidates"
    return (
        f"같은 primary target set에 이미 {comparable_runs}개의 comparable run이 있고 최신 근거는 `{latest_run_id}`다. "
        f"여기서 {additional_runs_needed}개만 더 좁게 finalize하면 {blocked_summary} 평가 창을 열 수 있어 현재 queue unblock의 최소 경로다."
    )


def _bootstrap_budget_signal() -> dict[str, str]:
    return {
        "signal": "mechanism_review.summary.candidates_emitted",
        "expected_change": "increase",
    }


def _bootstrap_no_history_budget_signal() -> dict[str, str]:
    return {
        "signal": "mechanism_review.summary.runs_considered",
        "expected_change": "increase",
    }


def _bootstrap_group_proposal(
    vault: Path,
    policy: dict,
    group: dict,
) -> MutationProposal | None:
    primary_targets = current_repo_target_paths(
        vault,
        [str(target).strip() for target in group.get("primary_targets", []) if str(target).strip()],
    )
    latest_run_id = str(group.get("latest_run_id", "")).strip()
    if not primary_targets or not latest_run_id:
        return None

    blocked_candidate_types = _bootstrap_blocked_candidate_types(group)
    additional_runs_needed = _bootstrap_additional_runs_needed(group)
    priority = _bootstrap_priority(group)
    priority_breakdown = _bootstrap_priority_breakdown(priority)
    supporting_targets = _with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=[],
    )
    pseudo_candidate = {
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "tier": "supporting",
    }
    must_change_tests = _resolve_must_change_tests(
        vault,
        policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
    )
    proposal_id = _proposal_id(
        {
            "primary_targets": primary_targets,
            "candidate_id": f"bootstrap_queue_unblock__{'-'.join(Path(target).stem for target in primary_targets)}",
        },
        BOOTSTRAP_FAILURE_MODE,
    )
    return MutationProposal(
        proposal_id=proposal_id,
        source_candidate_id=f"bootstrap_queue_unblock__{'-'.join(Path(target).stem for target in primary_targets)}",
        source_candidate_type=BOOTSTRAP_SOURCE_CANDIDATE_TYPE,
        family=BOOTSTRAP_FAMILY,
        tier="supporting",
        priority=priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=[BOOTSTRAP_FAILURE_MODE],
        run_ids=[latest_run_id],
        failure_mode=BOOTSTRAP_FAILURE_MODE,
        single_mechanism_scope=_bootstrap_scope(primary_targets, additional_runs_needed),
        change_hypothesis=_bootstrap_change_hypothesis(
            primary_targets,
            blocked_candidate_types,
            additional_runs_needed,
        ),
        expected_binary_signal=_bootstrap_expected_binary_signal(primary_targets),
        blast_radius_score=_proposal_blast_radius_score(
            pseudo_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal=_bootstrap_budget_signal(),
        must_not_expand_apply_roots=_must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=_required_artifacts(),
        blocked_by=[BOOTSTRAP_FAILURE_MODE],
        why_now=_bootstrap_why_now(group, latest_run_id),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=[],
    )


def _bootstrap_proposal_models_from_review(
    vault: Path,
    policy: dict,
    mechanism_review_report: dict,
) -> list[MutationProposal]:
    allowed_failure_modes = set(policy["mutation_proposal"]["allowed_failure_modes"])
    if BOOTSTRAP_FAILURE_MODE not in allowed_failure_modes:
        return []
    if mechanism_review_report.get("candidates"):
        return []
    diagnostics = mechanism_review_report.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return []
    bootstrap = diagnostics.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return []
    bootstrap_status = str(bootstrap.get("status", "")).strip()

    if bootstrap_status == BOOTSTRAP_NO_HISTORY_BLOCKER:
        no_history_proposal = _bootstrap_no_history_proposal(vault, policy)
        return [no_history_proposal] if no_history_proposal is not None else []
    if bootstrap_status != BOOTSTRAP_FAILURE_MODE:
        return []

    models: list[MutationProposal] = []
    for group in bootstrap.get("target_groups_under_min_history", []):
        if not isinstance(group, dict):
            continue
        proposal = _bootstrap_group_proposal(vault, policy, group)
        if proposal is not None:
            models.append(proposal)
    return models


def _bootstrap_no_history_proposal(
    vault: Path,
    policy: dict,
) -> MutationProposal | None:
    primary_targets = list(FALLBACK_PRIMARY_TARGETS)
    supporting_targets = _with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=list(FALLBACK_SUPPORTING_TARGETS),
    )
    if not primary_targets:
        return None

    must_change_tests = _resolve_must_change_tests(
        vault,
        policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
    )
    if not must_change_tests:
        must_change_tests = [
            path
            for path in FALLBACK_TEST_FILES
            if (vault / path).exists()
        ]

    priority = 92
    priority_breakdown = _bootstrap_priority_breakdown(priority)
    candidate_id = "bootstrap_queue_unblock__fallback-seed"
    pseudo_candidate = {
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "tier": "supporting",
    }
    return MutationProposal(
        proposal_id=_proposal_id(
            {
                "primary_targets": primary_targets,
                "candidate_id": candidate_id,
            },
            BOOTSTRAP_FAILURE_MODE,
        ),
        source_candidate_id=candidate_id,
        source_candidate_type=BOOTSTRAP_SOURCE_CANDIDATE_TYPE,
        family=BOOTSTRAP_FAMILY,
        tier="supporting",
        priority=priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=[BOOTSTRAP_FAILURE_MODE],
        run_ids=[BOOTSTRAP_NO_HISTORY_RUN_ID],
        failure_mode=BOOTSTRAP_FAILURE_MODE,
        single_mechanism_scope=(
            "finalize one narrow fallback-family system_mechanism run on "
            "`ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py` with supporting scope "
            "`ops/schemas/run-telemetry.schema.json` and `tests/test_auto_improve_iteration_runtime.py`"
        ),
        change_hypothesis=(
            "If the fallback target family gets its first finalized comparable system_mechanism run, "
            "mechanism review can move from no_history to a target-specific bootstrap diagnostic and the queue can reopen on concrete history."
        ),
        expected_binary_signal=(
            "mechanism review bootstrap status moves off no_history for the fallback target family and subsequent queue refreshes surface target-specific candidates or remaining history depth requirements"
        ),
        blast_radius_score=_proposal_blast_radius_score(
            pseudo_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal=_bootstrap_no_history_budget_signal(),
        must_not_expand_apply_roots=_must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=_required_artifacts(),
        blocked_by=[BOOTSTRAP_NO_HISTORY_BLOCKER],
        why_now=(
            "현재 유효한 comparable system_mechanism run이 0건이라 mechanism review가 no_history 상태다. "
            "readiness가 이미 가리키는 fallback target family부터 1건을 좁게 finalized하는 것이 queue reopen의 가장 작은 시작점이다."
        ),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=[],
    )


def _promotion_report_history_resolved(
    vault: Path,
    attempt: dict,
) -> bool:
    report_rel_path = _safe_repo_relative_path(attempt.get("promotion_report"))
    if report_rel_path is None:
        return False

    try:
        promotion_report = _read_json(vault / report_rel_path)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(promotion_report, dict):
        return False

    attempt_run_id = str(attempt.get("run_id", "")).strip()
    report_run_id = str(promotion_report.get("run_id", "")).strip()
    report_path_run_id = Path(report_rel_path).parent.name
    if attempt_run_id:
        if report_run_id and attempt_run_id not in {report_run_id, report_path_run_id}:
            return False
        if not report_run_id and attempt_run_id != report_path_run_id:
            return False

    history = promotion_report.get("history", {})
    if not isinstance(history, dict):
        return False
    history_status = str(history.get("status", "active")).strip().lower()
    return history_status in RESOLVED_PROMOTION_HISTORY_STATUSES


def _recent_unresolved_outcome_attempt_count(
    vault: Path,
    outcome_metrics_report: dict,
    *,
    proposal_id: str,
) -> int:
    recent_attempts = outcome_metrics_report.get("recent_attempts", [])
    if not isinstance(recent_attempts, list):
        return 0

    unresolved_count = 0
    for attempt in recent_attempts:
        if not isinstance(attempt, dict):
            continue
        if str(attempt.get("proposal_id", "")).strip() != proposal_id:
            continue

        outcome = str(attempt.get("outcome", "")).strip().lower()
        decision = str(attempt.get("decision", "")).strip().upper()
        if outcome == "promoted" or decision == "PROMOTE":
            break
        if _promotion_report_history_resolved(vault, attempt):
            continue
        if outcome or decision:
            unresolved_count += 1
    return unresolved_count


def _recent_outcome_rework_blockers(
    vault: Path,
    outcome_metrics_report: dict,
    *,
    proposal_id: str,
) -> list[str]:
    unresolved_count = _recent_unresolved_outcome_attempt_count(
        vault,
        outcome_metrics_report,
        proposal_id=proposal_id,
    )
    if unresolved_count < RECENT_OUTCOME_REWORK_MIN_ATTEMPTS:
        return []
    return [RECENT_OUTCOME_REWORK_BLOCKER]


def _fallback_test_files(vault: Path, test_files: list[str]) -> list[str]:
    existing = [path for path in test_files if (vault / path).exists()]
    return existing or list(test_files)


def _recent_log_overlap_unblock_target_option(
    vault: Path,
    policy: dict,
    *,
    recent_log_sections: list[RecentLogSection],
) -> tuple[list[str], list[str], list[str], list[RecentLogOverlapMatch], str]:
    options: list[
        tuple[list[str], list[str], list[str], list[RecentLogOverlapMatch], str]
    ] = []
    for index, option in enumerate(RECENT_LOG_OVERLAP_UNBLOCK_TARGET_OPTIONS):
        primary_targets = current_repo_target_paths(
            vault,
            [str(target).strip() for target in option["primary_targets"] if str(target).strip()],
        )
        if not primary_targets:
            continue
        supporting_targets = _with_generated_supporting_targets(
            vault,
            primary_targets=primary_targets,
            supporting_targets=[],
        )
        must_change_tests = _resolve_must_change_tests(
            vault,
            policy,
            primary_targets=primary_targets,
            supporting_targets=supporting_targets,
        )
        if not must_change_tests:
            must_change_tests = _fallback_test_files(
                vault,
                [str(path).strip() for path in option["test_files"] if str(path).strip()],
            )
        candidate_id = f"recent_log_overlap_queue_unblock__{_target_slug(primary_targets)}"
        pseudo_candidate = {
            "candidate_id": candidate_id,
            "primary_targets": primary_targets,
            "supporting_targets": supporting_targets,
            "tier": "supporting",
        }
        recent_log_matches = _recent_log_overlap_matches(
            pseudo_candidate,
            recent_log_sections,
        )
        options.append(
            (
                primary_targets,
                supporting_targets,
                must_change_tests,
                recent_log_matches,
                candidate_id,
            )
        )
        if not recent_log_matches:
            return options[-1]

    for option_candidate in options:
        if not option_candidate[3]:
            return option_candidate
    if options:
        return options[0]
    return ([], [], [], [], "recent_log_overlap_queue_unblock__unresolved")


def _recent_log_overlap_queue_unblock_proposal(
    vault: Path,
    policy: dict,
    available_proposals: list[MutationProposal],
    *,
    recent_log_sections: list[RecentLogSection],
    outcome_metrics_report: dict,
) -> MutationProposal | None:
    allowed_failure_modes = set(policy["mutation_proposal"]["allowed_failure_modes"])
    if RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE not in allowed_failure_modes:
        return None
    if not available_proposals:
        return None
    if any(not proposal.blocked_by for proposal in available_proposals):
        return None
    if any(proposal.blocked_by != ["recent_log_overlap"] for proposal in available_proposals):
        return None

    (
        primary_targets,
        supporting_targets,
        must_change_tests,
        recent_log_matches,
        candidate_id,
    ) = _recent_log_overlap_unblock_target_option(
        vault,
        policy,
        recent_log_sections=recent_log_sections,
    )
    if not primary_targets:
        return None

    priority = 91
    priority_breakdown = _bootstrap_priority_breakdown(priority)
    pseudo_candidate = {
        "candidate_id": candidate_id,
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "tier": "supporting",
    }
    proposal_id = _proposal_id(
        {
            "primary_targets": primary_targets,
            "candidate_id": candidate_id,
        },
        RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
    )
    blocked_by = ["recent_log_overlap"] if recent_log_matches else []
    blocked_by.extend(
        blocker
        for blocker in _recent_outcome_rework_blockers(
            vault,
            outcome_metrics_report,
            proposal_id=proposal_id,
        )
        if blocker not in blocked_by
    )
    scoped_target_text = " and ".join(f"`{path}`" for path in primary_targets)
    scoped_test_text = " and ".join(f"`{path}`" for path in must_change_tests)
    return MutationProposal(
        proposal_id=proposal_id,
        source_candidate_id=candidate_id,
        source_candidate_type=RECENT_LOG_OVERLAP_UNBLOCK_SOURCE_CANDIDATE_TYPE,
        family=RECENT_LOG_OVERLAP_UNBLOCK_FAMILY,
        tier="supporting",
        priority=priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=[RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE],
        run_ids=[RECENT_LOG_OVERLAP_UNBLOCK_RUN_ID],
        failure_mode=RECENT_LOG_OVERLAP_UNBLOCK_FAILURE_MODE,
        single_mechanism_scope=(
            f"keep the unblock experiment scoped to {scoped_target_text} and "
            f"{scoped_test_text} so all existing recent-log-overlap-blocked proposals remain "
            "diagnostic evidence while one runnable rotation target reopens the queue"
        ),
        change_hypothesis=(
            "If mutation proposal runtime emits a narrow non-overlapping fallback when every candidate "
            "is blocked only by recent_log_overlap, auto-improve readiness can keep a runnable queue "
            "without weakening the chronology overlap guardrail."
        ),
        expected_binary_signal=(
            "mutation proposal diagnostics retain recent_log_overlap blocked candidates and "
            "queue_selection.runnable_available_count becomes greater than zero"
        ),
        blast_radius_score=_proposal_blast_radius_score(
            pseudo_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal={
            "signal": "mutation_proposal.queue_selection.runnable_available_count",
            "expected_change": "greater_than_zero",
        },
        must_not_expand_apply_roots=_must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=_required_artifacts(),
        blocked_by=blocked_by,
        why_now=(
            "현재 후보들이 모두 recent_log_overlap 하나로만 막히면 live queue가 비어 readiness와 learning "
            "execution gate까지 연쇄적으로 닫힌다. guardrail은 보존하고 target rotation proposal만 별도로 열어둔다."
        ),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=recent_log_matches,
    )


def _proposal_from_candidate(
    vault: Path,
    policy: dict,
    candidate: dict,
    *,
    recent_log_sections: list[RecentLogSection],
) -> MutationProposal | None:
    allowed_failure_modes = set(policy["mutation_proposal"]["allowed_failure_modes"])
    primary_targets = current_repo_target_paths(vault, list(candidate["primary_targets"]))
    supporting_targets = _with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=current_repo_target_paths(vault, list(candidate["supporting_targets"])),
    )
    current_candidate = {
        **candidate,
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
    }
    recent_log_matches = _recent_log_overlap_matches(current_candidate, recent_log_sections)
    blocked_by = ["recent_log_overlap"] if recent_log_matches else []
    fields = proposal_fields_for_candidate(current_candidate, MECHANISM_CANDIDATE_REGISTRY)
    if fields["failure_mode"] not in allowed_failure_modes:
        return None
    metrics_triggered = _proposal_metrics_triggered(current_candidate, fields["failure_mode"])
    run_ids = _proposal_run_ids(
        current_candidate,
        fields["failure_mode"],
        lookback_runs=policy["mutation_proposal"]["lookback_runs"],
    )
    priority_breakdown = _priority_breakdown(current_candidate, blocked_by)
    must_change_tests = _resolve_must_change_tests(
        vault,
        policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
    )

    proposal_id = _proposal_id(current_candidate, fields["failure_mode"])
    return MutationProposal(
        proposal_id=proposal_id,
        source_candidate_id=candidate["candidate_id"],
        source_candidate_type=candidate["candidate_type"],
        family=candidate["family"],
        tier=candidate["tier"],
        priority=priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=metrics_triggered,
        run_ids=run_ids,
        failure_mode=fields["failure_mode"],
        single_mechanism_scope=fields["single_mechanism_scope"],
        change_hypothesis=fields["change_hypothesis"],
        expected_binary_signal=fields["expected_binary_signal"],
        blast_radius_score=_proposal_blast_radius_score(
            current_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal=_must_change_budget_signal(fields),
        must_not_expand_apply_roots=_must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=_required_artifacts(),
        blocked_by=blocked_by,
        why_now=_why_now(
            {**current_candidate, "metrics_triggered": metrics_triggered},
            run_ids,
            blocked_by,
        ),
        priority_breakdown=priority_breakdown,
        recent_log_overlap_matches=recent_log_matches,
    )


def _priority_sort_key(proposal: MutationProposal) -> tuple[int, str]:
    return (-proposal.priority, proposal.proposal_id)


def _report_selection_sort_key(proposal: MutationProposal) -> tuple[bool, int, int, str]:
    return (
        bool(proposal.blocked_by),
        -proposal.priority,
        proposal.blast_radius_score,
        proposal.proposal_id,
    )


def _select_report_proposals(
    proposals: list[MutationProposal],
    *,
    max_proposals: int,
) -> list[MutationProposal]:
    if max_proposals <= 0:
        return []
    return sorted(proposals, key=_report_selection_sort_key)[:max_proposals]


def _blocked_reason_counts(proposals: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for proposal in proposals:
        for reason in proposal.get("blocked_by", []):
            reason_text = str(reason).strip()
            if not reason_text:
                continue
            counts[reason_text] = counts.get(reason_text, 0) + 1
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _queue_selection_diagnostics(
    available_proposals: list[dict],
    selected_proposals: list[dict],
) -> dict:
    return QueueSelectionDiagnostics(
        available_proposal_count=len(available_proposals),
        selected_proposal_count=len(selected_proposals),
        runnable_available_count=sum(
            1 for proposal in available_proposals if not proposal.get("blocked_by")
        ),
        blocked_available_count=sum(
            1 for proposal in available_proposals if proposal.get("blocked_by")
        ),
        selected_runnable_count=sum(
            1 for proposal in selected_proposals if not proposal.get("blocked_by")
        ),
        selected_blocked_count=sum(
            1 for proposal in selected_proposals if proposal.get("blocked_by")
        ),
        blocked_reason_counts=_blocked_reason_counts(available_proposals),
    ).to_wire()


def _recent_log_overlap_diagnostics(
    proposal_models: list[MutationProposal],
    *,
    dedupe_window: int,
    max_age_days: int,
    section_ordering: str,
    recent_log_sections: list[RecentLogSection],
) -> dict:
    return {
        "dedupe_window": dedupe_window,
        "max_age_days": max_age_days,
        "section_ordering": section_ordering,
        "scanned_log_headings": _log_heading_summary(recent_log_sections),
        "matches": [
            match.to_wire(
                proposal_id=proposal.proposal_id,
                source_candidate_id=proposal.source_candidate_id,
            )
            for proposal in proposal_models
            for match in proposal.recent_log_overlap_matches
        ],
    }


def _family_session_calibration_diagnostics(
    mechanism_review_report: dict,
    proposals: list[dict],
) -> dict:
    source_summary = (
        mechanism_review_report.get("diagnostics", {}).get("session_calibration", {})
    )
    enabled = bool(source_summary.get("enabled", True)) if isinstance(source_summary, dict) else True
    source_by_family = {}
    if isinstance(source_summary, dict):
        for item in source_summary.get("by_family", []):
            if not isinstance(item, dict):
                continue
            family = str(item.get("family", "")).strip()
            if family:
                source_by_family[family] = item

    proposal_count_by_family: dict[str, int] = {}
    blocked_count_by_family: dict[str, int] = {}
    for proposal in proposals:
        family = str(proposal.get("family", "")).strip()
        if not family:
            continue
        proposal_count_by_family[family] = proposal_count_by_family.get(family, 0) + 1
        if proposal.get("blocked_by"):
            blocked_count_by_family[family] = blocked_count_by_family.get(family, 0) + 1

    families = sorted(proposal_count_by_family)
    if not proposals:
        status = "no_proposals"
    elif not enabled:
        status = "disabled"
    else:
        status = str(source_summary.get("status", "")).strip() if isinstance(source_summary, dict) else ""
        if status not in {"active", "no_session_context", "disabled"}:
            status = "active"

    by_family = []
    for family in families:
        source_family = source_by_family.get(family, {})
        by_family.append(
            {
                "family": family,
                "proposal_count": proposal_count_by_family.get(family, 0),
                "blocked_proposal_count": blocked_count_by_family.get(family, 0),
                "session_priority_delta": int(source_family.get("total_priority_delta", 0)),
                "boosted_candidates": int(source_family.get("boosted_candidates", 0)),
                "lowered_candidates": int(source_family.get("lowered_candidates", 0)),
                "unchanged_candidates": int(source_family.get("unchanged_candidates", 0)),
                "validation_blocked_sessions": int(source_family.get("validation_blocked_sessions", 0)),
                "review_blocked_sessions": int(source_family.get("review_blocked_sessions", 0)),
                "mutation_failed_sessions": int(source_family.get("mutation_failed_sessions", 0)),
                "validator_dispatch_sessions": int(source_family.get("validator_dispatch_sessions", 0)),
                "reviewer_dispatch_sessions": int(source_family.get("reviewer_dispatch_sessions", 0)),
                "high_risk_routing_sessions": int(source_family.get("high_risk_routing_sessions", 0)),
            }
        )

    return {
        "enabled": enabled,
        "status": status,
        "proposal_count": len(proposals),
        "blocked_proposal_count": sum(1 for proposal in proposals if proposal.get("blocked_by")),
        "by_family": by_family,
    }


def _queue_pressure_summary(
    family_session_calibration: dict,
    *,
    evidence_gaps: list[str] | None = None,
    top_n: int = QUEUE_PRESSURE_SUMMARY_TOP_N,
) -> str:
    status = str(family_session_calibration.get("status", "")).strip()
    by_family = list(family_session_calibration.get("by_family", []))
    evidence_summary = " | ".join((evidence_gaps or [])[:3])
    if status == "no_proposals" or not by_family:
        if evidence_summary:
            return f"no proposals emitted | {evidence_summary}"
        return "no proposals emitted"

    sorted_families = sorted(
        (item for item in by_family if isinstance(item, dict)),
        key=lambda item: (
            -int(item.get("proposal_count", 0)),
            -abs(int(item.get("session_priority_delta", 0))),
            -int(item.get("blocked_proposal_count", 0)),
            str(item.get("family", "")),
        ),
    )

    signal_labels = (
        ("validation_blocked_sessions", "validation"),
        ("review_blocked_sessions", "review"),
        ("mutation_failed_sessions", "mutation"),
        ("validator_dispatch_sessions", "validator"),
        ("reviewer_dispatch_sessions", "reviewer"),
        ("high_risk_routing_sessions", "risk"),
    )
    segments: list[str] = []
    for item in sorted_families[:top_n]:
        proposal_count = int(item.get("proposal_count", 0))
        blocked_count = int(item.get("blocked_proposal_count", 0))
        priority_delta = int(item.get("session_priority_delta", 0))
        family = str(item.get("family", "")).strip() or "<unknown>"
        parts = [
            f"{family} {proposal_count} proposal" + ("" if proposal_count == 1 else "s")
        ]
        if blocked_count > 0:
            parts.append(f"{blocked_count} blocked")
        if priority_delta != 0:
            parts.append(f"delta {priority_delta:+d}")
        active_signals = sorted(
            (
                (label, int(item.get(field, 0)), idx)
                for idx, (field, label) in enumerate(signal_labels)
                if int(item.get(field, 0)) > 0
            ),
            key=lambda entry: (-entry[1], entry[2], entry[0]),
        )
        for label, count, _ in active_signals[:2]:
            parts.append(f"{label} {count}")
        segments.append(", ".join(parts))

    if len(sorted_families) > top_n:
        segments.append(f"+{len(sorted_families) - top_n} more")

    summary = "; ".join(segments)
    if status == "disabled":
        return f"session calibration disabled | {summary}"
    if status == "no_session_context":
        return f"session unavailable | {summary}"
    return summary


def _source_evidence_gaps(mechanism_review_report: dict, proposals: list[dict]) -> list[str]:
    evidence_gaps: list[str] = []
    summary = mechanism_review_report.get("summary", {})
    if isinstance(summary, dict) and int(summary.get("candidates_emitted", 0)) <= 0:
        evidence_gaps.append("mechanism review emitted zero candidates")

    diagnostics = mechanism_review_report.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return evidence_gaps

    session_calibration = diagnostics.get("session_calibration", {})
    if isinstance(session_calibration, dict):
        session_status = str(session_calibration.get("status", "")).strip()
        if session_status == "no_session_context":
            evidence_gaps.append("session_calibration.status=no_session_context")

    outcome_metrics = diagnostics.get("outcome_metrics_calibration", {})
    if isinstance(outcome_metrics, dict):
        outcome_status = str(outcome_metrics.get("status", "")).strip()
        if outcome_status and outcome_status != "active":
            evidence_gaps.append(f"outcome_metrics_calibration.status={outcome_status}")
        for gap in outcome_metrics.get("evidence_gaps", []):
            text = str(gap).strip()
            if text:
                evidence_gaps.append(f"outcome_metrics: {text}")

    if not proposals and not evidence_gaps:
        evidence_gaps.append("proposal queue is empty after applying current mutation_proposal filters")

    deduped: list[str] = []
    seen: set[str] = set()
    for gap in evidence_gaps:
        if gap in seen:
            continue
        seen.add(gap)
        deduped.append(gap)
    return deduped


def _empty_queue_blocker(
    *,
    blocker_type: str,
    reason: str,
    detail: str,
    source: str,
    candidate_id: str | None = None,
    candidate_type: str | None = None,
    primary_targets: list[str] | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "blocker_type": blocker_type,
        "reason": reason,
        "detail": detail,
        "source": source,
    }
    if candidate_id:
        item["candidate_id"] = candidate_id
    if candidate_type:
        item["candidate_type"] = candidate_type
    if primary_targets:
        item["primary_targets"] = primary_targets
    return item


def _empty_queue_blockers(
    *,
    mutation_enabled: bool,
    mechanism_review_report: dict,
    available_proposals: list[dict],
    proposals: list[dict],
    skipped_candidates: list[dict],
    evidence_gaps: list[str],
) -> list[dict]:
    if proposals:
        return []

    blockers: list[dict] = []
    if not mutation_enabled:
        blockers.append(
            _empty_queue_blocker(
                blocker_type="policy",
                reason="mutation_proposal_disabled",
                detail="mutation_proposal.enabled=false",
                source="mutation_proposal_policy",
            )
        )

    diagnostics = mechanism_review_report.get("diagnostics", {})
    source_blockers = diagnostics.get("candidate_blockers", []) if isinstance(diagnostics, dict) else []
    if isinstance(source_blockers, list):
        for blocker in source_blockers:
            if not isinstance(blocker, dict):
                continue
            blocker_type = str(blocker.get("blocker_type", "")).strip() or "source"
            reason = str(blocker.get("reason", "")).strip() or "candidate_blocked"
            detail = str(blocker.get("detail", "")).strip() or reason
            primary_targets = [
                str(target)
                for target in blocker.get("primary_targets", [])
                if str(target).strip()
            ]
            blockers.append(
                _empty_queue_blocker(
                    blocker_type=blocker_type,
                    reason=reason,
                    detail=detail,
                    source="mechanism_review.candidate_blockers",
                    candidate_type=str(blocker.get("candidate_type", "")).strip() or None,
                    primary_targets=primary_targets,
                )
            )

    for skipped in skipped_candidates:
        reason = str(skipped.get("reason", "")).strip()
        if reason == "candidate_mapping_error":
            blocker_type = "schema"
        elif reason == "failure_mode_not_allowed":
            blocker_type = "policy"
        else:
            blocker_type = "source"
        blockers.append(
            _empty_queue_blocker(
                blocker_type=blocker_type,
                reason=reason or "candidate_skipped",
                detail=str(skipped.get("detail", "")).strip() or reason or "candidate skipped",
                source="skipped_candidates",
                candidate_id=str(skipped.get("candidate_id", "")).strip() or None,
            )
        )

    if available_proposals and not proposals:
        blockers.append(
            _empty_queue_blocker(
                blocker_type="selection",
                reason="max_proposals_selected_zero",
                detail="available proposals exist but report selection emitted none",
                source="queue_selection",
            )
        )

    if not blockers:
        for gap in evidence_gaps:
            gap_text = str(gap).strip()
            if not gap_text:
                continue
            if gap_text.startswith("session_calibration."):
                blocker_type = "session"
            elif gap_text.startswith("outcome_metrics"):
                blocker_type = "outcome"
            elif "zero candidates" in gap_text:
                blocker_type = "history"
            else:
                blocker_type = "source"
            blockers.append(
                _empty_queue_blocker(
                    blocker_type=blocker_type,
                    reason="evidence_gap",
                    detail=gap_text,
                    source="evidence_gaps",
                )
            )

    if not blockers:
        blockers.append(
            _empty_queue_blocker(
                blocker_type="source",
                reason="proposal_queue_empty_without_specific_blocker",
                detail="proposals_emitted=0 and blocked_proposals=0 after proposal generation",
                source="mutation_proposal",
            )
        )

    return blockers


def _candidate_blocker_count(mechanism_review_report: dict) -> int:
    diagnostics = mechanism_review_report.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return 0
    blockers = diagnostics.get("candidate_blockers", [])
    if not isinstance(blockers, list):
        return 0
    return sum(1 for blocker in blockers if isinstance(blocker, dict))


def _reported_blocked_proposal_count(
    proposals: list[dict],
    empty_queue_blockers: list[dict],
) -> int:
    blocked_proposal_count = sum(1 for proposal in proposals if proposal["blocked_by"])
    if proposals:
        return blocked_proposal_count
    return len(empty_queue_blockers)


def _report_status(*, enabled: bool, proposals: list[dict]) -> str:
    if not enabled:
        return "attention"
    if not proposals:
        return "attention"
    if not any(not proposal.get("blocked_by") for proposal in proposals):
        return "attention"
    return "pass"


def _effective_mutation_policy(
    policy: dict,
    *,
    max_proposals: int | None,
    dedupe_window: int | None,
) -> tuple[dict, dict]:
    mutation_policy = dict(policy["mutation_proposal"])
    if max_proposals is not None:
        mutation_policy["max_proposals"] = max_proposals
    if dedupe_window is not None:
        mutation_policy["dedupe_window"] = dedupe_window
    effective_policy = dict(policy)
    effective_policy["mutation_proposal"] = mutation_policy
    return effective_policy, mutation_policy


def _load_current_mechanism_review_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    mechanism_review_report_path: str | None,
) -> tuple[Path, dict]:
    mechanism_review_path = (
        vault / (mechanism_review_report_path or DEFAULT_MECHANISM_REVIEW_REPORT)
    ).resolve()
    if not mechanism_review_path.exists():
        raise FileNotFoundError(
            f"missing mechanism review report: {report_path(vault, mechanism_review_path)}"
        )
    mechanism_review_report = _load_mechanism_review_report(vault, mechanism_review_path)
    review_policy = mechanism_review_report.get("policy", {})
    if review_policy.get("path") != report_path(vault, policy_path):
        raise ValueError(
            "mechanism review report policy.path does not match current policy: "
            f"{review_policy.get('path')}"
        )
    if review_policy.get("version") != policy["version"]:
        raise ValueError(
            "mechanism review report policy.version does not match current policy: "
            f"{review_policy.get('version')}"
        )
    return mechanism_review_path, mechanism_review_report


def _proposal_models_from_candidates(
    vault: Path,
    effective_policy: dict,
    mechanism_review_report: dict,
    *,
    recent_log_sections: list[RecentLogSection],
    outcome_metrics_report: dict,
) -> tuple[list[MutationProposal], list[dict]]:
    available_proposal_models: list[MutationProposal] = []
    skipped_candidates: list[dict] = []
    if not effective_policy["mutation_proposal"]["enabled"]:
        return available_proposal_models, skipped_candidates

    for candidate in mechanism_review_report["candidates"]:
        try:
            proposal_model = _proposal_from_candidate(
                vault,
                effective_policy,
                candidate,
                recent_log_sections=recent_log_sections,
            )
        except ValueError as exc:
            skipped_candidates.append(
                {
                    "candidate_id": candidate.get("candidate_id", "<unknown>"),
                    "reason": "candidate_mapping_error",
                    "detail": str(exc),
                }
            )
            continue
        if proposal_model is None:
            skipped_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "reason": "failure_mode_not_allowed",
                    "detail": candidate["candidate_type"],
                }
            )
            continue
        available_proposal_models.append(proposal_model)
    available_proposal_models.extend(
        _bootstrap_proposal_models_from_review(vault, effective_policy, mechanism_review_report)
    )
    recent_log_overlap_unblock = _recent_log_overlap_queue_unblock_proposal(
        vault,
        effective_policy,
        available_proposal_models,
        recent_log_sections=recent_log_sections,
        outcome_metrics_report=outcome_metrics_report,
    )
    if recent_log_overlap_unblock is not None:
        available_proposal_models.append(recent_log_overlap_unblock)
    return available_proposal_models, skipped_candidates


def _load_mutation_report_inputs(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    mechanism_review_report_path: str | None,
    system_log_path: str | None,
    max_proposals: int | None,
    dedupe_window: int | None,
    context: RuntimeContext | None,
) -> _MutationReportInputs:
    runtime_context = context or RuntimeContext.from_policy(policy)
    effective_policy, mutation_policy = _effective_mutation_policy(
        policy,
        max_proposals=max_proposals,
        dedupe_window=dedupe_window,
    )
    mechanism_review_path, mechanism_review_report = _load_current_mechanism_review_report(
        vault,
        policy,
        policy_path,
        mechanism_review_report_path,
    )
    outcome_metrics_path = (vault / DEFAULT_OUTCOME_METRICS_REPORT).resolve()
    outcome_metrics_report = _read_optional_report(outcome_metrics_path)
    system_log = (vault / (system_log_path or DEFAULT_SYSTEM_LOG)).resolve()
    recent_log_sections, recent_log_section_ordering = _read_log_sections(
        system_log,
        max_entries=mutation_policy["dedupe_window"],
        max_age_days=int(mutation_policy["recent_log_overlap_max_age_days"]),
        runtime_context=runtime_context,
    )
    return _MutationReportInputs(
        runtime_context=runtime_context,
        effective_policy=effective_policy,
        mutation_policy=mutation_policy,
        mechanism_review_path=mechanism_review_path,
        mechanism_review_report=mechanism_review_report,
        outcome_metrics_path=outcome_metrics_path,
        outcome_metrics_report=outcome_metrics_report,
        system_log=system_log,
        recent_log_sections=recent_log_sections,
        recent_log_section_ordering=recent_log_section_ordering,
    )


def _assemble_mutation_proposals(
    vault: Path,
    inputs: _MutationReportInputs,
) -> _MutationProposalAssembly:
    available_proposal_models, skipped_candidates = _proposal_models_from_candidates(
        vault,
        inputs.effective_policy,
        inputs.mechanism_review_report,
        recent_log_sections=inputs.recent_log_sections,
        outcome_metrics_report=inputs.outcome_metrics_report,
    )
    proposal_models = _select_report_proposals(
        available_proposal_models,
        max_proposals=int(inputs.mutation_policy["max_proposals"]),
    )
    return _MutationProposalAssembly(
        available_proposal_models=available_proposal_models,
        proposal_models=proposal_models,
        available_proposals=[proposal.to_wire() for proposal in available_proposal_models],
        proposals=[proposal.to_wire() for proposal in proposal_models],
        skipped_candidates=skipped_candidates,
    )


def _assemble_mutation_diagnostics(
    inputs: _MutationReportInputs,
    proposal_assembly: _MutationProposalAssembly,
) -> _MutationDiagnosticsAssembly:
    family_session_calibration = _family_session_calibration_diagnostics(
        inputs.mechanism_review_report,
        proposal_assembly.proposals,
    )
    source_evidence_gaps = _source_evidence_gaps(
        inputs.mechanism_review_report,
        proposal_assembly.proposals,
    )
    empty_queue_blockers = _empty_queue_blockers(
        mutation_enabled=bool(inputs.mutation_policy["enabled"]),
        mechanism_review_report=inputs.mechanism_review_report,
        available_proposals=proposal_assembly.available_proposals,
        proposals=proposal_assembly.proposals,
        skipped_candidates=proposal_assembly.skipped_candidates,
        evidence_gaps=source_evidence_gaps,
    )
    reported_blocked_proposals = _reported_blocked_proposal_count(
        proposal_assembly.proposals,
        empty_queue_blockers,
    )
    status = _report_status(
        enabled=bool(inputs.mutation_policy["enabled"]),
        proposals=proposal_assembly.proposals,
    )
    return _MutationDiagnosticsAssembly(
        family_session_calibration=family_session_calibration,
        source_evidence_gaps=source_evidence_gaps,
        empty_queue_blockers=empty_queue_blockers,
        reported_blocked_proposals=reported_blocked_proposals,
        status=status,
        diagnostics={
            "source_mechanism_review_report": "",
            "skipped_candidates": proposal_assembly.skipped_candidates,
            "evidence_gaps": source_evidence_gaps,
            "empty_queue_blockers": empty_queue_blockers,
            "family_session_calibration": family_session_calibration,
            "queue_selection": _queue_selection_diagnostics(
                proposal_assembly.available_proposals,
                proposal_assembly.proposals,
            ),
            "recent_log_overlap": _recent_log_overlap_diagnostics(
                proposal_assembly.available_proposal_models,
                dedupe_window=int(inputs.mutation_policy["dedupe_window"]),
                max_age_days=int(inputs.mutation_policy["recent_log_overlap_max_age_days"]),
                section_ordering=inputs.recent_log_section_ordering,
                recent_log_sections=inputs.recent_log_sections,
            ),
        },
    )


def _mutation_report_payload(
    vault: Path,
    policy: dict,
    policy_path: Path,
    inputs: _MutationReportInputs,
    proposal_assembly: _MutationProposalAssembly,
    diagnostics_assembly: _MutationDiagnosticsAssembly,
) -> dict:
    diagnostics = dict(diagnostics_assembly.diagnostics)
    diagnostics["source_mechanism_review_report"] = report_path(vault, inputs.mechanism_review_path)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=inputs.runtime_context.isoformat_z(),
            artifact_kind="mutation_proposals_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=policy_path,
            schema_path=MUTATION_PROPOSAL_SCHEMA,
            source_paths=[
                "ops/scripts/mechanism/mutation_proposal_runtime.py",
                "ops/scripts/mechanism/current_target_path_runtime.py",
            ],
            file_inputs={
                "mechanism_review_report": report_path(vault, inputs.mechanism_review_path),
                "outcome_metrics": report_path(vault, inputs.outcome_metrics_path),
                "system_log": report_path(vault, inputs.system_log),
            },
            text_inputs={
                "mutation_max_proposals": str(inputs.mutation_policy["max_proposals"]),
                "mutation_dedupe_window": str(inputs.mutation_policy["dedupe_window"]),
                "mutation_recent_log_overlap_max_age_days": str(
                    inputs.mutation_policy["recent_log_overlap_max_age_days"]
                ),
            },
        ),
        "vault": display_path(vault, vault),
        "policy": {
            "path": report_path(vault, policy_path),
            "version": policy["version"],
        },
        "status": diagnostics_assembly.status,
        "summary": {
            "source_candidates_read": len(inputs.mechanism_review_report["candidates"]),
            "log_entries_scanned": len(inputs.recent_log_sections),
            "proposals_emitted": len(proposal_assembly.proposals),
            "blocked_proposals": diagnostics_assembly.reported_blocked_proposals,
            "candidate_blocker_count": _candidate_blocker_count(inputs.mechanism_review_report),
            "proposal_blocker_count": len(diagnostics_assembly.empty_queue_blockers),
            "queue_pressure_summary": _queue_pressure_summary(
                diagnostics_assembly.family_session_calibration,
                evidence_gaps=diagnostics_assembly.source_evidence_gaps,
            ),
        },
        "diagnostics": diagnostics,
        "proposals": proposal_assembly.proposals,
    }


def _validate_and_finalize_mutation_report(
    vault: Path,
    report: dict,
    runtime_context: RuntimeContext,
) -> dict:
    schema = load_schema_with_vault_override(vault, MUTATION_PROPOSAL_SCHEMA)
    errors = validate_with_schema(report, schema)
    if errors:
        raise ValueError(f"mutation proposal report schema validation failed: {errors[0]}")

    finalized_generated_at = runtime_context.isoformat_z()
    report["generated_at"] = finalized_generated_at
    currentness = report.get("currentness")
    if isinstance(currentness, dict):
        currentness["checked_at"] = finalized_generated_at
    return report


def build_report(
    vault: Path,
    policy: dict,
    policy_path: Path,
    *,
    mechanism_review_report_path: str | None = None,
    system_log_path: str | None = None,
    max_proposals: int | None = None,
    dedupe_window: int | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    inputs = _load_mutation_report_inputs(
        vault,
        policy,
        policy_path,
        mechanism_review_report_path=mechanism_review_report_path,
        system_log_path=system_log_path,
        max_proposals=max_proposals,
        dedupe_window=dedupe_window,
        context=context,
    )
    proposal_assembly = _assemble_mutation_proposals(vault, inputs)
    diagnostics_assembly = _assemble_mutation_diagnostics(inputs, proposal_assembly)
    report = _mutation_report_payload(
        vault,
        policy,
        policy_path,
        inputs,
        proposal_assembly,
        diagnostics_assembly,
    )
    return _validate_and_finalize_mutation_report(vault, report, inputs.runtime_context)
