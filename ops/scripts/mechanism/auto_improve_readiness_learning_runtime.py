from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import load_optional_json_object
from ops.scripts.gate_effect_vocabulary import (
    GATE_EFFECT_BLOCKS_EXECUTION,
    GATE_EFFECT_NONE,
    GATE_EFFECT_OPERATOR_REVIEW_REQUIRED,
)
from ops.scripts.learning_readiness_vocabulary import (
    LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID,
    LEARNING_STATUS_LIKELY,
    LEARNING_STATUS_NOT_RUNNABLE,
    LEARNING_STATUS_UNCERTAIN,
    is_signoff_supported_learning_blocker_id,
    learning_blocker_id_for_status,
)
from ops.scripts.policy_runtime import report_path

from .auto_improve_readiness_constants_runtime import (
    AUTO_IMPROVE_GOAL_ALLOW_LEARNING_UNCERTAIN_COMMAND,
    DEFAULT_DEFECT_ESCAPE_PAIR_COUNT,
    DEFAULT_HIGH_REWORK_COUNT,
    DEFAULT_HOLD_OR_DISCARD_MOVING_AVERAGE,
    DEFAULT_MIN_ATTEMPTS_CONSIDERED,
    READINESS_TARGET,
    ROUTING_PROVENANCE_AGGREGATE_DIR,
)


def _load_optional_json(path: Path) -> dict[str, Any]:
    return load_optional_json_object(path)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _float_value(value: object, default: float = 0.0) -> float:
    if not isinstance(value, str | int | float):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


LOOP_HEALTH_FLAG_SUMMARY_LABELS = {
    "missing_telemetry_coverage": "telemetry coverage missing",
    "partial_telemetry_coverage": "partial telemetry coverage",
    "routing_report_parse_gap": "routing parse gaps",
    "executor_report_parse_gap": "executor parse gaps",
    "executor_failures_present": "executor failures present",
    "rollback_signals_present": "rollback signals present",
    "rework_detected": "rework detected",
    "defect_escape_signals_present": "defect escape signals present",
    "unfinalized_runs_present": "unfinalized runs present",
    "recent_hold_present": "recent HOLD trend",
    "recent_discard_present": "recent DISCARD trend",
}

