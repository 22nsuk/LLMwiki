from __future__ import annotations

import json
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
LIVE_POLICY_VERSION = load_policy(REPO_ROOT)[0]["version"]
SCHEMA_NAMES = (
    "wiki-maintainer-policy.schema.json",
    "promotion-report.schema.json",
    "mechanism-assessment-report.schema.json",
    "eval-report.schema.json",
    "mechanism-review-candidates.schema.json",
    "run-telemetry.schema.json",
    "changed-files-manifest.schema.json",
)


def seed_review_vault(vault: Path) -> None:
    (vault / "ops" / "policies").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "runs").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for name in SCHEMA_NAMES:
        source = REPO_ROOT / "ops" / "schemas" / name
        (vault / "ops" / "schemas" / name).write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def eval_report(vault: Path, score: int, *, max_score: int = 10, status: str = "pass") -> dict:
    return {
        "$schema": "ops/schemas/eval-report.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": "2026-04-14T00:00:00Z",
        "artifact_kind": "wiki_eval_report",
        "producer": "tests.test_mechanism_review",
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {
            "policy": "fixture",
            "schema": "fixture",
            "artifact_envelope_schema": "fixture",
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": "2026-04-14T00:00:00Z",
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "status": status,
        "max_score": max_score,
        "total_score": score,
        "pages": [],
    }


def mechanism_report(
    vault: Path,
    *,
    primary_targets: list[str],
    nonempty: int,
    functions: int,
    branches: int,
    test_file_count: int,
    test_case_count: int,
    complexity_score: int,
    risk_flags: list[str] | None = None,
) -> dict:
    test_files = [f"tests/test_target_{idx}.py" for idx in range(max(test_file_count, 1))]
    selected_test_files = test_files[:test_file_count]
    all_targets = [*primary_targets, *selected_test_files]
    return {
        "$schema": "ops/schemas/mechanism-assessment-report.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": "2026-04-14T00:00:00Z",
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "primary_targets": primary_targets,
        "supporting_targets": [],
        "test_files": selected_test_files,
        "structural_metrics": {
            "nonempty_line_count_total": nonempty,
            "python_function_count": functions,
            "python_branch_node_count": branches,
            "markdown_heading_count": 0,
            "test_file_count": test_file_count,
            "test_case_count": test_case_count,
        },
        "total_structural_metrics": {
            "nonempty_line_count_total": nonempty,
            "python_function_count": functions,
            "python_branch_node_count": branches,
            "markdown_heading_count": 0,
            "test_file_count": test_file_count,
            "test_case_count": test_case_count,
        },
        "diagnostics": {
            "unreadable_targets": [],
            "python_parse_failures": [],
        },
        "complexity_profile": {
            "dimensions": {
                "change_surface": 3,
                "dependency_impact": 3,
                "verification_cost": 2,
                "artifact_heterogeneity": 1,
                "environment_risk": 2 if risk_flags else 0,
            },
            "complexity_score": complexity_score,
            "risk_flags": risk_flags or [],
            "primary_targets": primary_targets,
            "supporting_targets": [],
            "test_files": selected_test_files,
            "risk_flag_evidence": [
                {
                    "flag": flag,
                    "path": primary_targets[0],
                    "reason": "fixture",
                }
                for flag in (risk_flags or [])
            ],
            "target_profiles": [
                {
                    "path": path,
                    "kind": "python",
                    "nonempty_line_count": nonempty,
                    "python_function_count": functions,
                    "python_branch_node_count": branches,
                    "markdown_heading_count": 0,
                    "python_semantic_complexity_points": functions + branches,
                    "whole_file_volume": nonempty,
                    "coarse_target": False,
                }
                for path in all_targets
            ],
            "dimension_evidence": {
                "change_surface": {
                    "target_count": len(all_targets),
                    "target_count_score": 3,
                    "whole_file_volume": nonempty,
                    "whole_file_volume_score": 3,
                    "per_target_capped_volume": nonempty,
                    "per_target_capped_volume_score": 3,
                    "semantic_volume": functions + branches,
                    "semantic_volume_score": 3,
                    "large_file_target_count": 0,
                    "coarse_target_bias_mitigated": False,
                    "selected_score": 3,
                },
                "verification_cost": {
                    "target_count": len(all_targets),
                    "test_file_count": test_file_count,
                    "test_case_count": test_case_count,
                    "verification_scope": "targeted_pytest",
                    "reasons": ["fixture"],
                    "selected_score": 2,
                },
            },
        },
    }


def changed_files_manifest(
    run_id: str,
    *,
    changed_files: list[dict] | None = None,
    primary_targets: list[str] | None = None,
    supporting_targets: list[str] | None = None,
) -> dict:
    files = changed_files or [{"path": "ops/scripts/example.py", "change_type": "modified"}]
    return {
        "$schema": "ops/schemas/changed-files-manifest.schema.json",
        "run_id": run_id,
        "generated_at": "2026-04-14T00:00:00Z",
        "declared_targets": {
            "primary_targets": primary_targets or ["ops/scripts/example.py"],
            "supporting_targets": supporting_targets or [],
            "test_files": [],
        },
        "summary": {
            "total_changed_files": len(files),
            "added": sum(1 for item in files if item.get("change_type") == "added"),
            "modified": sum(1 for item in files if item.get("change_type") == "modified"),
            "deleted": sum(1 for item in files if item.get("change_type") == "deleted"),
        },
        "diff_universe": {
            "model": "full_workspace",
            "baseline_file_count": 1,
            "candidate_file_count": 1,
        },
        "files": files,
    }


def promotion_report(
    run_id: str,
    *,
    primary_targets: list[str],
    decision: str,
    baseline_eval_path: str,
    candidate_eval_path: str,
    baseline_mechanism_path: str,
    candidate_mechanism_path: str,
    changed_files_manifest_path: str | None = None,
    history_status: str = "active",
    history_reason: str = "",
) -> dict:
    inputs = {
        "baseline_eval_report": baseline_eval_path,
        "candidate_eval_report": candidate_eval_path,
        "baseline_lint_report": "runs/placeholder/baseline-lint.json",
        "candidate_lint_report": "runs/placeholder/candidate-lint.json",
        "baseline_mechanism_report": baseline_mechanism_path,
        "candidate_mechanism_report": candidate_mechanism_path,
        "run_ledger": f"runs/{run_id}/run-ledger.json",
    }
    if changed_files_manifest_path is not None:
        inputs["changed_files_manifest"] = changed_files_manifest_path

    return {
        "$schema": "ops/schemas/promotion-report.schema.json",
        "run_id": run_id,
        "mode": "report_only",
        "artifact_class": "system_mechanism",
        "decision": decision,
        "summary": f"promotion report for {run_id}",
        "primary_targets": primary_targets,
        "supporting_targets": [],
        "checks": [
            {
                "id": "candidate_eval_pass",
                "status": "PASS",
                "detail": "candidate eval pass",
            }
        ],
        "signoff": {
            "required": True,
            "status": "approved",
            "by": "tester",
            "ts": "2026-04-14T00:00:00Z",
        },
        "log": {
            "required": True,
            "page": "system/system-log.md",
            "summary": f"log summary for {run_id}",
            "status": "pending",
            "entry_ref": "",
        },
        "history": {
            "status": history_status,
            "reason": history_reason,
            "by": "",
            "ts": "",
        },
        "next_action": "append log entry",
        "inputs": inputs,
    }


def outcome_metrics_report(vault: Path, *, primary_targets: list[str]) -> dict:
    return {
        "$schema": "ops/schemas/outcome-metrics.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": "2026-04-15T00:00:00Z",
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "summary": {
            "attempts_considered": 3,
            "recent_window": 20,
            "recent_attempt_count": 3,
            "session_reports_considered": 1,
        },
        "metrics": {
            "attempt_count": 3,
            "recent_window": 20,
            "recent_attempt_count": 3,
            "rework_count": 2,
            "rollback_signal_count": 1,
            "rollback_rehearsal_coverage_count": 1,
            "moving_averages": {
                "hold": 0.3333,
                "discard": 0.6667,
                "rollback_signal": 0.3333,
            },
            "operator_effort_proxy": {
                "phase_totals_seconds": {"execution": 30.0},
                "executor_report_count": 3,
                "reviewer_dispatch_count": 1,
                "validator_dispatch_count": 1,
                "auditor_dispatch_count": 0,
                "hold_count": 1,
            },
            "rework_keys": [
                {
                    "key": "proposal:promotion-gate-rework",
                    "attempt_count": 3,
                    "rework_count": 2,
                    "run_ids": [
                        "run-20260414-a",
                        "run-20260414-b",
                        "run-20260414-c",
                    ],
                }
            ],
            "defect_escape_proxy": {
                "count": 1,
                "pairs": [
                    {
                        "target": primary_targets[0],
                        "promoted_run_id": "run-20260414-b",
                        "escaped_run_id": "run-20260414-c",
                        "escaped_decision": "HOLD",
                        "escaped_outcome": "validation_blocked",
                    }
                ],
            },
        },
        "recent_attempts": [
            {
                "run_id": "run-20260414-a",
                "session_id": "auto-session-shared",
                "proposal_id": "promotion-gate-rework",
                "observed_at": "2026-04-15T00:00:00Z",
                "decision": "DISCARD",
                "outcome": "validation_blocked",
                "primary_targets": primary_targets,
                "rework_key": "proposal:promotion-gate-rework",
                "rollback_rehearsal_covered": False,
                "rollback_signal": False,
                "run_telemetry": "runs/run-20260414-a/run-telemetry.json",
                "promotion_report": "runs/run-20260414-a/promotion-report.json",
            },
            {
                "run_id": "run-20260414-b",
                "session_id": "auto-session-shared",
                "proposal_id": "promotion-gate-rework",
                "observed_at": "2026-04-15T00:01:00Z",
                "decision": "DISCARD",
                "outcome": "validation_blocked",
                "primary_targets": primary_targets,
                "rework_key": "proposal:promotion-gate-rework",
                "rollback_rehearsal_covered": False,
                "rollback_signal": False,
                "run_telemetry": "runs/run-20260414-b/run-telemetry.json",
                "promotion_report": "runs/run-20260414-b/promotion-report.json",
            },
            {
                "run_id": "run-20260414-c",
                "session_id": "auto-session-shared",
                "proposal_id": "promotion-gate-rework",
                "observed_at": "2026-04-15T00:02:00Z",
                "decision": "HOLD",
                "outcome": "validation_blocked",
                "primary_targets": primary_targets,
                "rework_key": "proposal:promotion-gate-rework",
                "rollback_rehearsal_covered": True,
                "rollback_signal": True,
                "run_telemetry": "runs/run-20260414-c/run-telemetry.json",
                "promotion_report": "runs/run-20260414-c/promotion-report.json",
            },
        ],
    }


def write_run_session_context(vault: Path, run_id: str, *, session_id: str) -> None:
    write_json(
        vault / "runs" / run_id / "run-telemetry.json",
        {
            "$schema": "ops/schemas/run-telemetry.schema.json",
            "session_id": session_id,
            "run_id": run_id,
            "generated_at": "2026-04-15T00:00:00Z",
            "proposal_id": f"proposal-{run_id}",
            "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
            "scope_freeze": f"runs/{run_id}/scope-freeze.json",
            "routing_reports": [],
            "executor_reports": [],
            "phase_durations": {},
            "failure_taxonomy": "",
            "decision": "",
            "finalized": False,
            "finalize_result": {},
        },
    )


def write_session_report(
    vault: Path,
    session_id: str,
    *,
    failure_taxonomy_counts: dict[str, int] | None = None,
    executor_role_counts: dict[str, int] | None = None,
    risk_flag_counts: dict[str, int] | None = None,
    routing_extras: dict | None = None,
    executor_extras: dict | None = None,
    telemetry_extras: dict | None = None,
) -> None:
    routing_rollup = {
        "risk_flag_counts": risk_flag_counts or {},
    }
    if routing_extras:
        routing_rollup.update(routing_extras)
    executor_rollup = {
        "role_counts": executor_role_counts or {},
    }
    if executor_extras:
        executor_rollup.update(executor_extras)
    telemetry_rollup = {
        "failure_taxonomy_counts": failure_taxonomy_counts or {},
    }
    if telemetry_extras:
        telemetry_rollup.update(telemetry_extras)
    write_json(
        vault / "ops" / "reports" / "auto-improve-sessions" / f"{session_id}.json",
        {
            "session_id": session_id,
            "rollups": {
                "routing": routing_rollup,
                "executor": executor_rollup,
                "telemetry": telemetry_rollup,
            },
        },
    )
