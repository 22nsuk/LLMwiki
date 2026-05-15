from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .mechanism_review_history_runtime import load_optional_json

JsonLoader = Callable[[Path], dict | None]
DEFAULT_OUTCOME_METRICS_REPORT = "ops/reports/outcome-metrics.json"
OUTCOME_METRICS_PREVIEW_DEFAULTS = {
    "enabled": True,
    "mode": "audit_only",
    "source_report": DEFAULT_OUTCOME_METRICS_REPORT,
    "recent_window": 20,
    "high_rework_count": 1,
    "hold_or_discard_moving_average": 0.25,
    "rollback_signal_ratio": 0.2,
    "defect_escape_pair_count": 1,
    "min_attempts_considered": 10,
    "min_target_attempts": 2,
    "shadow_priority_max_delta": 10,
}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _float_value(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def outcome_metrics_preview_policy(policy: dict) -> dict:
    configured = (
        policy.get("mechanism_review", {})
        .get("calibration", {})
        .get("outcome_metrics_preview", {})
    )
    merged = dict(OUTCOME_METRICS_PREVIEW_DEFAULTS)
    if isinstance(configured, dict):
        merged.update(configured)
    return merged


def _outcome_metrics_thresholds(preview_policy: dict) -> dict:
    return {
        "high_rework_count": _int_value(preview_policy.get("high_rework_count"), 1),
        "hold_or_discard_moving_average": _float_value(
            preview_policy.get("hold_or_discard_moving_average"),
            0.25,
        ),
        "rollback_signal_ratio": _float_value(
            preview_policy.get("rollback_signal_ratio"),
            0.2,
        ),
        "defect_escape_pair_count": _int_value(
            preview_policy.get("defect_escape_pair_count"),
            1,
        ),
    }


def _shadow_priority_enabled(preview_policy: dict) -> bool:
    return str(preview_policy.get("mode", "audit_only")).strip() == "shadow_priority"


def _shadow_candidate_order(candidates: list[dict], priority_by_id: dict[str, int] | None = None) -> list[str]:
    def sort_key(candidate: dict) -> tuple[int, str]:
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        priority = (
            priority_by_id.get(candidate_id, _int_value(candidate.get("priority")))
            if priority_by_id is not None
            else _int_value(candidate.get("priority"))
        )
        return (-priority, candidate_id)

    return [
        str(candidate.get("candidate_id", "")).strip()
        for candidate in sorted(candidates, key=sort_key)
        if str(candidate.get("candidate_id", "")).strip()
    ]


def _shadow_priority_baseline(
    *,
    preview_policy: dict,
    candidates: list[dict],
    global_signals: dict,
    status: str,
) -> dict:
    return {
        "status": status,
        "gate_effect": "none",
        "min_attempts_considered": _int_value(preview_policy.get("min_attempts_considered"), 10),
        "min_target_attempts": _int_value(preview_policy.get("min_target_attempts"), 2),
        "shadow_priority_max_delta": _int_value(preview_policy.get("shadow_priority_max_delta"), 10),
        "attempts_considered": _int_value(global_signals.get("attempt_count")),
        "current_order": _shadow_candidate_order(candidates),
        "shadow_order": _shadow_candidate_order(candidates),
        "order_changed": False,
        "ordering_deltas": [],
    }


def _empty_moving_averages() -> dict:
    return {
        "hold": 0.0,
        "discard": 0.0,
        "rollback_signal": 0.0,
    }


def _outcome_global_signals(outcome_report: dict | None) -> dict:
    metrics = outcome_report.get("metrics", {}) if isinstance(outcome_report, dict) else {}
    if not isinstance(metrics, dict):
        metrics = {}
    moving_averages = metrics.get("moving_averages", {})
    if not isinstance(moving_averages, dict):
        moving_averages = {}
    defect_escape = metrics.get("defect_escape_proxy", {})
    if not isinstance(defect_escape, dict):
        defect_escape = {}
    return {
        "attempt_count": _int_value(metrics.get("attempt_count")),
        "recent_attempt_count": _int_value(metrics.get("recent_attempt_count")),
        "moving_averages": {
            "hold": _float_value(moving_averages.get("hold")),
            "discard": _float_value(moving_averages.get("discard")),
            "rollback_signal": _float_value(moving_averages.get("rollback_signal")),
        },
        "rework_count": _int_value(metrics.get("rework_count")),
        "rollback_signal_count": _int_value(metrics.get("rollback_signal_count")),
        "defect_escape_pair_count": _int_value(defect_escape.get("count")),
    }


def _outcome_metrics_evidence_gaps(
    *,
    preview_policy: dict,
    source_report: str,
    outcome_report: dict | None,
    candidates: list[dict],
    target_signals: list[dict],
) -> list[str]:
    if not isinstance(outcome_report, dict):
        return [f"missing source report: {source_report}"]
    metrics = outcome_report.get("metrics")
    if not isinstance(metrics, dict):
        return [f"invalid outcome metrics report: {source_report} does not contain a metrics object"]

    summary = outcome_report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    evidence_gaps: list[str] = []
    attempts_considered = _int_value(
        summary.get("attempts_considered"),
        _int_value(metrics.get("attempt_count")),
    )
    min_attempts = _int_value(preview_policy.get("min_attempts_considered"), 10)
    if attempts_considered < min_attempts:
        evidence_gaps.append(
            f"attempts_considered={attempts_considered} is below min_attempts_considered={min_attempts}"
        )

    session_reports_considered = _int_value(summary.get("session_reports_considered"))
    if session_reports_considered <= 0:
        evidence_gaps.append(
            "session_reports_considered=0 so outcome metrics still lack session-rollup evidence"
        )

    rollback_coverage = _int_value(metrics.get("rollback_rehearsal_coverage_count"))
    if rollback_coverage <= 0:
        evidence_gaps.append(
            "rollback_rehearsal_coverage_count=0 so rollback rehearsal coverage is not yet evidenced"
        )

    if candidates:
        min_target_attempts = _int_value(preview_policy.get("min_target_attempts"), 2)
        max_target_attempts = max(
            (_int_value(signal.get("attempt_count")) for signal in target_signals),
            default=0,
        )
        if max_target_attempts < min_target_attempts:
            evidence_gaps.append(
                f"max_target_attempts={max_target_attempts} is below min_target_attempts={min_target_attempts}"
            )

    return evidence_gaps


def _empty_outcome_metrics_calibration_diagnostics(
    *,
    preview_policy: dict,
    thresholds: dict,
    status: str,
    candidate_count: int,
    candidates: list[dict] | None = None,
) -> dict:
    global_signals = {
        "attempt_count": 0,
        "recent_attempt_count": 0,
        "moving_averages": _empty_moving_averages(),
        "rework_count": 0,
        "rollback_signal_count": 0,
        "defect_escape_pair_count": 0,
    }
    shadow_status = "disabled"
    if _shadow_priority_enabled(preview_policy):
        shadow_status = "no_candidates" if candidate_count == 0 else "unavailable"
    return {
        "enabled": bool(preview_policy.get("enabled", True)),
        "status": status,
        "mode": str(preview_policy.get("mode", "audit_only")).strip() or "audit_only",
        "gate_effect": "none",
        "source_report": str(
            preview_policy.get("source_report", DEFAULT_OUTCOME_METRICS_REPORT)
        ).strip()
        or DEFAULT_OUTCOME_METRICS_REPORT,
        "recent_window": _int_value(preview_policy.get("recent_window"), 20),
        "candidate_count": candidate_count,
        "candidates_with_outcome_context": 0,
        "target_count": 0,
        "thresholds": thresholds,
        "global_signals": global_signals,
        "target_signals": [],
        "family_signals": [],
        "high_rework_targets": [],
        "defect_escape_pairs": [],
        "shadow_priority": _shadow_priority_baseline(
            preview_policy=preview_policy,
            candidates=candidates or [],
            global_signals=global_signals,
            status=shadow_status,
        ),
        "evidence_gaps": [],
        "notes": [
            "audit-only preview: outcome metrics are reported for calibration review and do not change candidate priority.",
            "priority_delta and gate integration remain disabled until a later explicit policy step.",
        ],
    }


def _outcome_attempts_by_run(outcome_report: dict) -> dict[str, dict]:
    attempts_by_run: dict[str, dict] = {}
    recent_attempts = outcome_report.get("recent_attempts", [])
    if not isinstance(recent_attempts, list):
        return attempts_by_run
    for attempt in recent_attempts:
        if not isinstance(attempt, dict):
            continue
        run_id = str(attempt.get("run_id", "")).strip()
        if run_id:
            attempts_by_run[run_id] = attempt
    return attempts_by_run


def _outcome_rework_entries(outcome_report: dict) -> list[dict]:
    metrics = outcome_report.get("metrics", {})
    if not isinstance(metrics, dict):
        return []
    rework_keys = metrics.get("rework_keys", [])
    return [entry for entry in rework_keys if isinstance(entry, dict)] if isinstance(rework_keys, list) else []


def _outcome_defect_escape_pairs(outcome_report: dict) -> list[dict]:
    metrics = outcome_report.get("metrics", {})
    if not isinstance(metrics, dict):
        return []
    defect_escape = metrics.get("defect_escape_proxy", {})
    if not isinstance(defect_escape, dict):
        return []
    pairs = defect_escape.get("pairs", [])
    return [pair for pair in pairs if isinstance(pair, dict)] if isinstance(pairs, list) else []


def _target_contexts(candidates: list[dict]) -> dict[tuple[str, ...], dict]:
    contexts: dict[tuple[str, ...], dict] = {}
    for candidate in candidates:
        primary_targets = tuple(_string_list(candidate.get("primary_targets")))
        if not primary_targets:
            continue
        context = contexts.setdefault(
            primary_targets,
            {
                "primary_targets": list(primary_targets),
                "candidate_ids": [],
                "candidate_types": [],
                "families": [],
                "candidate_count_by_family": {},
                "current_priorities": [],
                "run_ids": [],
            },
        )
        family = str(candidate.get("family", "")).strip() or "<unknown>"
        context["candidate_ids"].append(str(candidate.get("candidate_id", "")).strip())
        context["candidate_types"].append(str(candidate.get("candidate_type", "")).strip())
        context["families"].append(family)
        context["candidate_count_by_family"][family] = (
            int(context["candidate_count_by_family"].get(family, 0)) + 1
        )
        context["current_priorities"].append(_int_value(candidate.get("priority")))
        context["run_ids"].extend(_string_list(candidate.get("run_ids")))
    for context in contexts.values():
        for key in ("candidate_ids", "candidate_types", "families", "run_ids"):
            context[key] = sorted({item for item in context[key] if item})
    return contexts


def _preview_flags(
    *,
    hold_ratio: float,
    discard_ratio: float,
    rollback_signal_ratio: float,
    rework_count: int,
    defect_escape_pair_count: int,
    thresholds: dict,
) -> list[str]:
    flags: list[str] = []
    if rework_count >= _int_value(thresholds.get("high_rework_count"), 1):
        flags.append("high_rework")
    moving_average_threshold = _float_value(
        thresholds.get("hold_or_discard_moving_average"),
        0.25,
    )
    if hold_ratio >= moving_average_threshold:
        flags.append("recent_hold_moving_average")
    if discard_ratio >= moving_average_threshold:
        flags.append("recent_discard_moving_average")
    if rollback_signal_ratio >= _float_value(thresholds.get("rollback_signal_ratio"), 0.2):
        flags.append("rollback_signal_ratio")
    if defect_escape_pair_count >= _int_value(thresholds.get("defect_escape_pair_count"), 1):
        flags.append("defect_escape_proxy")
    return flags


def _build_target_outcome_signal(
    context: dict,
    *,
    attempts_by_run: dict[str, dict],
    rework_entries: list[dict],
    defect_escape_pairs: list[dict],
    thresholds: dict,
) -> dict:
    primary_targets = _string_list(context.get("primary_targets"))
    target_set = set(primary_targets)
    run_ids = set(_string_list(context.get("run_ids")))
    source_attempts = []
    for attempt in attempts_by_run.values():
        attempt_targets = set(_string_list(attempt.get("primary_targets")))
        attempt_run_id = str(attempt.get("run_id", "")).strip()
        if target_set.intersection(attempt_targets) or attempt_run_id in run_ids:
            source_attempts.append(attempt)
            if attempt_run_id:
                run_ids.add(attempt_run_id)

    hold_count = sum(1 for attempt in source_attempts if str(attempt.get("decision", "")).strip() == "HOLD")
    discard_count = sum(
        1 for attempt in source_attempts if str(attempt.get("decision", "")).strip() == "DISCARD"
    )
    rollback_signal_count = sum(1 for attempt in source_attempts if bool(attempt.get("rollback_signal")))
    attempt_count = len(source_attempts)
    matched_rework = [
        entry
        for entry in rework_entries
        if run_ids.intersection(_string_list(entry.get("run_ids")))
    ]
    rework_count = sum(_int_value(entry.get("rework_count")) for entry in matched_rework)
    matched_defect_pairs = [
        pair
        for pair in defect_escape_pairs
        if str(pair.get("target", "")).strip() in target_set
        or str(pair.get("promoted_run_id", "")).strip() in run_ids
        or str(pair.get("escaped_run_id", "")).strip() in run_ids
    ]
    hold_ratio = round(hold_count / attempt_count, 4) if attempt_count else 0.0
    discard_ratio = round(discard_count / attempt_count, 4) if attempt_count else 0.0
    rollback_signal_ratio = round(rollback_signal_count / attempt_count, 4) if attempt_count else 0.0
    return {
        "primary_targets": primary_targets,
        "candidate_ids": _string_list(context.get("candidate_ids")),
        "candidate_types": _string_list(context.get("candidate_types")),
        "families": _string_list(context.get("families")),
        "candidate_count_by_family": {
            str(family): _int_value(count)
            for family, count in dict(context.get("candidate_count_by_family", {})).items()
        },
        "current_priority_max": max(
            [_int_value(value) for value in context.get("current_priorities", [])],
            default=0,
        ),
        "attempt_count": attempt_count,
        "source_run_ids": sorted(run_ids),
        "hold_count": hold_count,
        "discard_count": discard_count,
        "hold_moving_average": hold_ratio,
        "discard_moving_average": discard_ratio,
        "rollback_signal_count": rollback_signal_count,
        "rollback_signal_ratio": rollback_signal_ratio,
        "rework_count": rework_count,
        "defect_escape_pair_count": len(matched_defect_pairs),
        "preview_flags": _preview_flags(
            hold_ratio=hold_ratio,
            discard_ratio=discard_ratio,
            rollback_signal_ratio=rollback_signal_ratio,
            rework_count=rework_count,
            defect_escape_pair_count=len(matched_defect_pairs),
            thresholds=thresholds,
        ),
    }


def _empty_family_outcome_signal(family: str) -> dict:
    return {
        "family": family,
        "target_count": 0,
        "candidate_count": 0,
        "attempt_count": 0,
        "hold_count": 0,
        "discard_count": 0,
        "rollback_signal_count": 0,
        "rework_count": 0,
        "defect_escape_pair_count": 0,
        "preview_flags": [],
    }


def _family_outcome_signals(target_signals: list[dict]) -> list[dict]:
    by_family: dict[str, dict] = {}
    for signal in target_signals:
        family_counts = dict(signal.get("candidate_count_by_family", {}))
        for family in _string_list(signal.get("families")):
            entry = by_family.setdefault(family, _empty_family_outcome_signal(family))
            entry["target_count"] += 1
            entry["candidate_count"] += _int_value(family_counts.get(family))
            for key in (
                "attempt_count",
                "hold_count",
                "discard_count",
                "rollback_signal_count",
                "rework_count",
                "defect_escape_pair_count",
            ):
                entry[key] += _int_value(signal.get(key))
            entry["preview_flags"].extend(_string_list(signal.get("preview_flags")))
    for entry in by_family.values():
        attempt_count = _int_value(entry.get("attempt_count"))
        entry["hold_moving_average"] = (
            round(_int_value(entry.get("hold_count")) / attempt_count, 4) if attempt_count else 0.0
        )
        entry["discard_moving_average"] = (
            round(_int_value(entry.get("discard_count")) / attempt_count, 4)
            if attempt_count
            else 0.0
        )
        entry["rollback_signal_ratio"] = (
            round(_int_value(entry.get("rollback_signal_count")) / attempt_count, 4)
            if attempt_count
            else 0.0
        )
        entry["preview_flags"] = sorted(set(_string_list(entry.get("preview_flags"))))
    return [by_family[key] for key in sorted(by_family)]


def _high_rework_targets(target_signals: list[dict], thresholds: dict) -> list[dict]:
    high_rework_count = _int_value(thresholds.get("high_rework_count"), 1)
    return [
        {
            "primary_targets": _string_list(signal.get("primary_targets")),
            "families": _string_list(signal.get("families")),
            "rework_count": _int_value(signal.get("rework_count")),
            "source_run_ids": _string_list(signal.get("source_run_ids")),
        }
        for signal in target_signals
        if _int_value(signal.get("rework_count")) >= high_rework_count
    ]


def _shadow_priority_delta(signal: dict, *, preview_policy: dict) -> tuple[int, str]:
    if _int_value(signal.get("attempt_count")) < _int_value(preview_policy.get("min_target_attempts"), 2):
        return 0, "insufficient_target_attempts"
    weights = {
        "high_rework": 4,
        "recent_hold_moving_average": 2,
        "recent_discard_moving_average": 3,
        "rollback_signal_ratio": 2,
        "defect_escape_proxy": 4,
    }
    delta = sum(weights.get(flag, 0) for flag in _string_list(signal.get("preview_flags")))
    max_delta = max(_int_value(preview_policy.get("shadow_priority_max_delta"), 10), 0)
    return min(delta, max_delta), "preview_flags"


def _candidate_target_signal(candidate: dict, target_signal_by_targets: dict[tuple[str, ...], dict]) -> dict | None:
    primary_targets = tuple(_string_list(candidate.get("primary_targets")))
    if primary_targets in target_signal_by_targets:
        return target_signal_by_targets[primary_targets]
    candidate_targets = set(primary_targets)
    for targets, signal in target_signal_by_targets.items():
        if candidate_targets.intersection(targets):
            return signal
    return None


def _shadow_priority_diagnostics(
    *,
    preview_policy: dict,
    candidates: list[dict],
    target_signals: list[dict],
    global_signals: dict,
    outcome_status: str,
) -> dict:
    if not _shadow_priority_enabled(preview_policy):
        return _shadow_priority_baseline(
            preview_policy=preview_policy,
            candidates=candidates,
            global_signals=global_signals,
            status="disabled",
        )

    min_attempts = _int_value(preview_policy.get("min_attempts_considered"), 10)
    baseline = _shadow_priority_baseline(
        preview_policy=preview_policy,
        candidates=candidates,
        global_signals=global_signals,
        status=outcome_status,
    )
    if not candidates:
        baseline["status"] = "no_candidates"
        return baseline
    if _int_value(global_signals.get("attempt_count")) < min_attempts:
        baseline["status"] = "insufficient_data"
        return baseline
    if outcome_status != "active":
        baseline["status"] = "no_outcome_context" if outcome_status == "no_outcome_context" else "unavailable"
        return baseline

    target_signal_by_targets = {
        tuple(_string_list(signal.get("primary_targets"))): signal for signal in target_signals
    }
    priority_after_by_id: dict[str, int] = {}
    ordering_deltas: list[dict] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        if not candidate_id:
            continue
        before = _int_value(candidate.get("priority"))
        signal = _candidate_target_signal(candidate, target_signal_by_targets)
        if signal is None:
            delta, reason = 0, "no_target_signal"
            source_run_ids: list[str] = []
            preview_flags: list[str] = []
        else:
            delta, reason = _shadow_priority_delta(signal, preview_policy=preview_policy)
            source_run_ids = _string_list(signal.get("source_run_ids"))
            preview_flags = _string_list(signal.get("preview_flags"))
        after = min(max(before + delta, 0), 100)
        priority_after_by_id[candidate_id] = after
        ordering_deltas.append(
            {
                "candidate_id": candidate_id,
                "candidate_type": str(candidate.get("candidate_type", "")).strip(),
                "family": str(candidate.get("family", "")).strip(),
                "primary_targets": _string_list(candidate.get("primary_targets")),
                "priority_before": before,
                "priority_delta": delta,
                "priority_after": after,
                "source_run_ids": source_run_ids,
                "preview_flags": preview_flags,
                "reason": reason,
            }
        )

    shadow_order = _shadow_candidate_order(candidates, priority_after_by_id)
    baseline.update(
        {
            "status": "active",
            "shadow_order": shadow_order,
            "order_changed": baseline["current_order"] != shadow_order,
            "ordering_deltas": ordering_deltas,
        }
    )
    return baseline


def _populate_active_outcome_metrics_diagnostics(
    diagnostics: dict,
    *,
    preview_policy: dict,
    thresholds: dict,
    candidates: list[dict],
    outcome_report: dict,
    contexts: dict[tuple[str, ...], dict],
    source_report: str,
) -> dict:
    attempts_by_run = _outcome_attempts_by_run(outcome_report)
    rework_entries = _outcome_rework_entries(outcome_report)
    defect_escape_pairs = _outcome_defect_escape_pairs(outcome_report)
    target_signals = [
        _build_target_outcome_signal(
            context,
            attempts_by_run=attempts_by_run,
            rework_entries=rework_entries,
            defect_escape_pairs=defect_escape_pairs,
            thresholds=thresholds,
        )
        for _, context in sorted(contexts.items())
    ]
    candidates_with_context = sum(
        len(_string_list(signal.get("candidate_ids")))
        for signal in target_signals
        if _int_value(signal.get("attempt_count")) > 0
        or _int_value(signal.get("rework_count")) > 0
        or _int_value(signal.get("defect_escape_pair_count")) > 0
    )
    diagnostics["status"] = "active" if candidates_with_context else "no_outcome_context"
    diagnostics["candidates_with_outcome_context"] = candidates_with_context
    diagnostics["target_count"] = len(target_signals)
    diagnostics["target_signals"] = target_signals
    diagnostics["family_signals"] = _family_outcome_signals(target_signals)
    diagnostics["high_rework_targets"] = _high_rework_targets(target_signals, thresholds)
    diagnostics["defect_escape_pairs"] = [
        {
            "target": str(pair.get("target", "")).strip(),
            "promoted_run_id": str(pair.get("promoted_run_id", "")).strip(),
            "escaped_run_id": str(pair.get("escaped_run_id", "")).strip(),
            "escaped_decision": str(pair.get("escaped_decision", "")).strip(),
            "escaped_outcome": str(pair.get("escaped_outcome", "")).strip(),
        }
        for pair in defect_escape_pairs
    ]
    diagnostics["shadow_priority"] = _shadow_priority_diagnostics(
        preview_policy=preview_policy,
        candidates=candidates,
        target_signals=target_signals,
        global_signals=diagnostics["global_signals"],
        outcome_status=diagnostics["status"],
    )
    diagnostics["evidence_gaps"] = _outcome_metrics_evidence_gaps(
        preview_policy=preview_policy,
        source_report=source_report,
        outcome_report=outcome_report,
        candidates=candidates,
        target_signals=target_signals,
    )
    return diagnostics


def build_outcome_metrics_calibration_diagnostics(
    vault: Path,
    policy: dict,
    candidates: list[dict],
    *,
    load_optional_json_func: JsonLoader = load_optional_json,
) -> dict:
    preview_policy = outcome_metrics_preview_policy(policy)
    thresholds = _outcome_metrics_thresholds(preview_policy)
    if not bool(preview_policy.get("enabled", True)):
        diagnostics = _empty_outcome_metrics_calibration_diagnostics(
            preview_policy=preview_policy,
            thresholds=thresholds,
            status="disabled",
            candidate_count=0,
            candidates=[],
        )
        diagnostics["enabled"] = False
        return diagnostics

    source_report = str(preview_policy.get("source_report", DEFAULT_OUTCOME_METRICS_REPORT)).strip()
    source_report = source_report or DEFAULT_OUTCOME_METRICS_REPORT
    diagnostics = _empty_outcome_metrics_calibration_diagnostics(
        preview_policy=preview_policy,
        thresholds=thresholds,
        status="missing_outcome_metrics",
        candidate_count=len(candidates),
        candidates=candidates,
    )
    diagnostics["source_report"] = source_report
    if not candidates:
        diagnostics["status"] = "no_candidates"

    outcome_report = load_optional_json_func(vault / source_report)
    if not isinstance(outcome_report, dict):
        diagnostics["evidence_gaps"] = _outcome_metrics_evidence_gaps(
            preview_policy=preview_policy,
            source_report=source_report,
            outcome_report=outcome_report,
            candidates=candidates,
            target_signals=[],
        )
        return diagnostics
    if not isinstance(outcome_report.get("metrics"), dict):
        diagnostics["status"] = "invalid_outcome_metrics"
        diagnostics["evidence_gaps"] = _outcome_metrics_evidence_gaps(
            preview_policy=preview_policy,
            source_report=source_report,
            outcome_report=outcome_report,
            candidates=candidates,
            target_signals=[],
        )
        return diagnostics

    diagnostics["global_signals"] = _outcome_global_signals(outcome_report)
    diagnostics["shadow_priority"] = _shadow_priority_diagnostics(
        preview_policy=preview_policy,
        candidates=candidates,
        target_signals=[],
        global_signals=diagnostics["global_signals"],
        outcome_status=diagnostics["status"],
    )
    contexts = _target_contexts(candidates)
    if not contexts:
        diagnostics["status"] = "no_candidates"
        diagnostics["evidence_gaps"] = _outcome_metrics_evidence_gaps(
            preview_policy=preview_policy,
            source_report=source_report,
            outcome_report=outcome_report,
            candidates=candidates,
            target_signals=[],
        )
        diagnostics["shadow_priority"] = _shadow_priority_diagnostics(
            preview_policy=preview_policy,
            candidates=candidates,
            target_signals=[],
            global_signals=diagnostics["global_signals"],
            outcome_status=diagnostics["status"],
        )
        return diagnostics

    return _populate_active_outcome_metrics_diagnostics(
        diagnostics,
        preview_policy=preview_policy,
        thresholds=thresholds,
        candidates=candidates,
        outcome_report=outcome_report,
        contexts=contexts,
        source_report=source_report,
    )
