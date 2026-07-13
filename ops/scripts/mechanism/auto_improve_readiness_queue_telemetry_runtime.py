from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_io_runtime import load_optional_json_object
from ops.scripts.core.policy_runtime import report_path

from .auto_improve_readiness_constants_runtime import (
    FALLBACK_PRIMARY_TARGETS,
    LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_REPORT_REL_PATH,
    SAME_EVAL_PROPOSAL_FAILURE_MODES,
)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def matching_fallback_seed_runs(vault: Path) -> list[str]:
    runs_dir = vault / "runs"
    if not runs_dir.exists():
        return []

    matched: list[str] = []
    for path in sorted(runs_dir.glob("*/run-telemetry.json")):
        payload = load_optional_json_object(path)
        if not payload or not bool(payload.get("finalized")):
            continue
        primary_targets = _string_list(payload.get("primary_targets"))
        if primary_targets == FALLBACK_PRIMARY_TARGETS:
            matched.append(path.parent.name)
    return matched


def _safe_run_id(value: object) -> str | None:
    run_id = str(value).strip() if isinstance(value, str) else ""
    if (
        not run_id
        or run_id in {".", ".."}
        or any(character in run_id for character in "/\\*?[]")
    ):
        return None
    return run_id


def _telemetry_path_for_run(vault: Path, run_id: str) -> Path | None:
    safe_run_id = _safe_run_id(run_id)
    if safe_run_id is None:
        return None
    candidates = [
        vault / "runs" / safe_run_id / "run-telemetry.json",
        vault / "runs" / "archive" / safe_run_id / "run-telemetry.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted(
        (vault / "runs").glob(f"**/{safe_run_id}/run-telemetry.json")
    )
    return matches[0] if matches else None


def _same_eval_proposal_run_ids(mutation_proposal_report: dict[str, Any]) -> list[str]:
    run_ids: list[str] = []
    proposals = mutation_proposal_report.get("proposals")
    if not isinstance(proposals, list):
        return run_ids
    for proposal in proposals:
        if (
            not isinstance(proposal, dict)
            or _string_list(proposal.get("blocked_by"))
            or str(proposal.get("failure_mode", "")).strip()
            not in SAME_EVAL_PROPOSAL_FAILURE_MODES
        ):
            continue
        for run_id in proposal.get("run_ids", []):
            value = _safe_run_id(run_id)
            if value and value not in run_ids:
                run_ids.append(value)
    return run_ids


def readiness_run_telemetry_paths(
    vault: Path,
    mutation_proposal_report: dict[str, Any],
) -> list[str]:
    runs_dir = vault / "runs"
    paths = {
        report_path(vault, path)
        for path in runs_dir.glob("*/run-telemetry.json")
        if path.is_file()
    }
    for run_id in _same_eval_proposal_run_ids(mutation_proposal_report):
        paths.update(
            {
                f"runs/{run_id}/run-telemetry.json",
                f"runs/archive/{run_id}/run-telemetry.json",
            }
        )
        telemetry_path = _telemetry_path_for_run(vault, run_id)
        if telemetry_path is not None:
            paths.add(report_path(vault, telemetry_path))
    return sorted(paths)


def _coverage_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _legacy_reconstruction_by_run(vault: Path) -> dict[str, dict[str, Any]]:
    report = load_optional_json_object(
        vault / LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_REPORT_REL_PATH
    )
    rows = report.get("run_reconstructions")
    if not isinstance(rows, list):
        return {}
    by_run: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        run_id = str(row.get("run_id", "")).strip()
        status = str(row.get("reconstruction_status", "")).strip()
        if run_id and status in {"not_needed", "reconstructed"}:
            by_run[run_id] = row
    return by_run


def _legacy_secondary_axes_present(row: dict[str, Any]) -> bool:
    return bool(row.get("parsed_strict_secondary_improvement_present")) and bool(
        _string_list(row.get("parsed_secondary_axes"))
    )


def _legacy_behavior_delta_digest_present(row: dict[str, Any]) -> bool:
    digest = str(row.get("telemetry_behavior_delta_digest", "")).strip()
    artifact_sha = str(row.get("behavior_delta_artifact_sha256", "")).strip()
    return bool(digest or artifact_sha)


