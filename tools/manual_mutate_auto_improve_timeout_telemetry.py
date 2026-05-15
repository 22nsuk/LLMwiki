#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected snippet not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _patch_preserved_telemetry_fields(runtime_path: Path) -> None:
    replace_once(
        runtime_path,
        """# Optional run-telemetry fields that are produced earlier in the run and must
# survive later auto-improve iteration writes unless the phase has an explicit
# overwrite or merge rule above.
PRESERVED_RUN_TELEMETRY_FIELDS = frozenset(
    {
    "primary_targets",
    "supporting_targets",
    "test_files",
    "workspace_preparation",
    "apply_mode",
    "apply_status",
    "live_applied",
    "shadow_apply_report",
        "rollback_rehearsal_report",
    }
)
""",
        """# Run-telemetry fields produced earlier in the run that later iteration writes
# should preserve unless an explicit overwrite or merge rule applies.
PRESERVED_RUN_TELEMETRY_FIELDS = frozenset(
    {
        "primary_targets", "supporting_targets", "test_files",
        "workspace_preparation", "apply_mode", "apply_status",
        "live_applied", "shadow_apply_report", "rollback_rehearsal_report",
    }
)
""",
    )


def _patch_command_timeout_merge(runtime_path: Path) -> None:
    replace_once(
        runtime_path,
        """def _iteration_command_timeouts(vault: Path, run_id: str, result: dict | None) -> dict | None:
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    merged: dict[str, dict] = {}
    existing_timeouts = (
        existing_report.get("command_timeouts", {}) if isinstance(existing_report, dict) else {}
    )
    if isinstance(existing_timeouts, dict):
        for key in ("mutation_command", "repo_health"):
            normalized = _normalize_timeout_result(existing_timeouts.get(key))
            if normalized is not None:
                merged[key] = normalized
    if isinstance(result, dict):
        for key in ("mutation_command", "repo_health"):
            normalized = _normalize_timeout_result(result.get(key))
            if normalized is not None:
                merged[key] = normalized
    return merged or None
""",
        """def _iteration_command_timeouts(vault: Path, run_id: str, result: dict | None) -> dict | None:
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    merged: dict[str, dict] = {}
    timeout_sources = []
    if isinstance(existing_report, dict):
        timeout_sources.append(existing_report.get("command_timeouts", {}))
    if isinstance(result, dict):
        timeout_sources.extend((result.get("command_timeouts", {}), result))
    for source in timeout_sources:
        if not isinstance(source, dict):
            continue
        for key in ("mutation_command", "repo_health"):
            normalized = _normalize_timeout_result(source.get(key))
            if normalized is not None:
                merged[key] = normalized
    return merged or None
""",
    )


def _patch_timeout_failure_artifacts(runtime_path: Path) -> None:
    replace_once(
        runtime_path,
        """def _iteration_timeout_failure_artifacts(vault: Path, run_id: str) -> list[str]:
    artifacts: set[str] = set()
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    existing_artifacts = (
        existing_report.get("timeout_failure_artifacts", [])
        if isinstance(existing_report, dict)
        else []
    )
    if isinstance(existing_artifacts, list):
        artifacts.update(str(item) for item in existing_artifacts if str(item).strip())
    run_dir = vault / run_rel(run_id, "")
    if run_dir.exists():
        artifacts.update(
            run_rel(run_id, path.name)
            for path in run_dir.glob("*-timeout-failure.json")
            if path.is_file()
        )
    return sorted(artifacts)
""",
        """def _iteration_timeout_failure_artifacts(vault: Path, run_id: str, result: dict | None) -> list[str]:
    artifacts: set[str] = set()
    existing_report = load_optional_json(vault / run_rel(run_id, "run-telemetry.json"))
    existing_artifacts = existing_report.get("timeout_failure_artifacts", []) if isinstance(existing_report, dict) else []
    result_artifacts = result.get("timeout_failure_artifacts", []) if isinstance(result, dict) else []
    if isinstance(existing_artifacts, list) or isinstance(result_artifacts, list):
        artifacts.update(
            str(item)
            for item in [
                *(existing_artifacts if isinstance(existing_artifacts, list) else []),
                *(result_artifacts if isinstance(result_artifacts, list) else []),
            ]
            if str(item).strip()
        )
    run_dir = vault / run_rel(run_id, "")
    if run_dir.exists():
        artifacts.update(
            run_rel(run_id, path.name)
            for path in run_dir.glob("*-timeout-failure.json")
            if path.is_file()
        )
    return sorted(artifacts)
""",
    )


