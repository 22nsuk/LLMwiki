from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


MechanismCandidateTemplate = Callable[..., dict]
MechanismCandidateBuilder = Callable[[dict, list[Any], MechanismCandidateTemplate], dict | None]
MechanismProposalFieldsBuilder = Callable[[dict], dict]
TrendRequirementBuilder = Callable[[dict], dict]

BRANCH_GROWTH_CANDIDATE = "mechanism_branch_growth_without_test_growth_candidate"
HIGH_COMPLEXITY_CANDIDATE = "mechanism_high_complexity_low_test_pressure_candidate"
SCHEMA_DRIFT_CANDIDATE = "mechanism_schema_drift_candidate"
POLICY_COMPLEXITY_GROWTH_CANDIDATE = "mechanism_policy_complexity_growth_candidate"
EVAL_STAGNATION_CANDIDATE = "mechanism_eval_stagnation_candidate"


@dataclass(frozen=True)
class MechanismCandidateSpec:
    candidate_type: str
    build_candidate: MechanismCandidateBuilder
    build_proposal_fields: MechanismProposalFieldsBuilder
    trend_requirement: TrendRequirementBuilder | None = None


@dataclass(frozen=True)
class PolicyComplexityRunSignal:
    run_id: str
    policy_targets: list[str]
    eval_delta: int
    nonempty_delta: int
    complexity_delta: int
    nonempty_growth: bool
    complexity_growth: bool
    pruning_positive_signal: bool


def configured_mechanism_candidate_types(
    policy: dict,
    registry: dict[str, MechanismCandidateSpec],
) -> list[str]:
    configured = policy["mechanism_review"]["candidate_types"]
    if not isinstance(configured, list) or not configured:
        raise ValueError("mechanism_review.candidate_types must be a non-empty list")

    ordered: list[str] = []
    seen: set[str] = set()
    for raw_candidate_type in configured:
        if not isinstance(raw_candidate_type, str) or not raw_candidate_type.strip():
            raise ValueError("mechanism_review.candidate_types contains an invalid candidate type")
        candidate_type = raw_candidate_type.strip()
        if candidate_type in seen:
            continue
        if candidate_type not in registry:
            raise ValueError(
                "mechanism review candidate registry references unknown candidate type: "
                f"{candidate_type}"
            )
        seen.add(candidate_type)
        ordered.append(candidate_type)
    return ordered


def trend_candidate_requirements(
    policy: dict,
    ordered_candidate_types: list[str],
    registry: dict[str, MechanismCandidateSpec],
) -> list[dict]:
    requirements: list[dict] = []
    for candidate_type in ordered_candidate_types:
        spec = registry[candidate_type]
        if spec.trend_requirement is None:
            continue
        requirements.append(spec.trend_requirement(policy))
    return requirements


def proposal_fields_for_candidate(
    candidate: dict,
    registry: dict[str, MechanismCandidateSpec],
) -> dict:
    candidate_type = candidate["candidate_type"]
    spec = registry.get(candidate_type)
    if spec is None:
        raise ValueError(f"unsupported mechanism review candidate type: {candidate_type}")
    return spec.build_proposal_fields(candidate)


def _branch_growth_requirement(policy: dict) -> dict:
    thresholds = policy["mechanism_review"]["thresholds"]
    return {
        "candidate_type": BRANCH_GROWTH_CANDIDATE,
        "evaluation_min_runs": thresholds["repeated_branch_growth_runs"],
        "full_window_runs": thresholds["repeated_branch_growth_runs"],
    }


def _eval_stagnation_requirement(policy: dict) -> dict:
    thresholds = policy["mechanism_review"]["thresholds"]
    return {
        "candidate_type": EVAL_STAGNATION_CANDIDATE,
        "evaluation_min_runs": thresholds["repeated_discard_runs"],
        "full_window_runs": thresholds["stagnation_window"],
    }


def _schema_drift_requirement(policy: dict) -> dict:
    thresholds = policy["mechanism_review"]["thresholds"]
    return {
        "candidate_type": SCHEMA_DRIFT_CANDIDATE,
        "evaluation_min_runs": thresholds["repeated_schema_drift_runs"],
        "full_window_runs": thresholds["repeated_schema_drift_runs"],
    }


