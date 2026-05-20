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
GOAL_RUN_STATUS_PATH = "ops/reports/goal-run-status.json"
INPUT_PATHS = {
    "auto_improve_readiness": "ops/reports/auto-improve-readiness.json",
    "goal_run_status": GOAL_RUN_STATUS_PATH,
    "learning_delta_scoreboard": "ops/reports/learning-delta-scoreboard.json",
    "learning_claim_activation": "ops/reports/learning_claim_activation_report.json",
    "source_package_clean_extract": "ops/reports/source-package-clean-extract.json",
    "task_observations": "ops/reports/task-improvement-observations/task-20260515-reconciled-improvement-plan/improvement-observations.json",
}
DERIVED_REMEDIATION_BACKLOG_BLOCKER_IDS = {
    "goal_status_promotion_blocked_by_remediation_backlog_open",
    "promotion_blocked_by_remediation_backlog_open",
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


def _goal_profile_ladder(status_report: dict[str, Any]) -> dict[str, Any]:
    profile_ladder = status_report.get("profile_ladder")
    if not isinstance(profile_ladder, dict):
        return {
            "status": "missing",
            "current_profile": "",
            "run_profile": "",
            "verified_profiles": [],
            "highest_verified_profile": "unverified",
            "next_profile_required": "",
            "profile_verified_by_promotion_guard": "unverified",
            "profile_guard_consistent": False,
            "sustained_claim_allowed": False,
            "missing_evidence": [],
        }

    missing_evidence: list[dict[str, Any]] = []
    for profile in _dict_list(profile_ladder.get("profiles")):
        profile_name = str(profile.get("profile", "")).strip()
        for evidence in _dict_list(profile.get("evidence_paths")):
            evidence_status = str(evidence.get("status", "")).strip()
            if evidence_status == "present":
                continue
            evidence_path = str(evidence.get("path", "")).strip()
            if not evidence_path:
                continue
            missing_evidence.append(
                {
                    "profile": profile_name,
                    "path": evidence_path,
                    "status": evidence_status or "missing",
                }
            )

    return {
        "status": str(profile_ladder.get("status", "missing")).strip() or "missing",
        "current_profile": str(profile_ladder.get("current_profile", "")).strip(),
        "run_profile": str(profile_ladder.get("run_profile", "")).strip(),
        "verified_profiles": _string_list(profile_ladder.get("verified_profiles")),
        "highest_verified_profile": str(
            profile_ladder.get("highest_verified_profile", "unverified")
        ).strip()
        or "unverified",
        "next_profile_required": str(profile_ladder.get("next_profile_required", "")).strip(),
        "profile_verified_by_promotion_guard": str(
            profile_ladder.get("profile_verified_by_promotion_guard", "unverified")
        ).strip()
        or "unverified",
        "profile_guard_consistent": bool(
            profile_ladder.get("profile_guard_consistent", False)
        ),
        "sustained_claim_allowed": bool(
            profile_ladder.get("sustained_claim_allowed", False)
        ),
        "missing_evidence": missing_evidence[:8],
    }


def _goal_status_blockers(
    status_report: dict[str, Any],
    profile_ladder: dict[str, Any],
    *,
    suppressed_blocker_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    next_profile = str(profile_ladder.get("next_profile_required", "")).strip()
    suppressed_ids = suppressed_blocker_ids or set()
    for blocker in _string_list(status_report.get("blockers")):
        normalized_blocker_id = "_".join(
            blocker.lower().replace("-", " ").replace("/", " ").split()
        )
        if normalized_blocker_id in suppressed_ids:
            continue
        blocker_id = "goal_status_" + normalized_blocker_id
        if not blocker_id.strip("_"):
            continue
        if blocker_id in DERIVED_REMEDIATION_BACKLOG_BLOCKER_IDS:
            continue
        repair_target = "Refresh goal run status and close the active blocker before resuming."
        if blocker == "profile ladder incomplete":
            repair_target = (
                f"Collect bounded runtime evidence for next_profile_required={next_profile}."
                if next_profile
                else "Collect bounded runtime evidence for the next profile."
            )
        elif "sealed authority" in blocker:
            repair_target = "Refresh sealed authority preflight evidence before promotion."
        blockers.append(
            {
                "id": blocker_id,
                "source": "goal_run_status.blockers",
                "status": "open",
                "reason": blocker,
                "repair_target": repair_target,
            }
        )
    return blockers


def _active_goal_link(status_report: dict[str, Any]) -> dict[str, Any]:
    if not status_report:
        return {
            "link_status": "missing",
            "report_path": GOAL_RUN_STATUS_PATH,
            "contract_id": "",
            "run_id": "",
            "run_status": "",
            "profile": "",
            "promotion_status": "",
            "can_promote_result": False,
            "checkpoint_status": "",
            "periodic_evidence_status": "",
            "audit_log_path": "",
            "resume_metadata_path": "",
            "next_action": "Run make auto-improve-goal-status before resuming a goal run.",
        }
    goal = status_report.get("goal")
    goal = goal if isinstance(goal, dict) else {}
    run = status_report.get("run")
    run = run if isinstance(run, dict) else {}
    health = status_report.get("health")
    health = health if isinstance(health, dict) else {}
    artifacts = status_report.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    periodic_evidence = status_report.get("periodic_evidence")
    periodic_evidence = periodic_evidence if isinstance(periodic_evidence, dict) else {}
    return {
        "link_status": "linked",
        "report_path": GOAL_RUN_STATUS_PATH,
        "contract_id": str(goal.get("contract_id", "")).strip(),
        "run_id": str(run.get("run_id", "")).strip(),
        "run_status": str(run.get("status", "")).strip(),
        "profile": str(run.get("profile", "")).strip(),
        "promotion_status": str(health.get("promotion_status", "")).strip(),
        "can_promote_result": bool(health.get("can_promote_result", False)),
        "checkpoint_status": str(health.get("checkpoint_status", "")).strip(),
        "periodic_evidence_status": str(periodic_evidence.get("status", "")).strip(),
        "audit_log_path": str(artifacts.get("audit_log_path", "")).strip(),
        "resume_metadata_path": str(artifacts.get("resume_metadata_path", "")).strip(),
        "next_action": (
            "Resume via the linked goal status artifacts before starting a separate session."
            if str(run.get("status", "")).strip() in {"running", "paused", "blocked"}
            else "Refresh goal status before starting or resuming a goal run."
        ),
    }


def _recent_blockers(inputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    readiness = inputs["auto_improve_readiness"]
    activation = inputs["learning_claim_activation"]
    goal_status = inputs["goal_run_status"]
    goal_profile_ladder = _goal_profile_ladder(goal_status)
    readiness_blockers: list[dict[str, Any]] = []
    readiness_blocker_ids: set[str] = set()
    for blocker in _dict_list(readiness.get("promotion_blockers")):
        blocker_id = str(blocker.get("id", "")).strip()
        if not blocker_id:
            continue
        if blocker_id in DERIVED_REMEDIATION_BACKLOG_BLOCKER_IDS:
            continue
        readiness_blocker_ids.add(blocker_id)
        readiness_blockers.append(
            {
                "id": blocker_id,
                "source": "auto_improve_readiness.promotion_blockers",
                "status": str(blocker.get("status", "open")).strip() or "open",
                "reason": str(blocker.get("reason", "")).strip(),
                "repair_target": str(blocker.get("recommended_next_step", "")).strip(),
            }
        )
    blockers.extend(
        _goal_status_blockers(
            goal_status,
            goal_profile_ladder,
            suppressed_blocker_ids=readiness_blocker_ids,
        )
    )
    blockers.extend(readiness_blockers)
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
    return list(deduped.values())


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
    profile_ladder: dict[str, Any],
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
            "make auto-improve-goal-status",
            "make session-synopsis",
            "make remediation-backlog",
            "make static",
            "make test-public",
            "make auto-improve-goal-preflight",
            "make auto-improve-goal-run",
            "make goal-profile-verification",
        ],
        "stop_conditions": [
            "Do not promote while promotion_allowed is false.",
            "Do not claim learning improvement while claim_wording_allowed is false.",
            "Do not claim 5d sustained runtime while sustained_claim_allowed is false.",
            "Do not advance beyond next_profile_required without elapsed runtime evidence for that profile.",
            "Do not repeat forbidden patterns until their repair_target is closed.",
        ],
        "target_profile": str(profile_ladder.get("next_profile_required", "")).strip(),
        "profile_ladder_status": str(profile_ladder.get("status", "")).strip(),
        "sustained_claim_allowed": bool(profile_ladder.get("sustained_claim_allowed", False)),
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
    goal_profile_ladder = _goal_profile_ladder(inputs["goal_run_status"])
    active_goal = _active_goal_link(inputs["goal_run_status"])
    next_session = _next_session_entrypoint(
        inputs,
        blockers=blockers,
        forbidden_patterns=forbidden_patterns,
        evidence_gaps=evidence_gaps,
        profile_ladder=goal_profile_ladder,
    )
    profile_ladder_clear = (
        goal_profile_ladder["status"] == "complete"
        and goal_profile_ladder["sustained_claim_allowed"]
    )
    status = (
        "pass"
        if not blockers and not evidence_gaps and profile_ladder_clear
        else "attention"
    )
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
            "active_goal_id": active_goal["contract_id"],
            "active_goal_run_id": active_goal["run_id"],
            "active_goal_link_status": active_goal["link_status"],
            "goal_profile_ladder_status": goal_profile_ladder["status"],
            "goal_next_profile_required": goal_profile_ladder["next_profile_required"],
            "sustained_claim_allowed": goal_profile_ladder["sustained_claim_allowed"],
            "next_action": next_session["recommended_next_action"],
        },
        "recent_blockers": blockers,
        "last_success_patterns": success_patterns,
        "forbidden_repeat_patterns": forbidden_patterns,
        "recommended_seed_runs": seed_runs,
        "evidence_gaps": evidence_gaps,
        "source_package_replay": source_package_replay,
        "active_goal": active_goal,
        "goal_profile_ladder": goal_profile_ladder,
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
