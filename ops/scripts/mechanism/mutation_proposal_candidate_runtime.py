from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.core.filesystem_runtime import manifest_apply_guard_state
from ops.scripts.core.path_runtime import normalize_repo_path_text
from ops.scripts.core.proposal_scope_runtime import (
    dedupe_preserve_order,
    resolve_focus_tests,
)

from .current_target_path_runtime import current_repo_target_paths
from .mechanism_candidate_registry_runtime import (
    MECHANISM_CANDIDATE_REGISTRY,
    proposal_fields_for_candidate,
)
from .mutation_proposal_loader_runtime import RecentLogSection

REPEATED_DISCARD_FAILURE_MODE = "repeated_discard_runs"
REPEATED_DISCARD_METRIC = "repeated_discard_runs"
STAGE1_SAME_EVAL_METRIC = "stage1_same_eval_rate"
REPEATED_SAME_EVAL_AFTER_PROMOTE_FAILURE_MODE = "repeated_same_eval_after_promote"
SCRIPT_OUTPUT_SURFACES_TARGET = "ops/script-output-surfaces.json"
REPORT_SCHEMA_SAMPLES_TARGET = "tests/fixtures/report_schema_samples.json"
REPORT_SCHEMA_SAMPLE_REGENERATION_TEST = "tests/test_report_schema_sample_regeneration.py"
SAME_EVAL_ADJACENT_SUPPORTING_TARGETS_BY_PRIMARY = {
    "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py": [
        "ops/scripts/mechanism/auto_improve_iteration_telemetry_runtime.py",
    ],
}
CLOSED_REPEATED_DISCARD_BLOCKER_IDS = frozenset(
    {
        "discard_equal_score_secondary_eligibility",
    }
)
CLOSED_REPEATED_DISCARD_ITEM_IDS = frozenset(
    {
        "negative_lesson_discard_equal_score_secondary_eligibility",
    }
)


class CandidateSuppressedByClosedRemediation(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


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


def fixed_priority_breakdown(priority: int) -> PriorityBreakdown:
    return PriorityBreakdown(
        base_priority=priority,
        historical_calibration_delta=0,
        session_calibration_delta=0,
        review_candidate_priority=priority,
        recent_log_overlap_penalty=0,
        final_priority=priority,
    )


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


def must_change_budget_signal(fields: dict) -> dict[str, str]:
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


def _closed_repeated_discard_resolution_items(remediation_backlog_report: dict) -> list[dict]:
    items = remediation_backlog_report.get("items", [])
    if not isinstance(items, list):
        return []

    closed_items: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("status", "")).strip().lower() != "closed":
            continue
        item_id = str(item.get("item_id", "")).strip()
        blocker_id = str(item.get("blocker_id", "")).strip()
        if (
            item_id in CLOSED_REPEATED_DISCARD_ITEM_IDS
            or blocker_id in CLOSED_REPEATED_DISCARD_BLOCKER_IDS
        ):
            closed_items.append(item)
    return closed_items


def _closed_repeated_discard_resolution_detail(items: list[dict]) -> str:
    identifiers = [
        str(item.get("item_id") or item.get("blocker_id") or "").strip()
        for item in items
    ]
    identifiers = [identifier for identifier in identifiers if identifier]
    if not identifiers:
        return "repeated-discard remediation backlog item is closed"
    return "closed remediation backlog item(s): " + ", ".join(sorted(set(identifiers)))


def _candidate_suppressed_by_closed_remediation(
    candidate: dict,
    *,
    failure_mode: str,
    remediation_backlog_report: dict,
) -> str | None:
    if failure_mode != REPEATED_DISCARD_FAILURE_MODE:
        return None
    triggered = {
        str(metric).strip()
        for metric in candidate.get("metrics_triggered", [])
        if str(metric).strip()
    }
    if REPEATED_DISCARD_METRIC not in triggered:
        return None
    closed_items = _closed_repeated_discard_resolution_items(remediation_backlog_report)
    if not closed_items:
        return None
    return _closed_repeated_discard_resolution_detail(closed_items)