def _policy_complexity_growth_requirement(policy: dict) -> dict:
    thresholds = policy["mechanism_review"]["thresholds"]
    return {
        "candidate_type": POLICY_COMPLEXITY_GROWTH_CANDIDATE,
        "evaluation_min_runs": thresholds["repeated_policy_growth_runs"],
        "full_window_runs": thresholds["repeated_policy_growth_runs"],
    }


def _branch_growth_candidate(
    policy: dict,
    snapshots: list[Any],
    candidate_template: MechanismCandidateTemplate,
) -> dict | None:
    thresholds = policy["mechanism_review"]["thresholds"]
    latest = snapshots[-1]
    branch_growth_runs = 0
    no_test_growth_runs = 0
    verbosity_growth_runs = 0
    for snapshot in snapshots:
        baseline_metrics = snapshot.baseline_mechanism["structural_metrics"]
        candidate_metrics = snapshot.candidate_mechanism["structural_metrics"]
        branch_delta = candidate_metrics["python_branch_node_count"] - baseline_metrics["python_branch_node_count"]
        test_delta = candidate_metrics["test_case_count"] - baseline_metrics["test_case_count"]
        line_delta = candidate_metrics["nonempty_line_count_total"] - baseline_metrics["nonempty_line_count_total"]
        if branch_delta >= thresholds["branch_growth_min_delta"]:
            branch_growth_runs += 1
            if test_delta < thresholds["test_growth_min_delta"]:
                no_test_growth_runs += 1
        if line_delta > 0:
            verbosity_growth_runs += 1

    if no_test_growth_runs < thresholds["repeated_branch_growth_runs"]:
        return None

    latest_metrics = latest.candidate_mechanism["structural_metrics"]
    metrics_triggered = ["branch_growth_without_test_growth"]
    if verbosity_growth_runs:
        metrics_triggered.append("verbosity_growth")

    priority = 40
    if no_test_growth_runs >= thresholds["repeated_branch_growth_runs"] + 1:
        priority += 20
    if verbosity_growth_runs >= thresholds["repeated_branch_growth_runs"]:
        priority += 10
    if latest_metrics["python_branch_node_count"] >= thresholds["branch_count_high"]:
        priority += 10

    return candidate_template(
        policy,
        candidate_type=BRANCH_GROWTH_CANDIDATE,
        family="self_mod_stability",
        primary_targets=latest.primary_targets,
        supporting_targets=latest.supporting_targets,
        metrics_triggered=metrics_triggered,
        priority=priority,
        rationale=(
            f"최근 {len(snapshots)}개 comparable mechanism run에서 branch count 증가가 반복됐는데 "
            "test case growth는 따라오지 않았다."
        ),
        suggested_experiments=[
            f"add focused regression tests for {latest.primary_targets[0]}",
            f"split dense decision logic in {latest.primary_targets[0]}",
        ],
        run_ids=[snapshot.run_id for snapshot in snapshots],
        evidence={
            "runs_examined": len(snapshots),
            "branch_growth_runs": branch_growth_runs,
            "branch_growth_without_test_growth_runs": no_test_growth_runs,
            "verbosity_growth_runs": verbosity_growth_runs,
            "latest_candidate_branch_count": latest_metrics["python_branch_node_count"],
            "latest_candidate_test_case_count": latest_metrics["test_case_count"],
        },
    )


