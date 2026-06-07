from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext

from tests.run_mechanism_experiment_test_utils import mutation_proposal_report


def _incrementing_runtime_context(start: dt.datetime | None = None) -> RuntimeContext:
    current = {
        "value": start or dt.datetime(2026, 4, 15, 0, 0, tzinfo=dt.UTC)
    }

    def clock() -> dt.datetime:
        value = current["value"]
        current["value"] = value + dt.timedelta(seconds=1)
        return value

    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=clock,
        session_id="auto-incrementing",
        executor_id="codex_exec",
    )


def _expected_timeout_summary(
    *,
    timed_out: bool,
    timeout_seconds: int,
    termination_reason: str,
) -> dict[str, object]:
    return {
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "termination_reason": termination_reason,
        "launch_succeeded": True,
        "signal_sent": "none",
        "final_state_observed": "",
        "stdout_received": False,
        "stderr_received": False,
    }


def _learning_review_required_report() -> dict[str, object]:
    return {
        "generated_at": "2026-04-15T00:00:00Z",
        "execution_readiness": {
            "status": "pass",
            "can_run": True,
        },
        "learning_readiness": {
            "status": "learning_uncertain",
            "gate_effect": "operator_review_required",
            "can_run": True,
            "likely_to_learn": False,
            "metrics": {
                "session_reports_considered": 0,
            },
            "recommended_next_step": (
                "Execution readiness is pass, but learning readiness still requires explicit operator review. "
                "Rerun auto-improve with --allow-learning-uncertain only if you want a bounded trial."
            ),
        },
        "queue": {
            "runnable_proposal_ids": ["proposal-ready"],
            "runnable_proposal_count": 1,
        },
    }