def _legacy_decision_reason_code_present(
    telemetry: dict[str, Any],
    row: dict[str, Any],
) -> bool:
    decision = telemetry.get("decision_record")
    if not isinstance(decision, dict):
        return False
    reason_code = str(decision.get("reason_code", "")).strip()
    source_rule = str(decision.get("source_rule", "")).strip()
    if reason_code != "equal_score_secondary_eligibility" and source_rule != (
        "equal_score_secondary_eligibility"
    ):
        return False
    return _legacy_secondary_axes_present(row)


def same_eval_telemetry_summary(
    vault: Path, mutation_proposal_report: dict[str, Any]
) -> dict[str, Any]:
    run_ids = _same_eval_proposal_run_ids(mutation_proposal_report)
    legacy_rows = _legacy_reconstruction_by_run(vault)
    runs: list[dict[str, Any]] = []
    for run_id in run_ids:
        telemetry_path = _telemetry_path_for_run(vault, run_id)
        telemetry = load_optional_json_object(telemetry_path) if telemetry_path else {}
        legacy_row = legacy_rows.get(run_id, {})
        reason_code = str(telemetry.get("same_eval_reason_code", "")).strip()
        axes = _string_list(telemetry.get("secondary_improvement_axes"))
        legacy_axes_present = _legacy_secondary_axes_present(legacy_row)
        runs.append(
            {
                "run_id": run_id,
                "telemetry_path": report_path(vault, telemetry_path)
                if telemetry_path
                else "",
                "telemetry_present": bool(telemetry),
                "same_eval_reason_code_present": bool(
                    reason_code and reason_code != "unknown"
                )
                or _legacy_decision_reason_code_present(telemetry, legacy_row),
                "strict_secondary_improvement_present": bool(
                    telemetry.get("strict_secondary_improvement_present", False)
                )
                or legacy_axes_present,
                "secondary_improvement_axes_present": bool(axes) or legacy_axes_present,
                "behavior_delta_digest_present": bool(
                    str(telemetry.get("behavior_delta_digest", "")).strip()
                )
                or _legacy_behavior_delta_digest_present(legacy_row),
            }
        )
    run_count = len(runs)
    reason_code_count = sum(1 for item in runs if item["same_eval_reason_code_present"])
    strict_secondary_count = sum(
        1
        for item in runs
        if item["strict_secondary_improvement_present"]
        and item["secondary_improvement_axes_present"]
    )
    digest_count = sum(1 for item in runs if item["behavior_delta_digest_present"])
    complete_count = sum(
        1
        for item in runs
        if item["same_eval_reason_code_present"]
        and item["strict_secondary_improvement_present"]
        and item["secondary_improvement_axes_present"]
        and item["behavior_delta_digest_present"]
    )
    complete = run_count in (0, complete_count)
    return {
        "status": "not_applicable"
        if run_count == 0
        else ("pass" if complete else "blocked"),
        "proposal_family": "repeated_same_eval_or_discard",
        "proposal_failure_modes": sorted(SAME_EVAL_PROPOSAL_FAILURE_MODES),
        "run_count": run_count,
        "runs_with_complete_typed_evidence": complete_count,
        "same_eval_reason_code_coverage_ratio": _coverage_ratio(
            reason_code_count, run_count
        ),
        "strict_secondary_improvement_coverage_ratio": _coverage_ratio(
            strict_secondary_count, run_count
        ),
        "behavior_delta_digest_coverage_ratio": _coverage_ratio(
            digest_count, run_count
        ),
        "runs": runs,
    }


def fallback_history_requirement(
    mechanism_review_report: dict[str, Any],
) -> tuple[int, int]:
    bootstrap = mechanism_review_report.get("diagnostics", {}).get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return 0, 0
    target_groups = bootstrap.get("target_groups_under_min_history", [])
    if not isinstance(target_groups, list):
        return 0, 0

    for item in target_groups:
        if not isinstance(item, dict):
            continue
        if _string_list(item.get("primary_targets")) != FALLBACK_PRIMARY_TARGETS:
            continue
        blocked = item.get("blocked_candidate_types", [])
        if not isinstance(blocked, list):
            return 0, 0
        required_runs = [
            int(entry["required_runs"])
            for entry in blocked
            if isinstance(entry, dict) and isinstance(entry.get("required_runs"), int)
        ]
        additional_runs_needed = [
            int(entry["additional_runs_needed"])
            for entry in blocked
            if isinstance(entry, dict)
            and isinstance(entry.get("additional_runs_needed"), int)
        ]
        return (
            max(required_runs, default=0),
            max(additional_runs_needed, default=0),
        )
    return 0, 0