def _alternate_candidate_for_closed_failure_mode(
    candidate: dict,
    *,
    closed_failure_mode: str,
) -> dict | None:
    if closed_failure_mode != REPEATED_DISCARD_FAILURE_MODE:
        return None

    metrics = [
        str(metric).strip()
        for metric in candidate.get("metrics_triggered", [])
        if str(metric).strip()
    ]
    remaining_metrics = [metric for metric in metrics if metric != REPEATED_DISCARD_METRIC]
    if STAGE1_SAME_EVAL_METRIC not in remaining_metrics:
        return None
    return {
        **candidate,
        "supporting_targets": [],
        "metrics_triggered": remaining_metrics,
        "_closed_failure_mode_fallback": True,
    }


def _candidate_has_signal_for_failure_mode(candidate: dict, failure_mode: str) -> bool:
    signal_run_ids = candidate.get("signal_run_ids")
    if isinstance(signal_run_ids, dict) and failure_mode in signal_run_ids:
        return any(str(run_id).strip() for run_id in signal_run_ids.get(failure_mode, []))
    metrics = {
        str(metric).strip()
        for metric in candidate.get("metrics_triggered", [])
        if str(metric).strip()
    }
    if failure_mode == REPEATED_SAME_EVAL_AFTER_PROMOTE_FAILURE_MODE:
        return STAGE1_SAME_EVAL_METRIC in metrics
    return bool(metrics)


def _candidate_fields_after_closed_remediation(
    candidate: dict,
    fields: dict,
    *,
    remediation_backlog_report: dict,
) -> tuple[dict, dict, str | None]:
    closed_resolution_detail = _candidate_suppressed_by_closed_remediation(
        candidate,
        failure_mode=fields["failure_mode"],
        remediation_backlog_report=remediation_backlog_report,
    )
    if not closed_resolution_detail:
        return candidate, fields, None

    alternate_candidate = _alternate_candidate_for_closed_failure_mode(
        candidate,
        closed_failure_mode=fields["failure_mode"],
    )
    if alternate_candidate is None:
        raise CandidateSuppressedByClosedRemediation(closed_resolution_detail)
    alternate_fields = proposal_fields_for_candidate(
        alternate_candidate,
        MECHANISM_CANDIDATE_REGISTRY,
    )
    if not _candidate_has_signal_for_failure_mode(
        alternate_candidate,
        alternate_fields["failure_mode"],
    ):
        raise CandidateSuppressedByClosedRemediation(closed_resolution_detail)
    return alternate_candidate, alternate_fields, closed_resolution_detail


def priority_breakdown(candidate: dict, blocked_by: list[str]) -> PriorityBreakdown:
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


def recent_log_overlap_matches(
    candidate: dict,
    recent_log_sections: list[RecentLogSection],
) -> list[RecentLogOverlapMatch]:
    haystacks = [
        (section.heading, section.text.lower())
        for section in recent_log_sections
        if "quarantine" not in section.heading.lower()
    ]
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


def required_artifacts() -> list[str]:
    return [
        "runs/<run-id>/promotion-report.json",
        "runs/<run-id>/baseline-mechanism-assessment.json",
        "runs/<run-id>/candidate-mechanism-assessment.json",
    ]


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
        if (
            imported_from
            and any(alias.name == leaf_module for alias in node.names)
            and f"{imported_from}.{leaf_module}" == module_name
        ):
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


def resolve_must_change_tests(
    vault: Path,
    policy: dict,
    *,
    primary_targets: list[str],
    supporting_targets: list[str],
) -> list[str]:
    generated_tests = generated_must_change_tests(vault, [*primary_targets, *supporting_targets])
    scoped_tests = resolve_focus_tests(
        vault,
        policy,
        primary_targets,
        supporting_targets,
    )
    scoped_tests = must_change_test_paths(vault, scoped_tests)
    if scoped_tests:
        return dedupe_preserve_order([*scoped_tests, *generated_tests])
    return dedupe_preserve_order([*_content_evidence_tests(vault, primary_targets), *generated_tests])


def must_change_test_paths(vault: Path, paths: list[str]) -> list[str]:
    resolved: list[str] = []
    for path in paths:
        normalized_path = normalize_repo_path_text(path)
        if normalized_path is None:
            continue
        name = Path(normalized_path).name
        if (
            normalized_path.startswith("tests/")
            and normalized_path.endswith(".py")
            and (name.startswith("test_") or name.endswith("_test.py"))
            and (vault / normalized_path).is_file()
        ):
            resolved.append(normalized_path)
    return dedupe_preserve_order(resolved)