def _seed_scaffolded_run(vault: Path, run_id: str) -> None:
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-ledger.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/run-ledger.schema.json",
                "run_id": run_id,
                "status": "draft",
                "events": [
                    {
                        "ts": "2026-04-15T00:00:00Z",
                        "type": "created",
                        "summary": "created",
                        "artifacts": ["seed.yaml"],
                        "decision": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "proposal-snapshot.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/proposal-snapshot.schema.json",
                "run_id": run_id,
                "source_report": "ops/reports/mutation-proposals.json",
                "captured_at": "2026-04-15T00:00:00Z",
                "proposal": mutation_proposal_report("ops/scripts/example.py")["proposals"][0],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_executor_report(
    vault: Path,
    run_id: str,
    *,
    role: str,
    status: str,
    sandbox_mode: str,
    model: str,
    reasoning_effort: str,
    returncode: int,
    notes: list[str],
) -> None:
    (vault / "runs" / run_id / f"{role}-executor-report.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/executor-report.schema.json",
                "run_id": run_id,
                "role": role,
                "generated_at": "2026-04-15T00:00:00Z",
                "executor": {
                    "name": "codex_exec",
                    "sandbox_mode": sandbox_mode,
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                },
                "status": status,
                "command": {"argv": ["codex", "exec"]},
                "artifacts": {
                    "prompt": f"runs/{run_id}/{role}-prompt.md",
                    "output_last_message": f"runs/{run_id}/{role}-last-message.json",
                    "stdout": f"runs/{run_id}/{role}.stdout.txt",
                    "stderr": f"runs/{run_id}/{role}.stderr.txt",
                },
                "result": {
                    "returncode": returncode,
                    "timed_out": False,
                    "timeout_seconds": 1800,
                    "termination_reason": "completed",
                },
                "diagnostics": {
                    "routing_report": f"runs/{run_id}/subagent-routing.{role}.json",
                    "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                    "notes": notes,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_successful_run_telemetry(
    vault: Path,
    run_id: str,
    *,
    shadow_apply_rel: str,
    rollback_rehearsal_rel: str,
) -> None:
    (vault / "runs" / run_id / "run-telemetry.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/run-telemetry.schema.json",
                "session_id": "",
                "run_id": run_id,
                "generated_at": "2026-04-15T00:00:00Z",
                "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                "routing_reports": [],
                "executor_reports": [],
                "command_timeouts": {
                    "mutation_command": {
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                    },
                    "repo_health": {
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                    },
                },
                "workspace_preparation": {
                    "mode": "full_copy",
                    "baseline_file_count": 10,
                    "copied_file_count": 10,
                    "phase_durations": {
                        "digest": 0.1,
                        "copy": 0.2,
                        "total": 0.3,
                    },
                },
                "apply_mode": "live",
                "apply_status": "live_applied",
                "live_applied": True,
                "shadow_apply_report": shadow_apply_rel,
                "rollback_rehearsal_report": rollback_rehearsal_rel,
                "timeout_failure_artifacts": [
                    f"runs/{run_id}/worker-executor-timeout-failure.json"
                ],
                "decision": "PROMOTE",
                "finalized": True,
                "finalize_result": {"run_id": run_id},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_worker_timeout_failure(vault: Path, run_id: str) -> None:
    (vault / "runs" / run_id / "worker-executor-timeout-failure.json").write_text(
        json.dumps(
            {
                "$schema": "ops/schemas/timeout-failure.schema.json",
                "run_id": run_id,
                "generated_at": "2026-04-15T00:00:00Z",
                "phase": "executor",
                "role": "worker",
                "command": {"argv": ["codex", "exec", "-"]},
                "result": {
                    "returncode": -15,
                    "timed_out": True,
                    "timeout_seconds": 1800,
                    "termination_reason": "timeout",
                },
                "artifacts": {
                    "stdout": f"runs/{run_id}/worker.stdout.txt",
                    "stderr": f"runs/{run_id}/worker.stderr.txt",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_successful_executor_reports(vault: Path, run_id: str) -> None:
    _write_executor_report(
        vault,
        run_id,
        role="worker",
        status="pass",
        sandbox_mode="workspace-write",
        model="gpt-5.5",
        reasoning_effort="high",
        returncode=0,
        notes=["worker applied mutation"],
    )
    _write_executor_report(
        vault,
        run_id,
        role="validator",
        status="pass",
        sandbox_mode="read-only",
        model="gpt-5.5",
        reasoning_effort="xhigh",
        returncode=0,
        notes=["validator approved"],
    )


def _fake_successful_mechanism_experiment(
    vault_path: Path,
    *,
    run_id: str,
    scaffold_only: bool,
    **_: object,
) -> dict:
    if scaffold_only:
        _seed_scaffolded_run(vault_path, run_id)
        return {"run_id": run_id, "scaffold_only": True}
    shadow_apply_rel = f"runs/{run_id}/shadow-apply-report.json"
    rollback_rehearsal_rel = f"runs/{run_id}/rollback-rehearsal-report.json"
    (vault_path / shadow_apply_rel).write_text(
        json.dumps({"status": "ready_for_live_apply"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (vault_path / rollback_rehearsal_rel).write_text(
        json.dumps({"status": "pass"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_successful_run_telemetry(
        vault_path,
        run_id,
        shadow_apply_rel=shadow_apply_rel,
        rollback_rehearsal_rel=rollback_rehearsal_rel,
    )
    _write_worker_timeout_failure(vault_path, run_id)
    _write_successful_executor_reports(vault_path, run_id)
    return {
        "run_id": run_id,
        "decision": "PROMOTE",
        "apply_mode": "live",
        "apply_status": "live_applied",
        "live_applied": True,
        "shadow_apply_report": shadow_apply_rel,
        "rollback_rehearsal_report": rollback_rehearsal_rel,
        "finalized": True,
        "finalize_result": {"run_id": run_id},
        "repo_health": {"passed": True},
    }


def _fake_discarded_mechanism_experiment(
    vault_path: Path,
    *,
    run_id: str,
    scaffold_only: bool,
    **_: object,
) -> dict:
    if scaffold_only:
        _seed_scaffolded_run(vault_path, run_id)
        return {"run_id": run_id, "scaffold_only": True}
    _write_successful_run_telemetry(
        vault_path,
        run_id,
        shadow_apply_rel=f"runs/{run_id}/shadow-apply-report.json",
        rollback_rehearsal_rel=f"runs/{run_id}/rollback-rehearsal-report.json",
    )
    _write_successful_executor_reports(vault_path, run_id)
    return {
        "run_id": run_id,
        "decision": "DISCARD",
        "finalized": True,
        "finalize_result": {"run_id": run_id},
        "repo_health": {"passed": True},
    }


def _load_successful_auto_improve_artifacts(vault: Path, result: dict) -> dict:
    session = json.loads((vault / result["session_report"]).read_text(encoding="utf-8"))
    run_id = session["run_ids"][0]
    run_dir = vault / "runs" / run_id
    return {
        "session": session,
        "provenance_aggregate": json.loads(
            (vault / result["routing_provenance_aggregate"]).read_text(encoding="utf-8")
        ),
        "promotion_trends": json.loads(
            (vault / result["promotion_decision_trends"]).read_text(encoding="utf-8")
        ),
        "run_artifact_fingerprint": json.loads(
            (run_dir / "run-artifact-fingerprint.json").read_text(encoding="utf-8")
        ),
        "telemetry": json.loads((run_dir / "run-telemetry.json").read_text(encoding="utf-8")),
        "run_events": [
            json.loads(line)
            for line in (run_dir / "runtime-events.jsonl").read_text(encoding="utf-8").splitlines()
        ],
        "session_events": [
            json.loads(line)
            for line in (
                vault
                / "ops"
                / "reports"
                / "runtime-events"
                / "auto-improve-session"
                / "auto-session.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ],
        "routing_reports": [
            json.loads((vault / rel_path).read_text(encoding="utf-8"))
            for rel_path in session["iterations"][0]["routing_reports"]
        ],
    }