def _patch_timeout_failure_call(runtime_path: Path) -> None:
    replace_once(
        runtime_path,
        """    timeout_failure_artifacts = _iteration_timeout_failure_artifacts(request.vault, request.run_id)
""",
        """    timeout_failure_artifacts = _iteration_timeout_failure_artifacts(
        request.vault, request.run_id, request.result
    )
""",
    )


def _patch_test_regression(test_path: Path) -> None:
    replace_once(
        test_path,
        """            self.assertEqual(payload["behavior_delta"], f"runs/{run_id}/behavior-delta.json")
            self.assertEqual(payload["phase_durations"], {"routing": 0.2, "experiment": 0.5})

    def test_execute_evaluate_iteration_phase_builds_request_and_delegates(self) -> None:
""",
        """            self.assertEqual(payload["behavior_delta"], f"runs/{run_id}/behavior-delta.json")
            self.assertEqual(payload["phase_durations"], {"routing": 0.2, "experiment": 0.5})

    def test_write_iteration_telemetry_merges_nested_timeout_fields_from_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "auto-session-run-timeouts"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)

            rel_path = write_iteration_telemetry(
                request=IterationTelemetryRequest(
                    vault=vault,
                    run_id=run_id,
                    session_id="auto-session",
                    proposal={"proposal_id": "proposal-1"},
                    scope_freeze_rel=f"runs/{run_id}/scope-freeze.json",
                    routing_report_rels=[f"runs/{run_id}/subagent-routing.worker.json"],
                    roles=["worker"],
                    phase_durations={"routing": 0.1, "experiment": 0.2},
                    outcome="validation_blocked",
                    result={
                        "decision": "HOLD",
                        "finalized": False,
                        "finalize_result": {},
                        "mutation_command": {
                            "timed_out": True,
                            "timeout_seconds": 1800,
                            "termination_reason": "timeout",
                        },
                        "command_timeouts": {
                            "repo_health": {
                                "timed_out": False,
                                "timeout_seconds": 5400,
                                "termination_reason": "completed",
                            }
                        },
                        "timeout_failure_artifacts": [
                            f"runs/{run_id}/worker-executor-timeout-failure.json"
                        ],
                    },
                    context=_context(),
                )
            )

            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(
                payload["command_timeouts"],
                {
                    "mutation_command": {
                        "timed_out": True,
                        "timeout_seconds": 1800,
                        "termination_reason": "timeout",
                    },
                    "repo_health": {
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                    },
                },
            )
            self.assertEqual(
                payload["timeout_failure_artifacts"],
                [f"runs/{run_id}/worker-executor-timeout-failure.json"],
            )

    def test_execute_evaluate_iteration_phase_builds_request_and_delegates(self) -> None:
""",
    )


def main() -> None:
    repo = Path.cwd()
    runtime_path = repo / "ops" / "scripts" / "auto_improve_iteration_persistence_runtime.py"
    test_path = repo / "tests" / "test_auto_improve_iteration_runtime.py"
    _patch_preserved_telemetry_fields(runtime_path)
    _patch_command_timeout_merge(runtime_path)
    _patch_timeout_failure_artifacts(runtime_path)
    _patch_timeout_failure_call(runtime_path)
    _patch_test_regression(test_path)


if __name__ == "__main__":
    main()