LEARNING_SIGNAL_CONTRACTS: dict[str, dict[str, Any]] = {
    "generated_reports_missing": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "make refresh-generated-core produces outcome metrics, mechanism review, and mutation proposal reports.",
            "make auto-improve-readiness reloads all queue input reports without generated_reports_missing.",
        ],
        "minimum_sample_size": 1,
        "next_evaluation_command": "make refresh-generated-core auto-improve-readiness",
        "closure_strategy": "refresh missing generated queue input reports before evaluating learning readiness.",
    },
    "outcome_metrics_attempt_history_below_minimum": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "ops/reports/outcome-metrics.json summary.attempts_considered is at or above min_attempts_considered.",
            "recent attempts include finalized mechanism runs relevant to the current proposal family.",
        ],
        "minimum_sample_size": DEFAULT_MIN_ATTEMPTS_CONSIDERED,
        "next_evaluation_command": "make outcome-metrics auto-improve-readiness",
        "closure_strategy": "accumulate enough finalized attempts before treating shadow learning as confirmed.",
    },
    "outcome_metrics_session_rollup_missing": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "ops/reports/outcome-metrics.json summary.session_reports_considered is greater than zero.",
            "At least one auto-improve session report contributes a usable learning_summary rollup.",
        ],
        "minimum_sample_size": 1,
        "next_evaluation_command": "make outcome-metrics auto-improve-readiness",
        "closure_strategy": "produce a usable session-level rollup before relying on cross-run learning metrics.",
    },
    "mechanism_review_session_context_missing": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "ops/reports/mechanism-review-candidates.json diagnostics.session_calibration.status is not no_session_context.",
            "The selected mechanism family has at least one run with session context.",
        ],
        "minimum_sample_size": 1,
        "next_evaluation_command": "make mechanism-review auto-improve-readiness",
        "closure_strategy": "connect mechanism review calibration to session context before closing the blocker.",
    },
    "loop_health_telemetry_coverage_missing": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "latest routing provenance aggregate reports loop_health.coverage_ratios.telemetry greater than zero.",
            "latest routing provenance aggregate no longer emits missing_telemetry_coverage.",
        ],
        "minimum_sample_size": 1,
        "next_evaluation_command": "make routing-provenance-aggregate auto-improve-readiness",
        "closure_strategy": "ensure run telemetry is discoverable in the latest loop-health aggregate.",
    },
    "same_eval_typed_evidence_missing": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "repeated_same_eval_or_discard proposal run telemetry records same_eval_reason_code.",
            "same-eval telemetry records strict_secondary_improvement_present and secondary_improvement_axes.",
            "same-eval telemetry records behavior_delta_digest for the behavior delta evidence used by promotion.",
        ],
        "minimum_sample_size": 1,
        "next_evaluation_command": "make learning-delta-scoreboard auto-improve-readiness",
        "closure_strategy": "regenerate or backfill same-eval run telemetry with typed evidence before machine learning claims.",
    },
    "recent_hold_moving_average": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "ops/reports/outcome-metrics.json metrics.moving_averages.hold is below the configured threshold.",
            "Recent HOLD outcomes are explained or superseded by newer finalized attempts.",
        ],
        "minimum_sample_size": DEFAULT_MIN_ATTEMPTS_CONSIDERED,
        "next_evaluation_command": "make outcome-metrics auto-improve-readiness",
        "closure_strategy": "reduce recent HOLD pressure before declaring the loop predictably learnable.",
    },
    "recent_discard_moving_average": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "ops/reports/outcome-metrics.json metrics.moving_averages.discard is below the configured threshold.",
            "Recent DISCARD outcomes are explained or superseded by newer finalized attempts.",
        ],
        "minimum_sample_size": DEFAULT_MIN_ATTEMPTS_CONSIDERED,
        "next_evaluation_command": "make outcome-metrics auto-improve-readiness",
        "closure_strategy": "reduce recent DISCARD pressure before declaring the loop predictably learnable.",
    },
    "high_rework": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "ops/reports/outcome-metrics.json metrics.rework_count is below the configured high_rework_count threshold.",
            "Repeated target rework keys are absent or superseded by a narrower successful mechanism run.",
        ],
        "minimum_sample_size": DEFAULT_MIN_ATTEMPTS_CONSIDERED,
        "next_evaluation_command": "make outcome-metrics mechanism-review auto-improve-readiness",
        "closure_strategy": "run narrower mechanism experiments until repeated rework drops below threshold.",
    },
    "defect_escape_proxy": {
        "owner": "runtime-maintainer",
        "required_evidence": [
            "ops/reports/outcome-metrics.json metrics.defect_escape_proxy.count is below the configured threshold.",
            "Promoted-then-regressed pairs are absent or closed by a follow-up mechanism improvement.",
        ],
        "minimum_sample_size": DEFAULT_MIN_ATTEMPTS_CONSIDERED,
        "next_evaluation_command": "make outcome-metrics mechanism-review auto-improve-readiness",
        "closure_strategy": "close escaped regression pairs before removing the learning readiness signoff dependency.",
    },
}


@dataclass(frozen=True)
class LearningReadinessAssessment:
    status: str
    gate_effect: str
    can_run: bool
    likely_to_learn: bool
    reasons: list[str]
    metrics: dict[str, Any]
    signals: list[dict[str, Any]]
    recommended_next_step: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "gate_effect": self.gate_effect,
            "can_run": self.can_run,
            "likely_to_learn": self.likely_to_learn,
            "reasons": self.reasons,
            "metrics": self.metrics,
            "signals": self.signals,
            "recommended_next_step": self.recommended_next_step,
        }