def _generated_supporting_targets(vault: Path, targets: list[str]) -> list[str]:
    generated: list[str] = []
    for target in targets:
        normalized_target = normalize_repo_path_text(target)
        if normalized_target is None:
            continue
        if (
            normalized_target.startswith("ops/scripts/")
            and normalized_target.endswith(".py")
            and (vault / SCRIPT_OUTPUT_SURFACES_TARGET).is_file()
        ):
            generated.append(SCRIPT_OUTPUT_SURFACES_TARGET)
        if (
            normalized_target.startswith("ops/schemas/")
            and normalized_target.endswith(".schema.json")
            and (vault / REPORT_SCHEMA_SAMPLES_TARGET).is_file()
        ):
            generated.append(REPORT_SCHEMA_SAMPLES_TARGET)
    return dedupe_preserve_order(generated)


def generated_must_change_tests(vault: Path, targets: list[str]) -> list[str]:
    if not (vault / REPORT_SCHEMA_SAMPLE_REGENERATION_TEST).is_file():
        return []
    for target in targets:
        normalized_target = normalize_repo_path_text(target)
        if (
            normalized_target
            and normalized_target.startswith("ops/schemas/")
            and normalized_target.endswith(".schema.json")
        ):
            return [REPORT_SCHEMA_SAMPLE_REGENERATION_TEST]
    return []