def _high_complexity_candidate(
    policy: dict,
    snapshots: list[Any],
    candidate_template: MechanismCandidateTemplate,
) -> dict | None:
    thresholds = policy["mechanism_review"]["thresholds"]
    latest = snapshots[-1]
    latest_metrics = latest.candidate_mechanism["structural_metrics"]
    latest_complexity = latest.candidate_mechanism["complexity_profile"]["complexity_score"]
    if (
        latest_complexity < thresholds["complexity_score_high"]
        or latest_metrics["python_branch_node_count"] < thresholds["branch_count_high"]
        or latest_metrics["test_case_count"] > thresholds["low_test_case_count"]
    ):
        return None

    priority = 35
    if latest_complexity >= thresholds["complexity_score_high"] + 10:
        priority += 10
    if latest_metrics["python_branch_node_count"] >= thresholds["branch_count_high"] + 10:
        priority += 10

    return candidate_template(
        policy,
        candidate_type=HIGH_COMPLEXITY_CANDIDATE,
        family="self_mod_stability",
        primary_targets=latest.primary_targets,
        supporting_targets=latest.supporting_targets,
        metrics_triggered=["high_complexity_low_test_pressure"],
        priority=priority,
        rationale=(
            "latest mechanism assessment에서 complexity score와 branch pressure는 높은데 "
            "test case count는 낮은 상태로 남아 있다."
        ),
        suggested_experiments=[
            f"increase mechanism-specific test coverage for {latest.primary_targets[0]}",
            f"extract pure decision helper from {latest.primary_targets[0]}",
        ],
        run_ids=[latest.run_id],
        evidence={
            "runs_examined": 1,
            "latest_complexity_score": latest_complexity,
            "latest_candidate_branch_count": latest_metrics["python_branch_node_count"],
            "latest_candidate_test_case_count": latest_metrics["test_case_count"],
        },
    )


def _snapshot_risk_flags(snapshot: Any) -> list[str]:
    flags = snapshot.candidate_mechanism["complexity_profile"].get("risk_flags", [])
    return [flag for flag in flags if isinstance(flag, str)]


def _changed_manifest_file_entries(snapshot: Any) -> list[dict] | None:
    manifest = getattr(snapshot, "changed_files_manifest", {})
    if not isinstance(manifest, dict):
        return None
    files = manifest.get("files")
    if not isinstance(files, list):
        return None
    return [item for item in files if isinstance(item, dict)]


def _schema_file_path(path: str) -> bool:
    return path.startswith("ops/schemas/") or path.endswith(".schema.json")


def schema_changed_by_manifest(snapshot: Any) -> bool:
    if _changed_manifest_file_entries(snapshot) is None:
        return "schema_change" in _snapshot_risk_flags(snapshot)
    return bool(schema_changed_file_paths(snapshot))


def schema_changed_file_paths(snapshot: Any) -> list[str]:
    file_entries = _changed_manifest_file_entries(snapshot)
    if file_entries is None:
        return []
    return sorted(
        {
            path
            for item in file_entries
            if isinstance(path := item.get("path"), str) and _schema_file_path(path)
        }
    )


def _schema_drift_candidate(
    policy: dict,
    snapshots: list[Any],
    candidate_template: MechanismCandidateTemplate,
) -> dict | None:
    thresholds = policy["mechanism_review"]["thresholds"]
    latest = snapshots[-1]
    flagged_promotions = 0
    schema_change_runs = 0
    promoted_schema_change_runs = 0
    run_ids: list[str] = []
    for snapshot in snapshots:
        baseline_metrics = snapshot.baseline_mechanism["structural_metrics"]
        candidate_metrics = snapshot.candidate_mechanism["structural_metrics"]
        test_delta = candidate_metrics["test_case_count"] - baseline_metrics["test_case_count"]
        if schema_changed_by_manifest(snapshot):
            schema_change_runs += 1
            if snapshot.decision == "PROMOTE":
                promoted_schema_change_runs += 1
                if test_delta < thresholds["test_growth_min_delta"]:
                    flagged_promotions += 1
                    run_ids.append(snapshot.run_id)

    if flagged_promotions < thresholds["repeated_schema_drift_runs"]:
        return None

    latest_baseline_metrics = latest.baseline_mechanism["structural_metrics"]
    latest_candidate_metrics = latest.candidate_mechanism["structural_metrics"]
    latest_test_delta = (
        latest_candidate_metrics["test_case_count"] - latest_baseline_metrics["test_case_count"]
    )
    latest_schema_change = schema_changed_by_manifest(latest)
    latest_schema_change_without_test_growth = (
        latest_schema_change and latest_test_delta < thresholds["test_growth_min_delta"]
    )

    priority = 55
    if flagged_promotions >= thresholds["repeated_schema_drift_runs"] + 1:
        priority += 10
    if latest_schema_change_without_test_growth:
        priority += 10
    if latest_schema_change_without_test_growth and latest.decision == "PROMOTE":
        priority += 5

    metrics_triggered = [
        "schema_change_without_test_growth",
        "promoted_schema_change_without_guardrails",
    ]
    if latest_schema_change_without_test_growth:
        metrics_triggered.append("latest_schema_change_still_uncovered")

    return candidate_template(
        policy,
        candidate_type=SCHEMA_DRIFT_CANDIDATE,
        family="schema_drift",
        primary_targets=latest.primary_targets,
        supporting_targets=latest.supporting_targets,
        metrics_triggered=metrics_triggered,
        priority=priority,
        rationale=(
            f"최근 {len(snapshots)}개 comparable mechanism run 중 schema_change가 test growth 없이 "
            "PROMOTE된 패턴이 반복돼 schema contract guardrail이 느슨할 가능성이 있다."
        ),
        suggested_experiments=[
            f"add schema-focused regression coverage for {latest.primary_targets[0]}",
            f"require explicit schema guardrail evidence before promoting changes in {latest.primary_targets[0]}",
        ],
        run_ids=run_ids,
        evidence={
            "runs_examined": len(snapshots),
            "schema_change_runs": schema_change_runs,
            "promoted_schema_change_runs": promoted_schema_change_runs,
            "schema_change_without_test_growth_promotions": flagged_promotions,
            "latest_schema_change": latest_schema_change,
            "latest_schema_change_without_test_growth": latest_schema_change_without_test_growth,
            "latest_candidate_test_case_count": latest_candidate_metrics["test_case_count"],
        },
    )