@dataclass(frozen=True)
class LearningClaimBlocker:
    blocker_id: str
    scope: str
    status: str
    severity: str
    accepted_risk: bool
    gate_effect: str
    source_status: str
    reason: str
    signal_ids: list[str]
    required_evidence: list[str]
    recommended_next_step: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.blocker_id,
            "scope": self.scope,
            "status": self.status,
            "severity": self.severity,
            "accepted_risk": self.accepted_risk,
            "gate_effect": self.gate_effect,
            "source_status": self.source_status,
            "reason": self.reason,
            "signal_ids": self.signal_ids,
            "required_evidence": self.required_evidence,
            "recommended_next_step": self.recommended_next_step,
        }


def _preview_policy(policy: dict[str, Any]) -> dict[str, Any]:
    configured = (
        policy.get("mechanism_review", {})
        .get("calibration", {})
        .get("outcome_metrics_preview", {})
    )
    return configured if isinstance(configured, dict) else {}


def _preview_thresholds(policy: dict[str, Any]) -> dict[str, Any]:
    preview_policy = _preview_policy(policy)
    return {
        "min_attempts_considered": _int_value(
            preview_policy.get("min_attempts_considered"),
            DEFAULT_MIN_ATTEMPTS_CONSIDERED,
        ),
        "hold_or_discard_moving_average": _float_value(
            preview_policy.get("hold_or_discard_moving_average"),
            DEFAULT_HOLD_OR_DISCARD_MOVING_AVERAGE,
        ),
        "high_rework_count": _int_value(
            preview_policy.get("high_rework_count"),
            DEFAULT_HIGH_REWORK_COUNT,
        ),
        "defect_escape_pair_count": _int_value(
            preview_policy.get("defect_escape_pair_count"),
            DEFAULT_DEFECT_ESCAPE_PAIR_COUNT,
        ),
    }


def _empty_loop_health_summary() -> dict[str, Any]:
    return {
        "status": "missing",
        "gate_effect": "none",
        "source_report": "",
        "source_generated_at": "",
        "session_id": "",
        "summary": "latest routing provenance aggregate not available; loop health summary missing.",
        "health_flags": [],
        "attempt_count": 0,
        "finalized_run_count": 0,
        "rework_count": 0,
        "rollback_signal_count": 0,
        "defect_escape_count": 0,
        "executor_failure_count": 0,
        "routing_report_parse_gap_count": 0,
        "executor_report_parse_gap_count": 0,
        "telemetry_coverage_ratio": 0.0,
    }


def _latest_routing_provenance_aggregate(vault: Path) -> tuple[str, dict[str, Any]]:
    reports_dir = vault / ROUTING_PROVENANCE_AGGREGATE_DIR
    if not reports_dir.exists():
        return "", {}

    latest_key = (-1, -1, -1, "", "")
    latest_rel_path = ""
    latest_payload: dict[str, Any] = {}
    for path in sorted(reports_dir.glob("*.json")):
        payload = _load_optional_json(path)
        if not payload:
            continue
        generated_at = str(payload.get("generated_at", "")).strip()
        rel_path = report_path(vault, path)
        session_id = str(payload.get("session_id", "")).strip()
        audit_rollup = payload.get("audit_rollup")
        loop_health = audit_rollup.get("loop_health") if isinstance(audit_rollup, dict) else None
        telemetry_coverage_ratio = 0.0
        attempt_count = 0
        finalized_run_count = 0
        health_flags: list[str] = []
        if isinstance(loop_health, dict):
            coverage_ratios = loop_health.get("coverage_ratios")
            if isinstance(coverage_ratios, dict):
                telemetry_coverage_ratio = _float_value(coverage_ratios.get("telemetry"))
            attempt_count = _int_value(loop_health.get("attempt_count"))
            finalized_run_count = _int_value(loop_health.get("finalized_run_count"))
            health_flags = _string_list(loop_health.get("health_flags"))
        has_loop_health_evidence = int(
            telemetry_coverage_ratio > 0.0
            or attempt_count > 0
            or finalized_run_count > 0
            or ("missing_telemetry_coverage" not in health_flags and bool(health_flags))
        )
        standalone_penalty = 0 if session_id == "standalone-run-telemetry" else 1
        candidate_key = (has_loop_health_evidence, standalone_penalty, int(isinstance(loop_health, dict)), generated_at, rel_path)
        if candidate_key >= latest_key:
            latest_key = candidate_key
            latest_rel_path = rel_path
            latest_payload = payload
    return latest_rel_path, latest_payload


