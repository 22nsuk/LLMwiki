from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.release.release_evidence_dashboard_render_runtime import (
    FIXED_POINT_COST_TREND_PATH,
    FIXED_POINT_PATH,
)


@dataclass(frozen=True)
class FinalizerEvidenceDigests:
    fixed_point_raw_digest: str
    cost_trend_raw_digest: str


@dataclass(frozen=True)
class FinalizerDurationSections:
    duration_summary: dict[str, Any]
    expensive_prerequisites: dict[str, Any]
    writer_costs: list[dict[str, Any]]
    threshold_summary: dict[str, Any]
    trend_latest_sample: dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finalizer_evidence_digests(vault: Path) -> FinalizerEvidenceDigests:
    fixed_point_path = vault / FIXED_POINT_PATH
    cost_trend_path = vault / FIXED_POINT_COST_TREND_PATH
    return FinalizerEvidenceDigests(
        fixed_point_raw_digest=_sha256_file(fixed_point_path)
        if fixed_point_path.is_file()
        else "",
        cost_trend_raw_digest=_sha256_file(cost_trend_path)
        if cost_trend_path.is_file()
        else "",
    )


def _missing_expensive_prerequisites(load_status: str) -> dict[str, Any]:
    return {
        "targets": [],
        "configured_target_count": 0,
        "observed_target_count": 0,
        "run_count": 0,
        "total_duration_ms": 0,
        "summary": f"fixed-point report load_status={load_status}",
    }


def _missing_finalizer_evidence_basis(
    digests: FinalizerEvidenceDigests, cost_trend_load_status: str
) -> dict[str, Any]:
    return {
        "fixed_point_report_path": FIXED_POINT_PATH,
        "fixed_point_report_raw_digest": digests.fixed_point_raw_digest,
        "current_fixed_point_report_raw_digest": digests.fixed_point_raw_digest,
        "fixed_point_generated_at": "",
        "cost_trend_path": FIXED_POINT_COST_TREND_PATH,
        "cost_trend_load_status": cost_trend_load_status,
        "cost_trend_raw_digest": digests.cost_trend_raw_digest,
        "cost_trend_sample_count": 0,
        "cost_trend_latest_fixed_point_raw_digest": "",
        "sampled_fixed_point_report_raw_digest": "",
        "basis_relation_to_current_fixed_point": "cost_trend_unavailable",
    }


def _missing_finalizer_duration_signal(
    load_status: str,
    cost_trend_load_status: str,
    digests: FinalizerEvidenceDigests,
) -> dict[str, Any]:
    return {
        "path": FIXED_POINT_PATH,
        "load_status": load_status,
        "fixed_point_report_status": "unknown",
        "status": "unknown",
        "execution_pass_count": 0,
        "command_run_count": 0,
        "total_duration_ms": 0,
        "writer_costs": [],
        "expensive_prerequisites": _missing_expensive_prerequisites(load_status),
        "threshold_summary": {
            "status": "not_evaluated",
            "breached_writer_count": 0,
            "breached_writers": [],
            "summary": "fixed-point cost thresholds were not evaluated",
        },
        "evidence_basis": _missing_finalizer_evidence_basis(
            digests, cost_trend_load_status
        ),
        "summary": "fixed-point duration evidence unavailable",
    }


def _finalizer_duration_sections(
    fixed_point: dict[str, Any], cost_trend: dict[str, Any]
) -> FinalizerDurationSections:
    duration = fixed_point.get("duration_summary")
    duration_summary = duration if isinstance(duration, dict) else {}
    expensive = duration_summary.get("expensive_prerequisites")
    threshold = cost_trend.get("threshold_summary")
    latest = cost_trend.get("latest_sample")
    return FinalizerDurationSections(
        duration_summary=duration_summary,
        expensive_prerequisites=expensive if isinstance(expensive, dict) else {},
        writer_costs=[
            item
            for item in duration_summary.get("writer_costs", [])
            if isinstance(item, dict)
        ],
        threshold_summary=threshold if isinstance(threshold, dict) else {},
        trend_latest_sample=latest if isinstance(latest, dict) else {},
    )


def _cost_trend_basis_relation(
    *,
    cost_trend_load_status: str,
    sampled_fixed_point_raw_digest: str,
    fixed_point_raw_digest: str,
) -> str:
    if cost_trend_load_status != "ok":
        return "cost_trend_unavailable"
    if not sampled_fixed_point_raw_digest:
        return "sample_missing"
    if sampled_fixed_point_raw_digest == fixed_point_raw_digest:
        return "sampled_current_fixed_point"
    return "sampled_different_fixed_point"


def _finalizer_threshold_status(threshold_summary: dict[str, Any]) -> str:
    status = (
        str(threshold_summary.get("status", "not_evaluated")).strip() or "not_evaluated"
    )
    return status if status in {"pass", "attention"} else "not_evaluated"


def _finalizer_signal_status(report_status: str, threshold_status: str) -> str:
    if threshold_status == "attention":
        return "attention"
    return "pass" if report_status == "pass" else report_status


def _writer_cost_records(writer_costs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(item.get("name", "")).strip(),
            "target": str(item.get("target", "")).strip(),
            "produces": [
                str(path).strip()
                for path in item.get("produces", [])
                if str(path).strip()
            ],
            "run_count": int(item.get("run_count", 0) or 0),
            "selected": bool(item.get("selected", False)),
            "total_duration_ms": int(item.get("total_duration_ms", 0) or 0),
            "average_duration_ms": int(item.get("average_duration_ms", 0) or 0),
            "max_duration_ms": int(item.get("max_duration_ms", 0) or 0),
        }
        for item in writer_costs
        if str(item.get("target", "")).strip()
    ]