def with_generated_supporting_targets(
    vault: Path,
    *,
    primary_targets: list[str],
    supporting_targets: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    generated_targets = _generated_supporting_targets(vault, [*primary_targets, *supporting_targets])
    for target in [*supporting_targets, *generated_targets]:
        if target in seen:
            continue
        seen.add(target)
        ordered.append(target)
    return ordered


def _same_eval_adjacent_supporting_targets(vault: Path, primary_targets: list[str]) -> list[str]:
    targets: list[str] = []
    for primary_target in primary_targets:
        targets.extend(SAME_EVAL_ADJACENT_SUPPORTING_TARGETS_BY_PRIMARY.get(primary_target, []))
    return current_repo_target_paths(vault, targets)


def _proposal_supporting_targets_for_failure_mode(
    vault: Path,
    *,
    failure_mode: str,
    primary_targets: list[str],
    supporting_targets: list[str],
) -> list[str]:
    if failure_mode == REPEATED_DISCARD_FAILURE_MODE:
        return []
    if failure_mode == REPEATED_SAME_EVAL_AFTER_PROMOTE_FAILURE_MODE:
        supporting_targets = [
            *supporting_targets,
            *_same_eval_adjacent_supporting_targets(vault, primary_targets),
        ]
    return with_generated_supporting_targets(
        vault,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
    )


def must_not_expand_apply_roots(
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


def proposal_blast_radius_score(
    candidate: dict,
    *,
    must_change_tests: list[str],
) -> int:
    score = 10
    distinct_targets = list(
        dict.fromkeys([*candidate["primary_targets"], *candidate["supporting_targets"]])
    )
    for path in distinct_targets:
        if path.startswith("ops/policies/"):
            score += 15
        elif path.startswith(("ops/schemas/", "system/")):
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


def proposal_why_now(candidate: dict, run_ids: list[str], blocked_by: list[str]) -> str:
    metrics = ", ".join(candidate["metrics_triggered"])
    message = (
        f"{candidate['family']} family에서 `{metrics}` 신호가 최근 {len(run_ids)}개 run 기준으로 누적돼 "
        "지금 한 번의 단일 mechanism 실험으로 국소화할 가치가 있다."
    )
    if blocked_by:
        message += " 다만 최근 chronology와 target overlap이 보여 우선순위는 한 단계 낮춘다."
    return message


def target_slug(primary_targets: list[str]) -> str:
    target_slug = "-".join(Path(target).stem for target in primary_targets)
    return re.sub(r"[^a-z0-9]+", "-", target_slug.lower()).strip("-")


def proposal_id(candidate: dict, failure_mode: str) -> str:
    slug = target_slug(candidate["primary_targets"])
    return f"{failure_mode}__{slug or candidate['candidate_id']}"


def proposal_metrics_triggered(candidate: dict, failure_mode: str) -> list[str]:
    metrics = [
        str(item).strip()
        for item in candidate.get("metrics_triggered", [])
        if str(item).strip()
    ]
    failure_mode_metrics = {
        REPEATED_DISCARD_FAILURE_MODE: [REPEATED_DISCARD_FAILURE_MODE],
        REPEATED_SAME_EVAL_AFTER_PROMOTE_FAILURE_MODE: [STAGE1_SAME_EVAL_METRIC],
    }.get(failure_mode)
    if failure_mode_metrics is None:
        return metrics
    selected = [metric for metric in failure_mode_metrics if metric in metrics]
    return selected or metrics


def proposal_run_ids(
    candidate: dict,
    failure_mode: str,
    *,
    lookback_runs: int,
) -> list[str]:
    all_run_ids = [
        str(run_id).strip()
        for run_id in candidate.get("run_ids", [])
        if str(run_id).strip()
    ]
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


def proposal_from_candidate(
    vault: Path,
    policy: dict,
    candidate: dict,
    *,
    remediation_backlog_report: dict,
    recent_log_sections: list[RecentLogSection],
    skipped_candidates: list[dict] | None = None,
) -> MutationProposal | None:
    allowed_failure_modes = set(policy["mutation_proposal"]["allowed_failure_modes"])
    primary_targets = current_repo_target_paths(vault, list(candidate["primary_targets"]))
    candidate_supporting_targets = current_repo_target_paths(vault, list(candidate["supporting_targets"]))
    current_candidate = {
        **candidate,
        "primary_targets": primary_targets,
        "supporting_targets": candidate_supporting_targets,
    }
    fields = proposal_fields_for_candidate(current_candidate, MECHANISM_CANDIDATE_REGISTRY)
    current_candidate, fields, closed_resolution_detail = _candidate_fields_after_closed_remediation(
        current_candidate,
        fields,
        remediation_backlog_report=remediation_backlog_report,
    )
    if fields["failure_mode"] not in allowed_failure_modes:
        return None
    if closed_resolution_detail and skipped_candidates is not None:
        skipped_candidates.append(
            {
                "candidate_id": candidate.get("candidate_id", "<unknown>"),
                "reason": "closed_remediation_backlog_resolution",
                "detail": closed_resolution_detail,
            }
        )
    if current_candidate.get("_closed_failure_mode_fallback") is True:
        supporting_targets = []
    else:
        supporting_targets = _proposal_supporting_targets_for_failure_mode(
            vault,
            failure_mode=fields["failure_mode"],
            primary_targets=primary_targets,
            supporting_targets=list(current_candidate["supporting_targets"]),
        )
    current_candidate = {
        **current_candidate,
        "supporting_targets": supporting_targets,
    }
    recent_log_matches = recent_log_overlap_matches(current_candidate, recent_log_sections)
    blocked_by = ["recent_log_overlap"] if recent_log_matches else []
    metrics_triggered = proposal_metrics_triggered(current_candidate, fields["failure_mode"])
    run_ids = proposal_run_ids(
        current_candidate,
        fields["failure_mode"],
        lookback_runs=policy["mutation_proposal"]["lookback_runs"],
    )
    proposal_priority_breakdown = priority_breakdown(current_candidate, blocked_by)
    must_change_tests = resolve_must_change_tests(
        vault,
        policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
    )

    candidate_proposal_id = proposal_id(current_candidate, fields["failure_mode"])
    return MutationProposal(
        proposal_id=candidate_proposal_id,
        source_candidate_id=candidate["candidate_id"],
        source_candidate_type=candidate["candidate_type"],
        family=candidate["family"],
        tier=candidate["tier"],
        priority=proposal_priority_breakdown.final_priority,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        metrics_triggered=metrics_triggered,
        run_ids=run_ids,
        failure_mode=fields["failure_mode"],
        single_mechanism_scope=fields["single_mechanism_scope"],
        change_hypothesis=fields["change_hypothesis"],
        expected_binary_signal=fields["expected_binary_signal"],
        blast_radius_score=proposal_blast_radius_score(
            current_candidate,
            must_change_tests=must_change_tests,
        ),
        must_change_tests=must_change_tests,
        must_change_budget_signal=must_change_budget_signal(fields),
        must_not_expand_apply_roots=must_not_expand_apply_roots(
            vault,
            policy,
            proposal_targets=[*primary_targets, *supporting_targets],
            must_change_tests=must_change_tests,
        ),
        must_not_increase_untyped_surface=True,
        required_artifacts=required_artifacts(),
        blocked_by=blocked_by,
        why_now=proposal_why_now(
            {**current_candidate, "metrics_triggered": metrics_triggered},
            run_ids,
            blocked_by,
        ),
        priority_breakdown=proposal_priority_breakdown,
        recent_log_overlap_matches=recent_log_matches,
    )
