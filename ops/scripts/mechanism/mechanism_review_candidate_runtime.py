from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .mechanism_candidate_registry_runtime import (
    BRANCH_GROWTH_CANDIDATE,
    EVAL_STAGNATION_CANDIDATE,
    HIGH_COMPLEXITY_CANDIDATE,
    MECHANISM_CANDIDATE_REGISTRY,
    POLICY_COMPLEXITY_GROWTH_CANDIDATE,
    SCHEMA_DRIFT_CANDIDATE,
    configured_mechanism_candidate_types,
    schema_changed_by_manifest,
    schema_changed_file_paths,
    trend_candidate_requirements,
)
from .mechanism_review_history_runtime import (
    MechanismRunSnapshot,
    group_snapshots_by_targets,
    load_optional_json,
)
from .mechanism_review_session_calibration_runtime import apply_session_calibration

JsonLoader = Callable[[Path], dict | None]


@dataclass(frozen=True)
class CandidateTemplateRequest:
    policy: dict
    candidate_type: str
    family: str
    primary_targets: list[str]
    supporting_targets: list[str]
    metrics_triggered: list[str]
    priority: int
    rationale: str
    suggested_experiments: list[str]
    run_ids: list[str]
    evidence: dict
    signal_run_ids: dict[str, list[str]] | None = None


@dataclass(frozen=True)
class _NonTriggerContext:
    thresholds: dict
    latest: MechanismRunSnapshot
    latest_baseline_metrics: dict
    latest_candidate_metrics: dict
    latest_candidate_flags: list[str]


__all__ = [
    "JsonLoader",
    "apply_historical_calibration",
    "bootstrap_diagnostics",
    "build_candidate_for_history",
    "build_candidates",
    "candidate_requirements_by_type",
    "candidate_slug",
    "candidate_template",
    "clamp_priority",
    "family_spec",
    "format_threshold_ratio",
    "historical_calibration_summary",
    "non_trigger_detail",
    "non_trigger_diagnostics",
    "sorted_run_ids",
    "trend_candidate_requirements_for_policy",
]


def sorted_run_ids(run_ids: list[str]) -> list[str]:
    return sorted(run_ids)


def candidate_slug(primary_targets: list[str]) -> str:
    text = "-".join(Path(target).stem for target in primary_targets)
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if slug:
        return slug
    digest = hashlib.sha1("|".join(primary_targets).encode("utf-8")).hexdigest()[:12]
    return digest


def clamp_priority(value: int) -> int:
    return max(0, min(100, value))


def family_spec(policy: dict, family: str) -> dict:
    return policy["mechanism_review"]["families"][family]


def candidate_template(
    *args: object,
    request: CandidateTemplateRequest | None = None,
    **kwargs: object,
) -> dict:
    request = _coerce_candidate_template_request(request=request, args=args, kwargs=kwargs)
    spec = family_spec(request.policy, request.family)
    candidate = {
        "candidate_id": f"{request.candidate_type}__{candidate_slug(request.primary_targets)}",
        "candidate_type": request.candidate_type,
        "family": request.family,
        "tier": spec["tier"],
        "objective": spec["objective"],
        "priority": clamp_priority(request.priority),
        "primary_targets": request.primary_targets,
        "supporting_targets": request.supporting_targets,
        "metrics_triggered": request.metrics_triggered,
        "run_ids": sorted_run_ids(request.run_ids),
        "evidence": request.evidence,
        "rationale": request.rationale,
        "suggested_experiments": request.suggested_experiments,
    }
    if request.signal_run_ids:
        candidate["signal_run_ids"] = {
            signal: sorted_run_ids(run_ids)
            for signal, run_ids in sorted(request.signal_run_ids.items())
            if run_ids
        }
    return candidate