def _loop_health_flag_summary(flag: str) -> str:
    return LOOP_HEALTH_FLAG_SUMMARY_LABELS.get(flag, flag.replace("_", " "))


def _loop_health_summary_text(
    *,
    attempt_count: int,
    finalized_run_count: int,
    rework_count: int,
    rollback_signal_count: int,
    defect_escape_count: int,
    executor_failure_count: int,
    routing_report_parse_gap_count: int,
    executor_report_parse_gap_count: int,
    telemetry_coverage_ratio: float,
    health_flags: list[str],
) -> str:
    segments = [
        f"attempts={attempt_count}",
        f"finalized={finalized_run_count}",
        f"rework={rework_count}",
        f"rollback_signals={rollback_signal_count}",
        f"defect_escape={defect_escape_count}",
        f"telemetry_coverage={telemetry_coverage_ratio:.2f}",
    ]
    if executor_failure_count > 0:
        segments.append(f"executor_failures={executor_failure_count}")
    if routing_report_parse_gap_count > 0:
        segments.append(f"routing_parse_gaps={routing_report_parse_gap_count}")
    if executor_report_parse_gap_count > 0:
        segments.append(f"executor_parse_gaps={executor_report_parse_gap_count}")
    summary = ", ".join(segments)
    if not health_flags:
        return summary
    flag_segments = [_loop_health_flag_summary(flag) for flag in health_flags[:3]]
    if len(health_flags) > 3:
        flag_segments.append(f"+{len(health_flags) - 3} more")
    return f"{summary} | alerts: {', '.join(flag_segments)}"


def _build_loop_health_summary(vault: Path) -> dict[str, Any]:
    summary = _empty_loop_health_summary()
    source_report, aggregate = _latest_routing_provenance_aggregate(vault)
    if not aggregate:
        return summary

    summary["source_report"] = source_report
    summary["source_generated_at"] = str(aggregate.get("generated_at", "")).strip()
    summary["session_id"] = str(aggregate.get("session_id", "")).strip()

    audit_rollup = aggregate.get("audit_rollup")
    loop_health = audit_rollup.get("loop_health") if isinstance(audit_rollup, dict) else None
    if not isinstance(loop_health, dict):
        summary["summary"] = (
            "latest routing provenance aggregate is present but loop health data is unavailable."
        )
        return summary

    coverage_ratios = loop_health.get("coverage_ratios")
    telemetry_coverage_ratio = (
        round(_float_value(coverage_ratios.get("telemetry")), 4)
        if isinstance(coverage_ratios, dict)
        else 0.0
    )
    health_flags = _string_list(loop_health.get("health_flags"))
    attempt_count = int(loop_health.get("attempt_count", 0) or 0)
    finalized_run_count = int(loop_health.get("finalized_run_count", 0) or 0)
    rework_count = int(loop_health.get("rework_count", 0) or 0)
    rollback_signal_count = int(loop_health.get("rollback_signal_count", 0) or 0)
    defect_escape_count = int(loop_health.get("defect_escape_count", 0) or 0)
    executor_failure_count = int(loop_health.get("executor_failure_count", 0) or 0)
    routing_report_parse_gap_count = int(loop_health.get("routing_report_parse_gap_count", 0) or 0)
    executor_report_parse_gap_count = int(loop_health.get("executor_report_parse_gap_count", 0) or 0)

    summary.update(
        {
            "status": "available",
            "summary": _loop_health_summary_text(
                attempt_count=attempt_count,
                finalized_run_count=finalized_run_count,
                rework_count=rework_count,
                rollback_signal_count=rollback_signal_count,
                defect_escape_count=defect_escape_count,
                executor_failure_count=executor_failure_count,
                routing_report_parse_gap_count=routing_report_parse_gap_count,
                executor_report_parse_gap_count=executor_report_parse_gap_count,
                telemetry_coverage_ratio=telemetry_coverage_ratio,
                health_flags=health_flags,
            ),
            "health_flags": health_flags,
            "attempt_count": attempt_count,
            "finalized_run_count": finalized_run_count,
            "rework_count": rework_count,
            "rollback_signal_count": rollback_signal_count,
            "defect_escape_count": defect_escape_count,
            "executor_failure_count": executor_failure_count,
            "routing_report_parse_gap_count": routing_report_parse_gap_count,
            "executor_report_parse_gap_count": executor_report_parse_gap_count,
            "telemetry_coverage_ratio": telemetry_coverage_ratio,
        }
    )
    return summary