def _policy_targets(paths: list[str]) -> list[str]:
    return [path for path in paths if path.startswith("ops/policies/")]


def _preferred_policy_target(primary_targets: list[str], supporting_targets: list[str]) -> str:
    policy_targets = _policy_targets([*primary_targets, *supporting_targets])
    if policy_targets:
        return policy_targets[0]
    return primary_targets[0]


def _policy_complexity_run_signal(
    snapshot: Any,
    thresholds: dict,
) -> PolicyComplexityRunSignal:
    baseline_metrics = snapshot.baseline_mechanism["structural_metrics"]
    candidate_metrics = snapshot.candidate_mechanism["structural_metrics"]
    baseline_complexity = snapshot.baseline_mechanism["complexity_profile"]["complexity_score"]
    candidate_complexity = snapshot.candidate_mechanism["complexity_profile"]["complexity_score"]
    eval_delta = snapshot.candidate_eval["total_score"] - snapshot.baseline_eval["total_score"]
    nonempty_delta = (
        candidate_metrics["nonempty_line_count_total"]
        - baseline_metrics["nonempty_line_count_total"]
    )
    complexity_delta = candidate_complexity - baseline_complexity
    nonempty_growth = nonempty_delta >= thresholds["policy_nonempty_growth_min_delta"]
    complexity_growth = complexity_delta >= thresholds["policy_complexity_score_growth_min_delta"]
    nonempty_pruning = nonempty_delta <= -thresholds["policy_nonempty_growth_min_delta"]
    complexity_pruning = (
        complexity_delta <= -thresholds["policy_complexity_score_growth_min_delta"]
    )
    return PolicyComplexityRunSignal(
        run_id=snapshot.run_id,
        policy_targets=_policy_targets([*snapshot.primary_targets, *snapshot.supporting_targets]),
        eval_delta=eval_delta,
        nonempty_delta=nonempty_delta,
        complexity_delta=complexity_delta,
        nonempty_growth=nonempty_growth,
        complexity_growth=complexity_growth,
        pruning_positive_signal=eval_delta >= 0 and (nonempty_pruning or complexity_pruning),
    )


def _policy_complexity_run_signals(
    snapshots: list[Any],
    thresholds: dict,
) -> list[PolicyComplexityRunSignal]:
    return [_policy_complexity_run_signal(snapshot, thresholds) for snapshot in snapshots]