def _coerce_candidate_template_request(
    *,
    request: CandidateTemplateRequest | None,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> CandidateTemplateRequest:
    if request is not None:
        if args or kwargs:
            raise TypeError("request cannot be combined with positional or keyword candidate fields")
        return request

    field_names = [
        "policy",
        "candidate_type",
        "family",
        "primary_targets",
        "supporting_targets",
        "metrics_triggered",
        "priority",
        "rationale",
        "suggested_experiments",
        "run_ids",
        "evidence",
    ]
    if len(args) > len(field_names):
        raise TypeError(f"expected at most {len(field_names)} positional arguments")
    values = dict(zip(field_names, args, strict=False))
    values.update(kwargs)
    missing = [name for name in field_names if name not in values]
    if missing:
        raise TypeError(f"missing candidate template fields: {', '.join(missing)}")
    return CandidateTemplateRequest(
        policy=cast(dict, values["policy"]),
        candidate_type=str(values["candidate_type"]),
        family=str(values["family"]),
        primary_targets=cast(list[str], values["primary_targets"]),
        supporting_targets=cast(list[str], values["supporting_targets"]),
        metrics_triggered=cast(list[str], values["metrics_triggered"]),
        priority=cast(int, values["priority"]),
        rationale=str(values["rationale"]),
        suggested_experiments=cast(list[str], values["suggested_experiments"]),
        run_ids=cast(list[str], values["run_ids"]),
        evidence=cast(dict, values["evidence"]),
        signal_run_ids=cast(dict[str, list[str]] | None, values.get("signal_run_ids")),
    )


def trend_candidate_requirements_for_policy(policy: dict) -> list[dict]:
    ordered_candidate_types = configured_mechanism_candidate_types(
        policy,
        MECHANISM_CANDIDATE_REGISTRY,
    )
    return trend_candidate_requirements(
        policy,
        ordered_candidate_types,
        MECHANISM_CANDIDATE_REGISTRY,
    )


def candidate_requirements_by_type(policy: dict) -> dict[str, dict]:
    ordered_candidate_types = configured_mechanism_candidate_types(
        policy,
        MECHANISM_CANDIDATE_REGISTRY,
    )
    return {
        item["candidate_type"]: item
        for item in trend_candidate_requirements(
            policy,
            ordered_candidate_types,
            MECHANISM_CANDIDATE_REGISTRY,
        )
    }


def format_threshold_ratio(current: int, required: int) -> str:
    return f"{current}/{required}"


def _non_trigger_context(policy: dict, snapshots: list[MechanismRunSnapshot]) -> _NonTriggerContext:
    latest = snapshots[-1]
    return _NonTriggerContext(
        thresholds=policy["mechanism_review"]["thresholds"],
        latest=latest,
        latest_baseline_metrics=latest.baseline_mechanism["structural_metrics"],
        latest_candidate_metrics=latest.candidate_mechanism["structural_metrics"],
        latest_candidate_flags=latest.candidate_mechanism["complexity_profile"]["risk_flags"],
    )


def _branch_growth_non_trigger_detail(
    context: _NonTriggerContext,
    snapshots: list[MechanismRunSnapshot],
) -> str:
    branch_growth_runs = 0
    no_test_growth_runs = 0
    for snapshot in snapshots:
        baseline_metrics = snapshot.baseline_mechanism["structural_metrics"]
        candidate_metrics = snapshot.candidate_mechanism["structural_metrics"]
        branch_delta = (
            candidate_metrics["python_branch_node_count"] - baseline_metrics["python_branch_node_count"]
        )
        test_delta = candidate_metrics["test_case_count"] - baseline_metrics["test_case_count"]
        if branch_delta >= context.thresholds["branch_growth_min_delta"]:
            branch_growth_runs += 1
            if test_delta < context.thresholds["test_growth_min_delta"]:
                no_test_growth_runs += 1
    latest_branch_delta = (
        context.latest_candidate_metrics["python_branch_node_count"]
        - context.latest_baseline_metrics["python_branch_node_count"]
    )
    latest_test_delta = (
        context.latest_candidate_metrics["test_case_count"]
        - context.latest_baseline_metrics["test_case_count"]
    )
    return (
        "not triggered: "
        f"branch_growth_without_test_growth_runs={format_threshold_ratio(no_test_growth_runs, context.thresholds['repeated_branch_growth_runs'])}; "
        f"branch_growth_runs={branch_growth_runs}; "
        f"latest_branch_delta={latest_branch_delta}; "
        f"latest_test_delta={latest_test_delta}"
    )


def _high_complexity_non_trigger_detail(
    context: _NonTriggerContext,
    _snapshots: list[MechanismRunSnapshot],
) -> str:
    latest_complexity = context.latest.candidate_mechanism["complexity_profile"]["complexity_score"]
    latest_branch_count = context.latest_candidate_metrics["python_branch_node_count"]
    latest_test_case_count = context.latest_candidate_metrics["test_case_count"]
    return (
        "not triggered: "
        f"latest_complexity={format_threshold_ratio(latest_complexity, context.thresholds['complexity_score_high'])}; "
        f"latest_branch_count={format_threshold_ratio(latest_branch_count, context.thresholds['branch_count_high'])}; "
        f"latest_test_case_count={latest_test_case_count}/<={context.thresholds['low_test_case_count']}"
    )


def _schema_drift_non_trigger_detail(
    context: _NonTriggerContext,
    snapshots: list[MechanismRunSnapshot],
) -> str:
    flagged_promotions = 0
    schema_change_runs = 0
    promoted_schema_change_runs = 0
    for snapshot in snapshots:
        baseline_metrics = snapshot.baseline_mechanism["structural_metrics"]
        candidate_metrics = snapshot.candidate_mechanism["structural_metrics"]
        test_delta = candidate_metrics["test_case_count"] - baseline_metrics["test_case_count"]
        if schema_changed_by_manifest(snapshot):
            schema_change_runs += 1
            if snapshot.decision == "PROMOTE":
                promoted_schema_change_runs += 1
                if test_delta < context.thresholds["test_growth_min_delta"]:
                    flagged_promotions += 1
    latest_test_delta = (
        context.latest_candidate_metrics["test_case_count"]
        - context.latest_baseline_metrics["test_case_count"]
    )
    return (
        "not triggered: "
        f"schema_change_without_test_growth_promotions={format_threshold_ratio(flagged_promotions, context.thresholds['repeated_schema_drift_runs'])}; "
        f"schema_change_runs={schema_change_runs}; "
        f"promoted_schema_change_runs={promoted_schema_change_runs}; "
        f"latest_schema_changed_files={json.dumps(schema_changed_file_paths(context.latest), ensure_ascii=False)}; "
        f"latest_schema_flags={json.dumps(context.latest_candidate_flags, ensure_ascii=False)}; "
        f"latest_test_delta={latest_test_delta}"
    )


def _policy_complexity_growth_non_trigger_detail(
    context: _NonTriggerContext,
    snapshots: list[MechanismRunSnapshot],
) -> str:
    policy_touch_runs = 0
    flagged_growth_runs = 0
    latest_eval_delta = context.latest.candidate_eval["total_score"] - context.latest.baseline_eval["total_score"]
    latest_nonempty_delta = (
        context.latest_candidate_metrics["nonempty_line_count_total"]
        - context.latest_baseline_metrics["nonempty_line_count_total"]
    )
    latest_complexity_delta = (
        context.latest.candidate_mechanism["complexity_profile"]["complexity_score"]
        - context.latest.baseline_mechanism["complexity_profile"]["complexity_score"]
    )
    latest_policy_targets = [
        path
        for path in [*context.latest.primary_targets, *context.latest.supporting_targets]
        if path.startswith("ops/policies/")
    ]
    for snapshot in snapshots:
        combined_targets = [*snapshot.primary_targets, *snapshot.supporting_targets]
        if not any(path.startswith("ops/policies/") for path in combined_targets):
            continue
        policy_touch_runs += 1
        baseline_metrics = snapshot.baseline_mechanism["structural_metrics"]
        candidate_metrics = snapshot.candidate_mechanism["structural_metrics"]
        baseline_complexity = snapshot.baseline_mechanism["complexity_profile"]["complexity_score"]
        candidate_complexity = snapshot.candidate_mechanism["complexity_profile"]["complexity_score"]
        eval_delta = snapshot.candidate_eval["total_score"] - snapshot.baseline_eval["total_score"]
        nonempty_delta = (
            candidate_metrics["nonempty_line_count_total"] - baseline_metrics["nonempty_line_count_total"]
        )
        complexity_delta = candidate_complexity - baseline_complexity
        nonempty_growth = nonempty_delta >= context.thresholds["policy_nonempty_growth_min_delta"]
        complexity_growth = (
            complexity_delta >= context.thresholds["policy_complexity_score_growth_min_delta"]
        )
        if eval_delta <= 0 and (nonempty_growth or complexity_growth):
            flagged_growth_runs += 1
    return (
        "not triggered: "
        f"policy_surface_growth_without_eval_gain_runs={format_threshold_ratio(flagged_growth_runs, context.thresholds['repeated_policy_growth_runs'])}; "
        f"policy_touch_runs={policy_touch_runs}; "
        f"latest_policy_targets={json.dumps(latest_policy_targets, ensure_ascii=False)}; "
        f"latest_eval_delta={latest_eval_delta}; "
        f"latest_nonempty_delta={latest_nonempty_delta}; "
        f"latest_complexity_delta={latest_complexity_delta}"
    )


def _eval_stagnation_non_trigger_detail(
    context: _NonTriggerContext,
    snapshots: list[MechanismRunSnapshot],
) -> str:
    recent = snapshots[-context.thresholds["stagnation_window"] :]
    same_eval_runs = sum(
        1
        for snapshot in recent
        if snapshot.candidate_eval["total_score"] == snapshot.baseline_eval["total_score"]
    )
    discard_runs = sum(1 for snapshot in recent if snapshot.decision == "DISCARD")
    return (
        "not triggered: "
        f"same_eval_runs={format_threshold_ratio(same_eval_runs, context.thresholds['repeated_same_eval_runs'])}; "
        f"discard_runs={format_threshold_ratio(discard_runs, context.thresholds['repeated_discard_runs'])}; "
        f"window_runs={len(recent)}/{context.thresholds['stagnation_window']}"
    )


_NON_TRIGGER_DETAIL_BUILDERS = {
    BRANCH_GROWTH_CANDIDATE: _branch_growth_non_trigger_detail,
    HIGH_COMPLEXITY_CANDIDATE: _high_complexity_non_trigger_detail,
    SCHEMA_DRIFT_CANDIDATE: _schema_drift_non_trigger_detail,
    POLICY_COMPLEXITY_GROWTH_CANDIDATE: _policy_complexity_growth_non_trigger_detail,
    EVAL_STAGNATION_CANDIDATE: _eval_stagnation_non_trigger_detail,
}


def non_trigger_detail(
    policy: dict,
    candidate_type: str,
    snapshots: list[MechanismRunSnapshot],
) -> str:
    builder = _NON_TRIGGER_DETAIL_BUILDERS.get(candidate_type)
    if builder is None:
        return "not triggered under current policy thresholds"
    return builder(_non_trigger_context(policy, snapshots), snapshots)


def non_trigger_diagnostics(
    policy: dict,
    snapshots: list[MechanismRunSnapshot],
    candidates: list[dict],
) -> list[dict]:
    if not snapshots or candidates:
        return []

    ordered_candidate_types = configured_mechanism_candidate_types(
        policy,
        MECHANISM_CANDIDATE_REGISTRY,
    )
    requirements_by_type = candidate_requirements_by_type(policy)
    grouped = group_snapshots_by_targets(snapshots)
    diagnostics: list[dict] = []

    for primary_targets, group_snapshots in sorted(grouped.items()):
        comparable_runs = len(group_snapshots)
        if any(
            comparable_runs < requirement["evaluation_min_runs"]
            for requirement in requirements_by_type.values()
        ):
            continue
        latest = group_snapshots[-1]
        candidate_diagnostics = [
            {
                "candidate_type": candidate_type,
                "detail": non_trigger_detail(policy, candidate_type, group_snapshots),
            }
            for candidate_type in ordered_candidate_types
            if build_candidate_for_history(
                policy,
                candidate_type,
                group_snapshots,
                requirements_by_type,
            )
            is None
        ]
        if candidate_diagnostics:
            diagnostics.append(
                {
                    "primary_targets": list(primary_targets),
                    "comparable_runs": comparable_runs,
                    "latest_run_id": latest.run_id,
                    "candidate_diagnostics": candidate_diagnostics,
                }
            )

    return diagnostics


def bootstrap_diagnostics(
    policy: dict,
    snapshots: list[MechanismRunSnapshot],
    candidates: list[dict],
) -> dict:
    requirements = trend_candidate_requirements_for_policy(policy)
    grouped = group_snapshots_by_targets(snapshots)
    diagnostics = non_trigger_diagnostics(policy, snapshots, candidates)

    if not snapshots:
        return {
            "status": "no_history",
            "summary": (
                "아직 유효한 system_mechanism run history가 없어 trend-based mechanism candidate를 계산할 수 없다."
            ),
            "recommended_next_step": (
                "capture the first finalized system_mechanism run with baseline/candidate eval, lint, mechanism assessment, and promotion report"
            ),
            "trend_candidate_requirements": requirements,
            "target_groups_under_min_history": [],
        }

    under_min_history: list[dict] = []
    any_group_trend_ready = not requirements
    for primary_targets, group_snapshots in sorted(grouped.items()):
        blocked: list[dict] = []
        comparable_runs = len(group_snapshots)
        for requirement in requirements:
            required_runs = requirement["evaluation_min_runs"]
            if comparable_runs < required_runs:
                blocked.append(
                    {
                        "candidate_type": requirement["candidate_type"],
                        "required_runs": required_runs,
                        "additional_runs_needed": required_runs - comparable_runs,
                    }
                )
        if blocked:
            under_min_history.append(
                {
                    "primary_targets": list(primary_targets),
                    "comparable_runs": comparable_runs,
                    "latest_run_id": group_snapshots[-1].run_id,
                    "blocked_candidate_types": blocked,
                }
            )
        else:
            any_group_trend_ready = True

    if not any_group_trend_ready:
        summary = (
            "현재 target group들은 comparable mechanism run history가 아직 부족해 trend-based candidate 평가 창이 열리지 않았다."
        )
        if candidates:
            summary = (
                "single-run signal candidate는 생성됐지만, trend-based candidate를 평가하기에는 comparable mechanism run history가 아직 부족하다."
            )
        return {
            "status": "bootstrap_history_insufficient",
            "summary": summary,
            "recommended_next_step": (
                "run one or more additional comparable system_mechanism experiments on the same primary target set to unlock trend-based review candidates"
            ),
            "trend_candidate_requirements": requirements,
            "target_groups_under_min_history": under_min_history,
        }

    summary = "comparable mechanism run history는 trend-based candidate를 평가할 수 있을 만큼 확보됐다."
    if not candidates:
        summary = (
            "comparable mechanism run history는 충분하지만, 현재 threshold를 넘는 mechanism review candidate는 없다."
        )
    return {
        "status": "ready",
        "summary": summary,
        "recommended_next_step": (
            "review current candidates if present; otherwise continue narrow one-mechanism experiments or inspect skipped runs for missing signal"
        ),
        "trend_candidate_requirements": requirements,
        "target_groups_under_min_history": under_min_history,
        "non_trigger_diagnostics": diagnostics,
    }


def build_candidate_for_history(
    policy: dict,
    candidate_type: str,
    snapshots: list[MechanismRunSnapshot],
    requirements_by_type: dict[str, dict],
) -> dict | None:
    requirement = requirements_by_type.get(candidate_type)
    if requirement is not None and len(snapshots) < requirement["evaluation_min_runs"]:
        return None
    return MECHANISM_CANDIDATE_REGISTRY[candidate_type].build_candidate(
        policy,
        snapshots,
        candidate_template,
    )


def historical_calibration_summary(
    policy: dict,
    candidate: dict,
    group_snapshots: list[MechanismRunSnapshot],
    requirements_by_type: dict[str, dict],
) -> dict:
    calibration_policy = policy["mechanism_review"]["calibration"]
    lookback_runs = calibration_policy["lookback_runs"]
    unstable_followup_window = calibration_policy["unstable_followup_window"]
    adjustments = calibration_policy["priority_adjustments"]

    history_snapshots = group_snapshots[-lookback_runs:]
    historical_promote_count = 0
    promoted_then_regressed_count = 0
    repeated_same_eval_after_promote_count = 0
    durable_promote_count = 0

    for index in range(max(0, len(history_snapshots) - 1)):
        prefix = history_snapshots[: index + 1]
        historical_candidate = build_candidate_for_history(
            policy,
            candidate["candidate_type"],
            prefix,
            requirements_by_type,
        )
        if historical_candidate is None:
            continue
        if historical_candidate["family"] != candidate["family"]:
            continue
        if prefix[-1].decision != "PROMOTE":
            continue

        historical_promote_count += 1
        followups = history_snapshots[index + 1 : index + 1 + unstable_followup_window]
        if not followups:
            continue

        if followups[0].decision == "DISCARD":
            promoted_then_regressed_count += 1

        same_eval_after_promote = any(
            snapshot.candidate_eval["total_score"] == snapshot.baseline_eval["total_score"]
            for snapshot in followups
        )
        if same_eval_after_promote:
            repeated_same_eval_after_promote_count += 1

        if (
            len(followups) == unstable_followup_window
            and followups[0].decision != "DISCARD"
            and not same_eval_after_promote
        ):
            durable_promote_count += 1

    priority_before = int(candidate["priority"])
    requested_priority_delta = (
        adjustments["promoted_then_regressed"] * promoted_then_regressed_count
        + adjustments["repeated_same_eval_after_promote"] * repeated_same_eval_after_promote_count
        + adjustments["durable_promote"] * durable_promote_count
    )
    priority_after = clamp_priority(priority_before + requested_priority_delta)
    priority_delta = priority_after - priority_before
    return {
        "lookback_runs": lookback_runs,
        "history_window_runs": len(history_snapshots),
        "unstable_followup_window": unstable_followup_window,
        "historical_promote_count": historical_promote_count,
        "promoted_then_regressed_count": promoted_then_regressed_count,
        "repeated_same_eval_after_promote_count": repeated_same_eval_after_promote_count,
        "durable_promote_count": durable_promote_count,
        "priority_before_calibration": priority_before,
        "priority_delta": priority_delta,
        "priority_after_calibration": priority_after,
    }


def apply_historical_calibration(
    policy: dict,
    candidate: dict,
    group_snapshots: list[MechanismRunSnapshot],
    requirements_by_type: dict[str, dict],
) -> dict:
    calibration_policy = policy["mechanism_review"]["calibration"]
    if not calibration_policy["enabled"]:
        return candidate

    calibrated = dict(candidate)
    summary = historical_calibration_summary(
        policy,
        candidate,
        group_snapshots,
        requirements_by_type,
    )
    calibrated["priority"] = summary["priority_after_calibration"]
    calibrated["historical_calibration"] = summary
    return calibrated


def build_candidates(
    vault: Path,
    policy: dict,
    snapshots: list[MechanismRunSnapshot],
    *,
    load_optional_json_func: JsonLoader = load_optional_json,
) -> list[dict]:
    ordered_candidate_types = configured_mechanism_candidate_types(
        policy,
        MECHANISM_CANDIDATE_REGISTRY,
    )
    requirements_by_type = {
        item["candidate_type"]: item
        for item in trend_candidate_requirements(
            policy,
            ordered_candidate_types,
            MECHANISM_CANDIDATE_REGISTRY,
        )
    }
    grouped = group_snapshots_by_targets(snapshots)
    candidates: list[dict] = []
    session_report_cache: dict[str, dict | None] = {}
    run_session_cache: dict[str, tuple[str, dict | None]] = {}
    for group_snapshots in grouped.values():
        for candidate_type in ordered_candidate_types:
            candidate = build_candidate_for_history(
                policy,
                candidate_type,
                group_snapshots,
                requirements_by_type,
            )
            if candidate is not None:
                calibrated_candidate = apply_historical_calibration(
                    policy,
                    candidate,
                    group_snapshots,
                    requirements_by_type,
                )
                candidates.append(
                    apply_session_calibration(
                        vault,
                        policy,
                        calibrated_candidate,
                        session_report_cache,
                        run_session_cache,
                        load_optional_json_func=load_optional_json_func,
                    )
                )

    candidates.sort(key=lambda item: (-item["priority"], item["candidate_id"]))
    max_candidates = policy["mechanism_review"]["max_candidates"]
    return candidates[:max_candidates]