def _signal(signal_id: str, detail: str) -> dict[str, Any]:
    contract = LEARNING_SIGNAL_CONTRACTS.get(
        signal_id,
        {
            "owner": "runtime-maintainer",
            "required_evidence": ["Refresh auto-improve readiness and inspect the named learning signal."],
            "minimum_sample_size": 1,
            "next_evaluation_command": READINESS_TARGET,
            "closure_strategy": "triage this learning signal before closing the release blocker.",
        },
    )
    return {
        "id": signal_id,
        "severity": "warn",
        "detail": detail,
        "owner": str(contract["owner"]),
        "required_evidence": list(contract["required_evidence"]),
        "minimum_sample_size": int(contract["minimum_sample_size"]),
        "next_evaluation_command": str(contract["next_evaluation_command"]),
        "closure_strategy": str(contract["closure_strategy"]),
    }


def _outcome_history_shadow_signals(
    *,
    reports_present: bool,
    outcome_summary: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if not reports_present:
        signals.append(
            _signal(
                "generated_reports_missing",
                "one or more generated queue input reports are missing or empty",
            )
        )

    attempts_considered = _int_value(outcome_summary.get("attempts_considered"))
    min_attempts = _int_value(
        thresholds.get("min_attempts_considered"),
        DEFAULT_MIN_ATTEMPTS_CONSIDERED,
    )
    if attempts_considered < min_attempts:
        signals.append(
            _signal(
                "outcome_metrics_attempt_history_below_minimum",
                f"attempts_considered={attempts_considered} is below min_attempts_considered={min_attempts}",
            )
        )

    session_reports_considered = _int_value(outcome_summary.get("session_reports_considered"))
    if session_reports_considered <= 0:
        signals.append(
            _signal(
                "outcome_metrics_session_rollup_missing",
                "session_reports_considered=0 so outcome metrics still lack session-rollup evidence",
            )
        )
    return signals


def _mechanism_session_shadow_signals(
    mechanism_review_report: dict[str, Any],
) -> list[dict[str, Any]]:
    diagnostics = mechanism_review_report.get("diagnostics", {})
    session_calibration = diagnostics.get("session_calibration") if isinstance(diagnostics, dict) else {}
    session_calibration_status = (
        str(session_calibration.get("status", "")).strip()
        if isinstance(session_calibration, dict)
        else ""
    )
    if session_calibration_status != "no_session_context":
        return []
    return [
        _signal(
            "mechanism_review_session_context_missing",
            "session_calibration.status=no_session_context",
        )
    ]


def _loop_health_shadow_signals(
    loop_health_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    loop_health_status = str(loop_health_summary.get("status", "")).strip()
    telemetry_coverage_ratio = _float_value(loop_health_summary.get("telemetry_coverage_ratio"))
    loop_health_flags = _string_list(loop_health_summary.get("health_flags", []))
    if loop_health_status != "available" or (
        telemetry_coverage_ratio > 0.0 and "missing_telemetry_coverage" not in loop_health_flags
    ):
        return []
    return [
        _signal(
            "loop_health_telemetry_coverage_missing",
            (
                "loop_health.telemetry_coverage_ratio="
                f"{telemetry_coverage_ratio:.4f} so routing provenance still lacks telemetry-backed learning evidence"
            ),
        )
    ]


def _same_eval_shadow_signals(
    same_eval_telemetry_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    if same_eval_telemetry_summary.get("status") != "blocked":
        return []
    return [
        _signal(
            "same_eval_typed_evidence_missing",
            (
                "same-eval telemetry typed evidence coverage is incomplete: "
                "same_eval_reason_code="
                f"{_float_value(same_eval_telemetry_summary.get('same_eval_reason_code_coverage_ratio')):.4f}, "
                "strict_secondary_improvement="
                f"{_float_value(same_eval_telemetry_summary.get('strict_secondary_improvement_coverage_ratio')):.4f}, "
                "behavior_delta_digest="
                f"{_float_value(same_eval_telemetry_summary.get('behavior_delta_digest_coverage_ratio')):.4f}"
            ),
        )
    ]


def _outcome_quality_shadow_signals(
    outcome_metrics: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    moving_averages = outcome_metrics.get("moving_averages", {})
    if not isinstance(moving_averages, dict):
        moving_averages = {}
    ratio_threshold = _float_value(
        thresholds.get("hold_or_discard_moving_average"),
        DEFAULT_HOLD_OR_DISCARD_MOVING_AVERAGE,
    )
    hold_average = _float_value(moving_averages.get("hold"))
    if hold_average >= ratio_threshold:
        signals.append(
            _signal(
                "recent_hold_moving_average",
                f"hold_moving_average={hold_average:.4f} is at or above threshold={ratio_threshold:.4f}",
            )
        )
    discard_average = _float_value(moving_averages.get("discard"))
    if discard_average >= ratio_threshold:
        signals.append(
            _signal(
                "recent_discard_moving_average",
                f"discard_moving_average={discard_average:.4f} is at or above threshold={ratio_threshold:.4f}",
            )
        )

    rework_count = _int_value(outcome_metrics.get("rework_count"))
    high_rework_count = _int_value(
        thresholds.get("high_rework_count"),
        DEFAULT_HIGH_REWORK_COUNT,
    )
    if rework_count >= high_rework_count:
        signals.append(
            _signal(
                "high_rework",
                f"rework_count={rework_count} is at or above threshold={high_rework_count}",
            )
        )

    defect_escape = outcome_metrics.get("defect_escape_proxy", {})
    if not isinstance(defect_escape, dict):
        defect_escape = {}
    defect_escape_count = _int_value(defect_escape.get("count"))
    defect_escape_threshold = _int_value(
        thresholds.get("defect_escape_pair_count"),
        DEFAULT_DEFECT_ESCAPE_PAIR_COUNT,
    )
    if defect_escape_count >= defect_escape_threshold:
        signals.append(
            _signal(
                "defect_escape_proxy",
                (
                    f"defect_escape_pair_count={defect_escape_count} "
                    f"is at or above threshold={defect_escape_threshold}"
                ),
            )
        )
    return signals


def _loop_health_confirms_current_outcome_quality(loop_health_summary: dict[str, Any]) -> bool:
    if str(loop_health_summary.get("status", "")).strip() != "available":
        return False
    if _int_value(loop_health_summary.get("attempt_count")) <= 0:
        return False
    if _int_value(loop_health_summary.get("finalized_run_count")) <= 0:
        return False
    if _float_value(loop_health_summary.get("telemetry_coverage_ratio")) < 1.0:
        return False
    if _string_list(loop_health_summary.get("health_flags")):
        return False
    for field in (
        "rework_count",
        "rollback_signal_count",
        "defect_escape_count",
        "executor_failure_count",
        "routing_report_parse_gap_count",
        "executor_report_parse_gap_count",
    ):
        if _int_value(loop_health_summary.get(field)) > 0:
            return False
    return True


def _learnability_shadow_signals(
    *,
    reports_present: bool,
    outcome_summary: dict[str, Any],
    outcome_metrics: dict[str, Any],
    mechanism_review_report: dict[str, Any],
    loop_health_summary: dict[str, Any],
    same_eval_telemetry_summary: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[dict[str, Any]]:
    current_loop_quality_clean = _loop_health_confirms_current_outcome_quality(loop_health_summary)
    return [
        *_outcome_history_shadow_signals(
            reports_present=reports_present,
            outcome_summary=outcome_summary,
            thresholds=thresholds,
        ),
        *_mechanism_session_shadow_signals(mechanism_review_report),
        *_loop_health_shadow_signals(loop_health_summary),
        *_same_eval_shadow_signals(same_eval_telemetry_summary),
        *(
            []
            if current_loop_quality_clean
            else _outcome_quality_shadow_signals(outcome_metrics, thresholds)
        ),
    ]


def _learning_readiness_assessment(
    *,
    queue_ready: bool,
    reports_present: bool,
    outcome_summary: dict[str, Any],
    active_outcome_metrics: dict[str, Any],
    active_mechanism_review: dict[str, Any],
    loop_health_summary: dict[str, Any],
    same_eval_telemetry_summary: dict[str, Any],
    policy: dict[str, Any],
) -> LearningReadinessAssessment:
    outcome_metrics = active_outcome_metrics.get("metrics", {})
    if not isinstance(outcome_metrics, dict):
        outcome_metrics = {}
    diagnostics = active_mechanism_review.get("diagnostics", {})
    session_calibration = diagnostics.get("session_calibration") if isinstance(diagnostics, dict) else {}
    session_calibration_status = (
        str(session_calibration.get("status", "")).strip()
        if isinstance(session_calibration, dict)
        else ""
    )
    moving_averages = outcome_metrics.get("moving_averages", {})
    if not isinstance(moving_averages, dict):
        moving_averages = {}
    defect_escape = outcome_metrics.get("defect_escape_proxy", {})
    if not isinstance(defect_escape, dict):
        defect_escape = {}

    thresholds = _preview_thresholds(policy)
    shadow_signals = _learnability_shadow_signals(
        reports_present=reports_present,
        outcome_summary=outcome_summary,
        outcome_metrics=outcome_metrics,
        mechanism_review_report=active_mechanism_review,
        loop_health_summary=loop_health_summary,
        same_eval_telemetry_summary=same_eval_telemetry_summary,
        thresholds=thresholds,
    )
    likely_to_learn = queue_ready and not shadow_signals
    status = LEARNING_STATUS_LIKELY if likely_to_learn else LEARNING_STATUS_UNCERTAIN
    gate_effect = GATE_EFFECT_NONE if likely_to_learn else GATE_EFFECT_OPERATOR_REVIEW_REQUIRED
    if not queue_ready:
        status = LEARNING_STATUS_NOT_RUNNABLE
        gate_effect = GATE_EFFECT_BLOCKS_EXECUTION
    likely_reason = (
        "runnable queue has enough outcome/session evidence and no shadow learning warnings"
        if likely_to_learn
        else "shadow learning signals require operator review before this run can count as confirmed learning"
    )
    if not queue_ready:
        likely_reason = "no runnable proposal is available, so learning likelihood is not evaluated as ready"

    recommended_next_step = (
        "Execution readiness is blocked, so keep auto-improve paused until the runnable proposal queue is non-empty."
        if not queue_ready
        else (
            "Learning readiness is clean enough for bounded live auto-improve; keep the run narrow and continue monitoring the shadow signals."
            if likely_to_learn
            else (
                "Execution readiness is pass, but learning readiness still requires explicit operator review. "
                "Rerun goal-native auto-improve with "
                f"`{AUTO_IMPROVE_GOAL_ALLOW_LEARNING_UNCERTAIN_COMMAND}` only if you want a bounded runtime "
                "with runner heartbeat, checkpoint, resume, and timeout evidence while session evidence remains incomplete."
            )
        )
    )

    return LearningReadinessAssessment(
        status=status,
        gate_effect=gate_effect,
        can_run=queue_ready,
        likely_to_learn=likely_to_learn,
        reasons=[
            "runnable proposal queue is non-empty"
            if queue_ready
            else "no runnable proposal is available",
            likely_reason,
        ],
        metrics={
            "attempts_considered": _int_value(outcome_summary.get("attempts_considered")),
            "min_attempts_considered": thresholds["min_attempts_considered"],
            "session_reports_considered": _int_value(outcome_summary.get("session_reports_considered")),
            "session_calibration_status": session_calibration_status,
            "telemetry_coverage_ratio": _float_value(loop_health_summary.get("telemetry_coverage_ratio")),
            "same_eval_run_count": _int_value(same_eval_telemetry_summary.get("run_count")),
            "same_eval_reason_code_coverage_ratio": _float_value(
                same_eval_telemetry_summary.get("same_eval_reason_code_coverage_ratio")
            ),
            "strict_secondary_improvement_coverage_ratio": _float_value(
                same_eval_telemetry_summary.get("strict_secondary_improvement_coverage_ratio")
            ),
            "behavior_delta_digest_coverage_ratio": _float_value(
                same_eval_telemetry_summary.get("behavior_delta_digest_coverage_ratio")
            ),
            "rework_count": _int_value(outcome_metrics.get("rework_count")),
            "hold_moving_average": _float_value(moving_averages.get("hold")),
            "discard_moving_average": _float_value(moving_averages.get("discard")),
            "defect_escape_pair_count": _int_value(defect_escape.get("count")),
        },
        signals=shadow_signals,
        recommended_next_step=recommended_next_step,
    )


def _learning_claim_blockers(learning: LearningReadinessAssessment) -> list[LearningClaimBlocker]:
    if learning.likely_to_learn:
        return []

    signal_ids = [
        str(signal.get("id", "")).strip()
        for signal in learning.signals
        if isinstance(signal, dict) and str(signal.get("id", "")).strip()
    ]
    blocker_id = learning_blocker_id_for_status(learning.status)
    reason = "; ".join(learning.reasons)
    if signal_ids:
        reason = f"{reason}; learning signals: {', '.join(signal_ids)}"
    if blocker_id == LEARNING_EXECUTION_NOT_RUNNABLE_BLOCKER_ID:
        required_evidence = [
            "execution_readiness.can_run must be true before learning readiness can pass",
            "restore a non-empty runnable proposal queue; learning-readiness signoff cannot accept not_runnable execution blockers",
        ]
    else:
        required_evidence = [
            "learning_readiness.likely_to_learn must be true before release readiness can pass",
            "or an operator must record accepted risk for this named learning review blocker",
        ]

    return [
        LearningClaimBlocker(
            blocker_id=blocker_id,
            scope="learning_readiness",
            status="open",
            severity="blocker",
            accepted_risk=False,
            gate_effect=learning.gate_effect,
            source_status=learning.status,
            reason=reason,
            signal_ids=signal_ids,
            required_evidence=required_evidence,
            recommended_next_step=learning.recommended_next_step,
        )
    ]


def learning_claim_blocker_payloads(
    learning: LearningReadinessAssessment,
    *,
    signoff_active: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claim_blockers = [
        blocker.to_wire() for blocker in _learning_claim_blockers(learning)
    ]
    if not signoff_active:
        return claim_blockers, claim_blockers
    promotion_blockers = [
        blocker
        for blocker in claim_blockers
        if not is_signoff_supported_learning_blocker_id(
            str(blocker.get("id", "")).strip()
        )
    ]
    return claim_blockers, promotion_blockers