def _policy_complexity_growth_candidate(
    policy: dict,
    snapshots: list[Any],
    candidate_template: MechanismCandidateTemplate,
) -> dict | None:
    thresholds = policy["mechanism_review"]["thresholds"]
    latest = snapshots[-1]
    signals = _policy_complexity_run_signals(snapshots, thresholds)
    policy_signals = [signal for signal in signals if signal.policy_targets]
    growth_signals = [
        signal
        for signal in policy_signals
        if signal.eval_delta <= 0 and (signal.nonempty_growth or signal.complexity_growth)
    ]
    pruning_signals = [signal for signal in policy_signals if signal.pruning_positive_signal]
    policy_targets_seen = {
        target
        for signal in policy_signals
        for target in signal.policy_targets
    }
    latest_signal = signals[-1]
    flagged_growth_runs = len(growth_signals)

    if flagged_growth_runs < thresholds["repeated_policy_growth_runs"]:
        return None

    preferred_target = _preferred_policy_target(latest.primary_targets, latest.supporting_targets)

    priority = 45
    if flagged_growth_runs >= thresholds["repeated_policy_growth_runs"] + 1:
        priority += 10
    if latest_signal.eval_delta <= 0 and (
        latest_signal.nonempty_growth or latest_signal.complexity_growth
    ):
        priority += 10
    if latest_signal.nonempty_growth and latest_signal.complexity_growth:
        priority += 5
    policy_pruning_priority_credit = min(
        15,
        len(pruning_signals) * 5,
    )
    priority -= policy_pruning_priority_credit

    metrics_triggered = ["policy_surface_growth_without_eval_gain"]
    if latest_signal.complexity_growth:
        metrics_triggered.append("policy_complexity_score_growth")
    if latest_signal.nonempty_growth:
        metrics_triggered.append("policy_nonempty_growth")
    if latest_signal.pruning_positive_signal:
        metrics_triggered.append("policy_pruning_positive_signal")

    return candidate_template(
        policy,
        candidate_type=POLICY_COMPLEXITY_GROWTH_CANDIDATE,
        family="policy_complexity_growth",
        primary_targets=latest.primary_targets,
        supporting_targets=latest.supporting_targets,
        metrics_triggered=metrics_triggered,
        priority=priority,
        rationale=(
            f"최근 {len(snapshots)}개 comparable mechanism run에서 policy surface {preferred_target} "
            "변경이 complexity growth로 이어졌지만 eval gain은 만들지 못했다."
        ),
        suggested_experiments=[
            f"shrink the next policy change in {preferred_target} to one rule or threshold and pair it with direct regression coverage",
            f"move one policy-sensitive branch in {preferred_target} behind an explicit contract-oriented test case",
        ],
        run_ids=[signal.run_id for signal in growth_signals],
        evidence={
            "runs_examined": len(snapshots),
            "policy_touch_runs": len(policy_signals),
            "policy_surface_growth_without_eval_gain_runs": flagged_growth_runs,
            "policy_complexity_growth_runs": sum(
                signal.complexity_growth for signal in policy_signals
            ),
            "policy_nonempty_growth_runs": sum(
                signal.nonempty_growth for signal in policy_signals
            ),
            "policy_pruning_positive_signal_runs": len(pruning_signals),
            "policy_pruning_positive_signal_run_ids": ", ".join(
                signal.run_id for signal in pruning_signals
            ),
            "latest_policy_pruning_positive_signal": latest_signal.pruning_positive_signal,
            "policy_pruning_priority_credit": policy_pruning_priority_credit,
            "policy_target_count": len(policy_targets_seen),
            "policy_targets_summary": ", ".join(sorted(policy_targets_seen)),
            "latest_eval_score_delta": latest_signal.eval_delta,
            "latest_nonempty_delta": latest_signal.nonempty_delta,
            "latest_complexity_score_delta": latest_signal.complexity_delta,
        },
    )