def _expensive_prerequisites_payload(expensive: dict[str, Any]) -> dict[str, Any]:
    return {
        "targets": [
            str(target).strip()
            for target in expensive.get("targets", [])
            if str(target).strip()
        ],
        "configured_target_count": int(
            expensive.get("configured_target_count", 0) or 0
        ),
        "observed_target_count": int(expensive.get("observed_target_count", 0) or 0),
        "run_count": int(expensive.get("run_count", 0) or 0),
        "total_duration_ms": int(expensive.get("total_duration_ms", 0) or 0),
        "summary": str(expensive.get("summary", "")).strip()
        or "fixed-point expensive prerequisite duration evidence loaded",
    }


def _finalizer_threshold_summary_payload(
    threshold_summary: dict[str, Any],
    *,
    threshold_status: str,
    cost_trend_load_status: str,
) -> dict[str, Any]:
    return {
        "status": threshold_status,
        "breached_writer_count": int(
            threshold_summary.get("breached_writer_count", 0) or 0
        ),
        "breached_writers": [
            str(item).strip()
            for item in threshold_summary.get("breached_writers", [])
            if str(item).strip()
        ],
        "summary": str(threshold_summary.get("summary", "")).strip()
        or (
            "fixed-point cost trend thresholds loaded"
            if cost_trend_load_status == "ok"
            else f"fixed-point cost trend load_status={cost_trend_load_status}"
        ),
    }


def _finalizer_evidence_basis(
    fixed_point: dict[str, Any],
    cost_trend: dict[str, Any],
    sections: FinalizerDurationSections,
    digests: FinalizerEvidenceDigests,
    *,
    cost_trend_load_status: str,
    sampled_fixed_point_raw_digest: str,
    basis_relation: str,
) -> dict[str, Any]:
    return {
        "fixed_point_report_path": FIXED_POINT_PATH,
        "fixed_point_report_raw_digest": digests.fixed_point_raw_digest,
        "current_fixed_point_report_raw_digest": digests.fixed_point_raw_digest,
        "fixed_point_generated_at": str(fixed_point.get("generated_at", "")).strip(),
        "cost_trend_path": FIXED_POINT_COST_TREND_PATH,
        "cost_trend_load_status": cost_trend_load_status,
        "cost_trend_raw_digest": digests.cost_trend_raw_digest,
        "cost_trend_sample_count": int(cost_trend.get("sample_count", 0) or 0)
        if cost_trend_load_status == "ok"
        else 0,
        "cost_trend_latest_fixed_point_raw_digest": str(
            sections.trend_latest_sample.get("fixed_point_report_raw_digest", "")
        ).strip(),
        "sampled_fixed_point_report_raw_digest": sampled_fixed_point_raw_digest,
        "basis_relation_to_current_fixed_point": basis_relation,
    }


def finalizer_duration_signal(
    vault: Path,
    fixed_point: dict[str, Any],
    load_status: str,
    cost_trend: dict[str, Any],
    cost_trend_load_status: str,
) -> dict[str, Any]:
    digests = _finalizer_evidence_digests(vault)
    effective_load_status = load_status
    if load_status == "ok" and fixed_point.get("schema_version") != 2:
        effective_load_status = "unsupported_schema_version"
    effective_cost_trend_load_status = cost_trend_load_status
    if cost_trend_load_status == "ok" and cost_trend.get("schema_version") != 2:
        effective_cost_trend_load_status = "unsupported_schema_version"
    if effective_load_status != "ok":
        return _missing_finalizer_duration_signal(
            effective_load_status, effective_cost_trend_load_status, digests
        )
    sections = _finalizer_duration_sections(fixed_point, cost_trend)
    sampled_digest = str(
        sections.trend_latest_sample.get("fixed_point_report_raw_digest", "")
    ).strip()
    basis_relation = _cost_trend_basis_relation(
        cost_trend_load_status=effective_cost_trend_load_status,
        sampled_fixed_point_raw_digest=sampled_digest,
        fixed_point_raw_digest=digests.fixed_point_raw_digest,
    )
    threshold_status = _finalizer_threshold_status(sections.threshold_summary)
    report_status = str(fixed_point.get("status", "unknown")).strip() or "unknown"
    return {
        "path": FIXED_POINT_PATH,
        "load_status": effective_load_status,
        "fixed_point_report_status": report_status,
        "status": _finalizer_signal_status(report_status, threshold_status),
        "execution_pass_count": int(
            sections.duration_summary.get(
                "execution_pass_count",
                fixed_point.get("execution_pass_count", 0),
            )
            or 0
        ),
        "command_run_count": int(
            sections.duration_summary.get("command_run_count", 0) or 0
        ),
        "total_duration_ms": int(
            sections.duration_summary.get("total_duration_ms", 0) or 0
        ),
        "writer_costs": _writer_cost_records(sections.writer_costs),
        "expensive_prerequisites": _expensive_prerequisites_payload(
            sections.expensive_prerequisites
        ),
        "threshold_summary": _finalizer_threshold_summary_payload(
            sections.threshold_summary,
            threshold_status=threshold_status,
            cost_trend_load_status=effective_cost_trend_load_status,
        ),
        "evidence_basis": _finalizer_evidence_basis(
            fixed_point,
            cost_trend,
            sections,
            digests,
            cost_trend_load_status=effective_cost_trend_load_status,
            sampled_fixed_point_raw_digest=sampled_digest,
            basis_relation=basis_relation,
        ),
        "summary": str(sections.duration_summary.get("summary", "")).strip()
        or "fixed-point duration evidence loaded",
    }
