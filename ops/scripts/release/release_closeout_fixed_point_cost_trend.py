#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.runtime_context import RuntimeContext

DEFAULT_OUT = "ops/reports/release-closeout-fixed-point-cost-trend.json"
FIXED_POINT_REPORT_PATH = "ops/reports/release-closeout-fixed-point.json"
POLICY_PATH = "ops/policies/release-closeout-fixed-point.json"
PRODUCER = "ops.scripts.release_closeout_fixed_point_cost_trend"
SCHEMA_PATH = "ops/schemas/release-closeout-fixed-point-cost-trend.schema.json"
SOURCE_COMMAND = "make release-closeout-fixed-point-cost-trend"
DEFAULT_RETAINED_RUN_COUNT = 10


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _cost_policy(policy: dict[str, Any]) -> dict[str, Any]:
    raw = policy.get("cost_trend")
    cost_trend: dict[str, Any] = raw if isinstance(raw, dict) else {}
    thresholds_payload = cost_trend.get("thresholds")
    thresholds: dict[str, Any] = (
        thresholds_payload if isinstance(thresholds_payload, dict) else {}
    )
    default_payload = thresholds.get("default")
    default: dict[str, Any] = (
        default_payload if isinstance(default_payload, dict) else {}
    )
    writers_payload = thresholds.get("writers")
    writers: dict[str, Any] = (
        writers_payload if isinstance(writers_payload, dict) else {}
    )
    return {
        "retained_run_count": max(
            1,
            int(
                cost_trend.get("retained_run_count", DEFAULT_RETAINED_RUN_COUNT)
                or DEFAULT_RETAINED_RUN_COUNT
            ),
        ),
        "default": {
            "min_previous_samples": max(
                0, int(default.get("min_previous_samples", 1) or 0)
            ),
            "total_duration_ms_attention": max(
                0,
                int(default.get("total_duration_ms_attention", 0) or 0),
            ),
            "max_duration_ms_attention": max(
                0,
                int(default.get("max_duration_ms_attention", 0) or 0),
            ),
            "relative_total_duration_attention_multiplier": float(
                default.get("relative_total_duration_attention_multiplier", 0.0) or 0.0
            ),
            "minimum_relative_delta_ms": max(
                0,
                int(default.get("minimum_relative_delta_ms", 0) or 0),
            ),
        },
        "writers": {
            str(target): value
            for target, value in writers.items()
            if isinstance(value, dict)
        },
    }


def _threshold_for_target(policy: dict[str, Any], target: str) -> dict[str, Any]:
    default = dict(policy["default"])
    override = policy["writers"].get(target)
    if isinstance(override, dict):
        for key, value in override.items():
            if key in default:
                default[key] = value
    default["min_previous_samples"] = max(0, int(default["min_previous_samples"] or 0))
    default["total_duration_ms_attention"] = max(
        0, int(default["total_duration_ms_attention"] or 0)
    )
    default["max_duration_ms_attention"] = max(
        0, int(default["max_duration_ms_attention"] or 0)
    )
    default["relative_total_duration_attention_multiplier"] = float(
        default["relative_total_duration_attention_multiplier"] or 0.0
    )
    default["minimum_relative_delta_ms"] = max(
        0, int(default["minimum_relative_delta_ms"] or 0)
    )
    return default


def _sample_from_fixed_point(
    fixed_point: dict[str, Any],
    *,
    fixed_point_digest: str,
) -> dict[str, Any]:
    duration_summary = fixed_point.get("duration_summary")
    if not isinstance(duration_summary, dict):
        duration_summary = {}
    writer_costs = [
        {
            "name": str(item.get("name", "")).strip(),
            "target": str(item.get("target", "")).strip(),
            "run_count": int(item.get("run_count", 0) or 0),
            "total_duration_ms": int(item.get("total_duration_ms", 0) or 0),
            "average_duration_ms": int(item.get("average_duration_ms", 0) or 0),
            "max_duration_ms": int(item.get("max_duration_ms", 0) or 0),
        }
        for item in duration_summary.get("writer_costs", [])
        if isinstance(item, dict) and str(item.get("target", "")).strip()
    ]
    return {
        "fixed_point_report_path": FIXED_POINT_REPORT_PATH,
        "fixed_point_report_digest": fixed_point_digest,
        "fixed_point_generated_at": str(fixed_point.get("generated_at", "")).strip(),
        "fixed_point_status": str(fixed_point.get("status", "unknown")).strip()
        or "unknown",
        "fixed_point_converged": bool(fixed_point.get("converged", False)),
        "iteration_count": int(
            fixed_point.get(
                "iteration_count", duration_summary.get("iteration_count", 0)
            )
            or 0
        ),
        "command_run_count": int(duration_summary.get("command_run_count", 0) or 0),
        "total_duration_ms": int(duration_summary.get("total_duration_ms", 0) or 0),
        "writer_costs": writer_costs,
    }


def _previous_samples(
    previous_trend: dict[str, Any], current_digest: str
) -> list[dict[str, Any]]:
    samples = previous_trend.get("samples")
    if not isinstance(samples, list):
        return []
    return [
        item
        for item in samples
        if isinstance(item, dict)
        and str(item.get("fixed_point_report_digest", "")).strip() != current_digest
    ]


def _writer_cost_by_target(sample: dict[str, Any]) -> dict[str, dict[str, Any]]:
    costs = sample.get("writer_costs")
    if not isinstance(costs, list):
        return {}
    return {
        str(item.get("target", "")).strip(): item
        for item in costs
        if isinstance(item, dict) and str(item.get("target", "")).strip()
    }