def _eval_stagnation_candidate(
    policy: dict,
    snapshots: list[Any],
    candidate_template: MechanismCandidateTemplate,
) -> dict | None:
    thresholds = policy["mechanism_review"]["thresholds"]
    window = thresholds["stagnation_window"]
    recent = snapshots[-window:]
    latest = recent[-1]
    same_eval_runs = sum(
        1
        for snapshot in recent
        if snapshot.candidate_eval["total_score"] == snapshot.baseline_eval["total_score"]
    )
    discard_runs = sum(1 for snapshot in recent if snapshot.decision == "DISCARD")
    same_eval_run_ids = [
        snapshot.run_id
        for snapshot in recent
        if snapshot.candidate_eval["total_score"] == snapshot.baseline_eval["total_score"]
    ]
    discard_run_ids = [snapshot.run_id for snapshot in recent if snapshot.decision == "DISCARD"]
    if (
        same_eval_runs < thresholds["repeated_same_eval_runs"]
        and discard_runs < thresholds["repeated_discard_runs"]
    ):
        return None

    metrics_triggered: list[str] = []
    if same_eval_runs >= thresholds["repeated_same_eval_runs"]:
        metrics_triggered.append("stage1_same_eval_rate")
    if discard_runs >= thresholds["repeated_discard_runs"]:
        metrics_triggered.append("repeated_discard_runs")

    priority = 50
    if same_eval_runs >= thresholds["repeated_same_eval_runs"] + 1:
        priority += 20
    if discard_runs >= thresholds["repeated_discard_runs"]:
        priority += 10

    return candidate_template(
        policy,
        candidate_type=EVAL_STAGNATION_CANDIDATE,
        family="contract_regression_signals",
        primary_targets=latest.primary_targets,
        supporting_targets=latest.supporting_targets,
        metrics_triggered=metrics_triggered,
        priority=priority,
        rationale=(
            f"최근 {len(recent)}개 mechanism run에서 eval non-improvement 또는 DISCARD가 반복돼 "
            "다음 실험 scope를 더 좁히거나 failure mode를 재국소화할 필요가 있다."
        ),
        suggested_experiments=[
            f"try one mechanism-only experiment on {latest.primary_targets[0]}",
            f"reduce experiment scope and isolate one failure mode in {latest.primary_targets[0]}",
        ],
        run_ids=[snapshot.run_id for snapshot in recent],
        signal_run_ids={
            "repeated_same_eval_after_promote": same_eval_run_ids,
            "repeated_discard_runs": discard_run_ids,
        },
        evidence={
            "runs_examined": len(recent),
            "same_eval_runs": same_eval_runs,
            "discard_runs": discard_runs,
            "latest_baseline_eval_score": latest.baseline_eval["total_score"],
            "latest_candidate_eval_score": latest.candidate_eval["total_score"],
        },
    )


def _branch_growth_proposal_fields(candidate: dict) -> dict:
    primary_target = candidate["primary_targets"][0]
    return {
        "failure_mode": "branch_growth_without_test_growth",
        "single_mechanism_scope": (
            f"split one dense decision path in {primary_target} and pair it with focused regression coverage"
        ),
        "change_hypothesis": (
            f"If one dense decision path in {primary_target} is extracted and paired with target-specific tests, "
            "branch growth pressure can stop increasing without giving back current eval performance."
        ),
        "expected_binary_signal": (
            "tests_non_regression=true and test_case_count increases while branch pressure stays flat or decreases"
        ),
    }


def _high_complexity_proposal_fields(candidate: dict) -> dict:
    primary_target = candidate["primary_targets"][0]
    return {
        "failure_mode": "high_complexity_low_test_pressure",
        "single_mechanism_scope": (
            f"increase target-specific mechanism test coverage for {primary_target} without changing policy semantics"
        ),
        "change_hypothesis": (
            f"If test coverage grows around the current high-complexity path in {primary_target}, "
            "future same-eval or discard loops become easier to localize and shrink."
        ),
        "expected_binary_signal": (
            "test_case_count increases while complexity score and branch count do not increase"
        ),
    }


def _schema_drift_proposal_fields(candidate: dict) -> dict:
    primary_target = candidate["primary_targets"][0]
    return {
        "failure_mode": "schema_change_without_test_guardrails",
        "single_mechanism_scope": (
            f"add schema-specific guardrail tests around {primary_target} before the next schema-touching promotion"
        ),
        "change_hypothesis": (
            f"If schema-touching changes in {primary_target} are paired with explicit regression coverage and promotion guardrails, "
            "future schema promotions are less likely to ship with unobserved contract drift."
        ),
        "expected_binary_signal": (
            "schema_change candidates promote only when targeted test coverage or schema guardrail evidence increases"
        ),
    }


