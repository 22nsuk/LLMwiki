from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import load_optional_json_object, write_schema_validated_json
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema


DEFAULT_ACTIVATION_REPORT = "ops/reports/learning_claim_activation_report.json"
DEFAULT_OUT = "ops/reports/self-improvement-negative-lessons.json"
SCHEMA_PATH = "ops/schemas/self-improvement-negative-lessons.schema.json"
POLICY_PATH = "ops/policies/wiki-maintainer-policy.yaml"


def _artifact_envelope(
    vault: Path,
    *,
    generated_at: str,
    activation_report: str,
) -> dict[str, Any]:
    _policy, resolved_policy_path = load_policy(vault, POLICY_PATH)
    return build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="self_improvement_negative_lessons",
        producer="ops.scripts.self_improvement_negative_lessons",
        source_command="python -m ops.scripts.self_improvement_negative_lessons",
        resolved_policy_path=resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=[
            "ops/scripts/mechanism/self_improvement_negative_lessons.py",
            SCHEMA_PATH,
        ],
        file_inputs={"activation_report": activation_report},
    )


def _normalize_pattern(pattern: dict[str, Any], index: int) -> dict[str, Any]:
    pattern_id = str(pattern.get("id") or pattern.get("pattern_id") or "").strip()
    status = str(pattern.get("status") or "").strip() or "open"
    normalized = dict(pattern)
    normalized["id"] = pattern_id or f"negative-pattern-{index}"
    normalized["status"] = status
    return normalized


def build_report(
    vault: Path,
    *,
    activation_report: str = DEFAULT_ACTIVATION_REPORT,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    activation = load_optional_json_object(vault / activation_report)
    ledger = activation.get("negative_learning_ledger")
    ledger = ledger if isinstance(ledger, dict) else {}
    patterns = ledger.get("patterns", [])
    patterns = [item for item in patterns if isinstance(item, dict)] if isinstance(patterns, list) else []
    normalized_patterns = [
        _normalize_pattern(pattern, index)
        for index, pattern in enumerate(patterns, start=1)
    ]
    generated_at = runtime_context.isoformat_z()
    report = {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "self_improvement_negative_lessons",
        "generated_at": generated_at,
        "producer": "ops.scripts.self_improvement_negative_lessons",
        "status": "attention" if normalized_patterns else "pass",
        "source_activation_report": activation_report,
        "summary": {
            "pattern_count": len(normalized_patterns),
            "gate_effect": "none",
        },
        "patterns": normalized_patterns,
    }
    report.update(
        _artifact_envelope(
            vault,
            generated_at=generated_at,
            activation_report=activation_report,
        )
    )
    return report


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_validated_json(
        vault / out_path,
        report,
        load_schema(vault / SCHEMA_PATH),
        context="self-improvement negative lessons schema validation failed",
        trailing_newline=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract standalone negative learning lessons.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--activation-report", default=DEFAULT_ACTIVATION_REPORT)
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, activation_report=args.activation_report)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