def _writer_trends(
    samples: list[dict[str, Any]], cost_policy: dict[str, Any]
) -> list[dict[str, Any]]:
    if not samples:
        return []
    latest = samples[-1]
    previous = samples[:-1]
    previous_costs_by_sample = [_writer_cost_by_target(sample) for sample in previous]
    trends: list[dict[str, Any]] = []
    for target, latest_cost in _writer_cost_by_target(latest).items():
        previous_costs = [
            costs[target] for costs in previous_costs_by_sample if target in costs
        ]
        previous_sample_count = len(previous_costs)
        previous_average = (
            int(
                round(
                    sum(
                        int(item.get("total_duration_ms", 0) or 0)
                        for item in previous_costs
                    )
                    / previous_sample_count
                )
            )
            if previous_sample_count
            else 0
        )
        latest_total = int(latest_cost.get("total_duration_ms", 0) or 0)
        latest_max = int(latest_cost.get("max_duration_ms", 0) or 0)
        delta = latest_total - previous_average if previous_sample_count else 0
        ratio = (
            round(latest_total / previous_average, 3) if previous_average > 0 else 0.0
        )
        threshold = _threshold_for_target(cost_policy, target)
        breaches: list[str] = []
        if (
            threshold["total_duration_ms_attention"]
            and latest_total > threshold["total_duration_ms_attention"]
        ):
            breaches.append("total_duration_ms_attention")
        if (
            threshold["max_duration_ms_attention"]
            and latest_max > threshold["max_duration_ms_attention"]
        ):
            breaches.append("max_duration_ms_attention")
        if (
            previous_sample_count >= threshold["min_previous_samples"]
            and threshold["relative_total_duration_attention_multiplier"] > 0
            and previous_average > 0
            and ratio > threshold["relative_total_duration_attention_multiplier"]
            and delta >= threshold["minimum_relative_delta_ms"]
        ):
            breaches.append("relative_total_duration_attention_multiplier")
        trends.append(
            {
                "name": str(latest_cost.get("name", "")).strip(),
                "target": target,
                "latest_total_duration_ms": latest_total,
                "latest_average_duration_ms": int(
                    latest_cost.get("average_duration_ms", 0) or 0
                ),
                "latest_max_duration_ms": latest_max,
                "previous_sample_count": previous_sample_count,
                "previous_average_total_duration_ms": previous_average,
                "delta_from_previous_average_ms": delta,
                "ratio_to_previous_average": ratio,
                "threshold_status": "attention" if breaches else "pass",
                "breached_thresholds": breaches,
            }
        )
    return sorted(
        trends,
        key=lambda item: (-int(item["latest_total_duration_ms"]), str(item["target"])),
    )


def build_report(
    vault: Path,
    *,
    previous_path: str = DEFAULT_OUT,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    policy = _load_json(vault / POLICY_PATH)
    cost_policy = _cost_policy(policy)
    fixed_point_path = vault / FIXED_POINT_REPORT_PATH
    fixed_point, fixed_point_diagnostics = load_optional_json_object_with_diagnostics(
        fixed_point_path
    )
    if fixed_point_diagnostics.get("status") != "ok":
        raise FileNotFoundError(
            f"fixed-point report is required: {display_path(vault, fixed_point_path)}"
        )
    fixed_point_digest = _sha256_file(fixed_point_path)
    previous_trend, previous_diagnostics = load_optional_json_object_with_diagnostics(
        vault / previous_path
    )
    previous_digest = (
        _sha256_file(vault / previous_path) if (vault / previous_path).is_file() else ""
    )
    sample = _sample_from_fixed_point(
        fixed_point, fixed_point_digest=fixed_point_digest
    )
    retained_run_count = int(cost_policy["retained_run_count"])
    samples = [*_previous_samples(previous_trend, fixed_point_digest), sample][
        -retained_run_count:
    ]
    writer_trends = _writer_trends(samples, cost_policy)
    breached = [
        item for item in writer_trends if item["threshold_status"] == "attention"
    ]
    status = "attention" if breached else "pass"
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="release_closeout_fixed_point_cost_trend",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=vault / POLICY_PATH,
        schema_path=SCHEMA_PATH,
        source_paths=["ops/scripts/release_closeout_fixed_point_cost_trend.py"],
        file_inputs={"release_closeout_fixed_point": FIXED_POINT_REPORT_PATH},
        text_inputs={
            "retained_run_count": str(retained_run_count),
            "threshold_policy": json.dumps(cost_policy, sort_keys=True),
        },
        source_tree_excluded_files=(DEFAULT_OUT,),
    )
    return {
        **envelope,
        "vault": display_path(vault, vault),
        "policy": {
            "path": POLICY_PATH,
            "version": int(policy.get("version", 1) or 1),
        },
        "status": status,
        "retained_run_count": retained_run_count,
        "sample_count": len(samples),
        "previous_trend": {
            "path": previous_path,
            "load_status": str(previous_diagnostics.get("status", "unknown")),
            "digest": previous_digest,
        },
        "latest_sample": sample,
        "samples": samples,
        "writer_trends": writer_trends,
        "threshold_policy": cost_policy,
        "threshold_summary": {
            "status": status,
            "breached_writer_count": len(breached),
            "breached_writers": [str(item["target"]) for item in breached],
            "summary": (
                f"{len(breached)} fixed-point writer cost threshold breach(es)"
                if breached
                else "fixed-point writer costs are within configured thresholds"
            ),
        },
    }


def write_report(
    vault: Path, report: dict[str, Any], out_path: str | None = None
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release closeout fixed-point cost trend schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build rolling fixed-point finalizer cost trend evidence."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--previous", default=DEFAULT_OUT)
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, previous_path=args.previous)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.no_fail:
        return 0
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