def _policy_complexity_growth_proposal_fields(candidate: dict) -> dict:
    policy_target = _preferred_policy_target(
        candidate["primary_targets"],
        candidate["supporting_targets"],
    )
    return {
        "failure_mode": "policy_surface_growth_without_eval_gain",
        "single_mechanism_scope": (
            f"narrow the next policy-layer experiment in {policy_target} to one rule or threshold and pair it with direct contract coverage"
        ),
        "change_hypothesis": (
            f"If the next policy-touching change in {policy_target} is reduced to one explicit rule surface and backed by direct regression coverage, "
            "mechanism complexity can stop growing without sacrificing current eval performance."
        ),
        "expected_binary_signal": (
            "candidate_eval > baseline_eval or equal-score promotion with lower policy-touched complexity and nonempty-line growth"
        ),
    }


def _eval_stagnation_proposal_fields(candidate: dict) -> dict:
    primary_target = candidate["primary_targets"][0]
    metrics_triggered = {str(item).strip() for item in candidate.get("metrics_triggered", [])}
    if "repeated_discard_runs" in metrics_triggered:
        return {
            "failure_mode": "repeated_discard_runs",
            "single_mechanism_scope": (
                f"narrow the next mechanism experiment on {primary_target} to the DISCARD outcome path only"
            ),
            "change_hypothesis": (
                f"If the next experiment around {primary_target} changes only one DISCARD-producing path "
                "and records explicit non-regression evidence, recent discard/rework pressure should drop "
                "without expanding the mechanism surface."
            ),
            "expected_binary_signal": (
                "next finalized attempt for this target avoids DISCARD while candidate_eval non-regresses "
                "and promotion artifacts explain the terminal decision"
            ),
        }
    if "stage1_same_eval_rate" in metrics_triggered:
        return {
            "failure_mode": "repeated_same_eval_after_promote",
            "single_mechanism_scope": (
                f"narrow the next mechanism experiment on {primary_target} to same-eval secondary evidence only"
            ),
            "change_hypothesis": (
                f"If the next experiment around {primary_target} changes only one same-eval evidence path, "
                "equal-score promotions should either show a strict secondary improvement or be rejected earlier."
            ),
            "expected_binary_signal": (
                "candidate_eval > baseline_eval or equal-score promotion with one strict secondary improvement"
            ),
        }
    return {
        "failure_mode": "repeated_same_eval_or_discard",
        "single_mechanism_scope": (
            f"narrow the next mechanism experiment on {primary_target} to one failure mode"
        ),
        "change_hypothesis": (
            f"If the next experiment around {primary_target} isolates one failure mode instead of mutating multiple surfaces, "
            "candidate_eval improvement or equal-score secondary improvement becomes more likely."
        ),
        "expected_binary_signal": (
            "candidate_eval > baseline_eval or equal-score promotion with one strict secondary improvement"
        ),
    }


MECHANISM_CANDIDATE_REGISTRY = {
    BRANCH_GROWTH_CANDIDATE: MechanismCandidateSpec(
        candidate_type=BRANCH_GROWTH_CANDIDATE,
        build_candidate=_branch_growth_candidate,
        build_proposal_fields=_branch_growth_proposal_fields,
        trend_requirement=_branch_growth_requirement,
    ),
    HIGH_COMPLEXITY_CANDIDATE: MechanismCandidateSpec(
        candidate_type=HIGH_COMPLEXITY_CANDIDATE,
        build_candidate=_high_complexity_candidate,
        build_proposal_fields=_high_complexity_proposal_fields,
    ),
    SCHEMA_DRIFT_CANDIDATE: MechanismCandidateSpec(
        candidate_type=SCHEMA_DRIFT_CANDIDATE,
        build_candidate=_schema_drift_candidate,
        build_proposal_fields=_schema_drift_proposal_fields,
        trend_requirement=_schema_drift_requirement,
    ),
    POLICY_COMPLEXITY_GROWTH_CANDIDATE: MechanismCandidateSpec(
        candidate_type=POLICY_COMPLEXITY_GROWTH_CANDIDATE,
        build_candidate=_policy_complexity_growth_candidate,
        build_proposal_fields=_policy_complexity_growth_proposal_fields,
        trend_requirement=_policy_complexity_growth_requirement,
    ),
    EVAL_STAGNATION_CANDIDATE: MechanismCandidateSpec(
        candidate_type=EVAL_STAGNATION_CANDIDATE,
        build_candidate=_eval_stagnation_candidate,
        build_proposal_fields=_eval_stagnation_proposal_fields,
        trend_requirement=_eval_stagnation_requirement,
    ),
}
