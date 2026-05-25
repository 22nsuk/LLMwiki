from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext

DEFAULT_OUT = "ops/reports/self-improvement-negative-lessons.json"
PRODUCER = "ops.scripts.self_improvement_negative_lessons"
SCHEMA_PATH = "ops/schemas/self-improvement-negative-lessons.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.self_improvement_negative_lessons --vault ."
ACTIVATION_REPORT_PATH = "ops/reports/learning_claim_activation_report.json"
SESSION_SYNOPSIS_PATH = "ops/reports/session-synopsis.json"
SOURCE_PATHS = [
    "ops/scripts/learning/self_improvement_negative_lessons.py",
    "ops/scripts/learning/learning_claim_activation_report.py",
    "ops/scripts/learning/session_synopsis.py",
]
SAFE_ID_RE = re.compile(r"[^a-z0-9_]+")


def _safe_id(value: str) -> str:
    text = SAFE_ID_RE.sub("_", value.lower()).strip("_")
    return text or "unknown"


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _evidence_digests(value: object) -> list[dict[str, Any]]:
    digests: list[dict[str, Any]] = []
    for item in _dict_list(value):
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        digests.append(
            {
                "path": path,
                "exists": bool(item.get("exists", False)),
                "sha256": str(item.get("sha256", "")).strip(),
                "status": str(item.get("status", "unknown")).strip() or "unknown",
            }
        )
    return digests


def _lesson_from_activation(pattern: dict[str, Any]) -> dict[str, Any] | None:
    pattern_id = str(pattern.get("pattern_id", "")).strip()
    if not pattern_id:
        return None
    occurrence_count = int(pattern.get("occurrence_count", 0) or 0)
    return {
        "lesson_id": _safe_id(pattern_id),
        "source": "learning_claim_activation.negative_learning_ledger",
        "decisions": _string_list(pattern.get("decisions")),
        "run_ids": _string_list(pattern.get("run_ids")),
        "occurrence_count": max(1, occurrence_count),
        "forbidden_repeat": str(pattern.get("forbidden_repeat", "")).strip(),
        "repair_target": str(pattern.get("repair_target", "")).strip(),
        "evidence_digests": _evidence_digests(pattern.get("evidence_digests")),
        "repeat_policy": "do_not_repeat_until_repaired",
        "backlog_candidate": occurrence_count >= 2,
    }


def _lesson_from_synopsis(pattern: dict[str, Any]) -> dict[str, Any] | None:
    pattern_id = str(pattern.get("id", "")).strip()
    if not pattern_id:
        return None
    occurrence_count = int(pattern.get("occurrence_count", 0) or 0)
    return {
        "lesson_id": _safe_id(pattern_id),
        "source": "session_synopsis.forbidden_repeat_patterns",
        "decisions": _string_list(pattern.get("decisions")),
        "run_ids": _string_list(pattern.get("run_ids")),
        "occurrence_count": max(1, occurrence_count),
        "forbidden_repeat": str(pattern.get("forbidden_repeat", "")).strip(),
        "repair_target": str(pattern.get("repair_target", "")).strip(),
        "evidence_digests": [],
        "repeat_policy": "do_not_repeat_until_repaired",
        "backlog_candidate": occurrence_count >= 2,
    }


def collect_lessons(
    vault: Path,
    *,
    activation_report_path: str = ACTIVATION_REPORT_PATH,
    session_synopsis_path: str = SESSION_SYNOPSIS_PATH,
) -> list[dict[str, Any]]:
    activation = load_optional_json_object(vault / activation_report_path)
    synopsis = load_optional_json_object(vault / session_synopsis_path)
    lessons_by_id: dict[str, dict[str, Any]] = {}
    ledger = activation.get("negative_learning_ledger")
    ledger = ledger if isinstance(ledger, dict) else {}
    for pattern in _dict_list(ledger.get("patterns")):
        lesson = _lesson_from_activation(pattern)
        if lesson is not None:
            lessons_by_id[lesson["lesson_id"]] = lesson
    for pattern in _dict_list(synopsis.get("forbidden_repeat_patterns")):
        lesson = _lesson_from_synopsis(pattern)
        if lesson is None:
            continue
        existing = lessons_by_id.get(lesson["lesson_id"])
        if existing is None:
            lessons_by_id[lesson["lesson_id"]] = lesson
            continue
        existing["source"] = "learning_claim_activation.negative_learning_ledger+session_synopsis"
        existing["occurrence_count"] = max(existing["occurrence_count"], lesson["occurrence_count"])
        existing["backlog_candidate"] = bool(
            existing["backlog_candidate"] or lesson["backlog_candidate"]
        )
    return sorted(lessons_by_id.values(), key=lambda item: item["lesson_id"])


def _status(lessons: list[dict[str, Any]]) -> str:
    return "attention" if lessons else "pass"


def _next_action(lessons: list[dict[str, Any]], backlog_candidates: list[dict[str, Any]]) -> str:
    if backlog_candidates:
        return "Promote backlog candidates to remediation-backlog before rerunning the same blocker pattern."
    if lessons:
        return "Negative lessons are advisory only; no repeated backlog candidates detected."
    return "No negative learning lessons detected."


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
    activation_report_path: str = ACTIVATION_REPORT_PATH,
    session_synopsis_path: str = SESSION_SYNOPSIS_PATH,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    lessons = collect_lessons(
        vault,
        activation_report_path=activation_report_path,
        session_synopsis_path=session_synopsis_path,
    )
    backlog_candidates = [lesson for lesson in lessons if lesson["backlog_candidate"]]
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="self_improvement_negative_lessons",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=SOURCE_PATHS,
            file_inputs={
                "learning_claim_activation": activation_report_path,
                "session_synopsis": session_synopsis_path,
            },
            source_tree_excluded_files=(DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": _status(lessons),
        "mode": "advisory",
        "gate_effect": "blocks_repeat_only",
        "summary": {
            "lesson_count": len(lessons),
            "backlog_candidate_count": len(backlog_candidates),
            "source_activation_status": str(
                activation_status(vault, activation_report_path=activation_report_path)
            ),
            "next_action": _next_action(lessons, backlog_candidates),
        },
        "lessons": lessons,
        "inputs": {
            "learning_claim_activation": activation_report_path,
            "session_synopsis": session_synopsis_path,
        },
    }


def activation_status(vault: Path, *, activation_report_path: str = ACTIVATION_REPORT_PATH) -> str:
    activation = load_optional_json_object(vault / activation_report_path)
    return str(activation.get("status", "missing")).strip() or "missing"


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="self-improvement negative lessons schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build standalone negative learning lessons report.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--learning-claim-activation", default=ACTIVATION_REPORT_PATH)
    parser.add_argument("--session-synopsis", default=SESSION_SYNOPSIS_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        policy_path=args.policy_path,
        activation_report_path=args.learning_claim_activation,
        session_synopsis_path=args.session_synopsis,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
