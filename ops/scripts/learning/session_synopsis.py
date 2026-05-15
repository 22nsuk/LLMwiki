from __future__ import annotations

import argparse
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


DEFAULT_OUT = "ops/reports/session-synopsis.json"
PRODUCER = "ops.scripts.session_synopsis"
SCHEMA_PATH = "ops/schemas/session-synopsis.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.session_synopsis --vault ."
SOURCE_PATHS = ["ops/scripts/learning/session_synopsis.py"]
INPUT_PATHS = {
    "auto_improve_readiness": "ops/reports/auto-improve-readiness.json",
    "learning_delta_scoreboard": "ops/reports/learning-delta-scoreboard.json",
    "learning_claim_activation": "ops/reports/learning_claim_activation_report.json",
    "source_package_clean_extract": "ops/reports/source-package-clean-extract.json",
    "task_observations": "ops/reports/task-improvement-observations/task-20260515-reconciled-improvement-plan/improvement-observations.json",
}


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _load_inputs(vault: Path) -> dict[str, dict[str, Any]]:
    return {
        key: load_optional_json_object(vault / rel_path)
        for key, rel_path in INPUT_PATHS.items()
    }


def _recent_blockers(inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    readiness = inputs["auto_improve_readiness"]
    activation = inputs["learning_claim_activation"]
    for blocker in _dict_list(readiness.get("promotion_blockers")):
        blocker_id = str(blocker.get("id", "")).strip()
        if not blocker_id:
            continue
        blockers.append(
            {
                "id": blocker_id,
                "source": "auto_improve_readiness.promotion_blockers",
                "status": str(blocker.get("status", "open")).strip() or "open",
                "reason": str(blocker.get("reason", "")).strip(),
                "repair_target": str(blocker.get("recommended_next_step", "")).strip(),
            }
        )
    for predicate in _dict_list(activation.get("blocked_predicates")):
        predicate_id = str(predicate.get("id", "")).strip()
        if not predicate_id:
            continue
        blockers.append(
            {
                "id": predicate_id,
                "source": "learning_claim_activation.blocked_predicates",
                "status": str(predicate.get("status", "blocked")).strip() or "blocked",
                "reason": str(predicate.get("observed_value", "")).strip(),
                "repair_target": str(predicate.get("repair_target", "")).strip(),
            }
        )

    deduped: dict[str, dict[str, Any]] = {}
    for blocker in blockers:
        deduped.setdefault(blocker["id"], blocker)
    return list(deduped.values())[:5]


def _last_success_patterns(inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    scoreboard = inputs["learning_delta_scoreboard"]
    observations = inputs["task_observations"]
    summary = scoreboard.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    confirmed = summary.get("confirmed_evidence_summary")
    confirmed = confirmed if isinstance(confirmed, dict) else {}
    patterns: list[dict[str, Any]] = []
    for run_id in _string_list(confirmed.get("selected_valid_run_ids"))[:3]:
        patterns.append(
            {
                "id": f"selected_valid_run:{run_id}",
                "source": "learning_delta_scoreboard.confirmed_evidence_summary",
                "summary": "Selected as valid same-family learning evidence.",
                "evidence": [run_id],
            }
        )
    for observation in _dict_list(observations.get("observations")):
        if str(observation.get("status", "")).strip() != "automated":
            continue
        observation_id = str(observation.get("observation_id", "")).strip()
        if not observation_id:
            continue
        patterns.append(
            {
                "id": observation_id,
                "source": "task_improvement_observations",
                "summary": str(observation.get("suggested_followup", "")).strip(),
                "evidence": [str(observation.get("surface", "")).strip()],
            }
        )
    return patterns[-5:]


def _forbidden_repeat_patterns(inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    activation = inputs["learning_claim_activation"]
    ledger = activation.get("negative_learning_ledger")
    ledger = ledger if isinstance(ledger, dict) else {}
    patterns: list[dict[str, Any]] = []
    for pattern in _dict_list(ledger.get("patterns")):
        pattern_id = str(pattern.get("pattern_id", "")).strip()
        if not pattern_id:
            continue
        patterns.append(
            {
                "id": pattern_id,
                "decisions": _string_list(pattern.get("decisions")),
                "run_ids": _string_list(pattern.get("run_ids")),
                "occurrence_count": int(pattern.get("occurrence_count", 0) or 0),
                "forbidden_repeat": str(pattern.get("forbidden_repeat", "")).strip(),
                "repair_target": str(pattern.get("repair_target", "")).strip(),
            }
        )
    return patterns[:5]


def _recommended_seed_runs(inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    readiness = inputs["auto_improve_readiness"]
    fallback = readiness.get("fallback")
    fallback = fallback if isinstance(fallback, dict) else {}
    seed_runs = _string_list(fallback.get("seed_runs"))
    scoreboard = inputs["learning_delta_scoreboard"]
    summary = scoreboard.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    confirmed = summary.get("confirmed_evidence_summary")
    confirmed = confirmed if isinstance(confirmed, dict) else {}
    if not seed_runs:
        seed_runs = _string_list(confirmed.get("selected_valid_run_ids"))
    return [
        {
            "run_id": run_id,
            "source": "auto_improve_readiness.fallback.seed_runs"
            if run_id in _string_list(fallback.get("seed_runs"))
            else "learning_delta_scoreboard.selected_valid_run_ids",
            "reason": "Reusable bounded evidence candidate for the next narrow run.",
        }
        for run_id in seed_runs[:5]
    ]


def _evidence_gaps(inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    activation = inputs["learning_claim_activation"]
    anti_slop = activation.get("anti_slop_preview_ledger")
    anti_slop = anti_slop if isinstance(anti_slop, dict) else {}
    for axis in _dict_list(anti_slop.get("axes")):
        if str(axis.get("status", "")).strip() == "pass":
            continue
        gaps.append(
            {
                "id": str(axis.get("axis", "")).strip(),
                "source": "learning_claim_activation.anti_slop_preview_ledger",
                "current": str(axis.get("current", "")).strip(),
                "required": str(axis.get("required", "")).strip(),
                "repair_target": str(axis.get("repair_target", "")).strip(),
            }
        )
    for predicate in _dict_list(activation.get("blocked_predicates")):
        gaps.append(
            {
                "id": str(predicate.get("id", "")).strip(),
                "source": "learning_claim_activation.blocked_predicates",
                "current": str(predicate.get("observed_value", "")).strip(),
                "required": str(predicate.get("required_condition", "")).strip(),
                "repair_target": str(predicate.get("repair_target", "")).strip(),
            }
        )
    return [gap for gap in gaps if gap["id"]][:8]


def _source_package_replay(inputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_package = inputs["source_package_clean_extract"]
    return {
        "status": str(source_package.get("status", "missing")).strip() or "missing",
        "report_path": INPUT_PATHS["source_package_clean_extract"],
        "profile": "source-package/release-archive",
        "replay_command": "make release-source-package-check",
        "summary": "Use the profile-aware source package check before treating distribution evidence as replayable.",
    }


def _next_session_entrypoint(
    inputs: dict[str, dict[str, Any]],
    *,
    blockers: list[dict[str, Any]],
    forbidden_patterns: list[dict[str, Any]],
    evidence_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness = inputs["auto_improve_readiness"]
    activation = inputs["learning_claim_activation"]
    next_action = str(readiness.get("next_action", "")).strip()
    if not next_action:
        next_action = "Refresh auto-improve readiness and session synopsis before continuing."
    return {
        "promotion_allowed": bool(readiness.get("can_promote_result", False)),
        "claim_wording_allowed": bool(
            activation.get("summary", {}).get("claim_wording_allowed", False)
            if isinstance(activation.get("summary"), dict)
            else False
        ),
        "recommended_next_action": next_action,
        "first_commands": [
            "make session-synopsis",
            "make static",
            "make test-public",
        ],
        "stop_conditions": [
            "Do not promote while promotion_allowed is false.",
            "Do not claim learning improvement while claim_wording_allowed is false.",
            "Do not repeat forbidden patterns until their repair_target is closed.",
        ],
        "open_blocker_count": len(blockers),
        "forbidden_pattern_count": len(forbidden_patterns),
        "evidence_gap_count": len(evidence_gaps),
    }


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    inputs = _load_inputs(vault)
    blockers = _recent_blockers(inputs)
    success_patterns = _last_success_patterns(inputs)
    forbidden_patterns = _forbidden_repeat_patterns(inputs)
    seed_runs = _recommended_seed_runs(inputs)
    evidence_gaps = _evidence_gaps(inputs)
    source_package_replay = _source_package_replay(inputs)
    next_session = _next_session_entrypoint(
        inputs,
        blockers=blockers,
        forbidden_patterns=forbidden_patterns,
        evidence_gaps=evidence_gaps,
    )
    status = "pass" if not blockers and not evidence_gaps else "attention"
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="session_synopsis",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=SOURCE_PATHS,
            file_inputs=INPUT_PATHS,
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "summary": {
            "recent_blocker_count": len(blockers),
            "last_success_pattern_count": len(success_patterns),
            "forbidden_repeat_pattern_count": len(forbidden_patterns),
            "recommended_seed_run_count": len(seed_runs),
            "evidence_gap_count": len(evidence_gaps),
            "source_package_replay_status": source_package_replay["status"],
            "next_action": next_session["recommended_next_action"],
        },
        "recent_blockers": blockers,
        "last_success_patterns": success_patterns,
        "forbidden_repeat_patterns": forbidden_patterns,
        "recommended_seed_runs": seed_runs,
        "evidence_gaps": evidence_gaps,
        "source_package_replay": source_package_replay,
        "next_session_entrypoint": next_session,
        "inputs": INPUT_PATHS,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="session synopsis report schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the canonical next-session synopsis report")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
