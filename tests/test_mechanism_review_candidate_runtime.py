from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.mechanism import mechanism_review_candidate_runtime
from ops.scripts.mechanism.mechanism_candidate_registry_runtime import (
    BRANCH_GROWTH_CANDIDATE,
    EVAL_STAGNATION_CANDIDATE,
    HIGH_COMPLEXITY_CANDIDATE,
    SCHEMA_DRIFT_CANDIDATE,
)
from ops.scripts.mechanism.mechanism_review_candidate_runtime import (
    build_candidates,
    candidate_template,
)
from ops.scripts.mechanism.mechanism_review_history_runtime import (
    MechanismRunSnapshot,
    load_optional_json,
)
from ops.scripts.mechanism.mechanism_review_session_calibration_runtime import (
    build_session_calibration_diagnostics,
    session_report_for_run,
)
from tests.mechanism_review_test_utils import (
    REPO_ROOT,
    changed_files_manifest,
    eval_report,
    mechanism_report,
    write_run_session_context,
    write_session_report,
)


def mechanism_snapshot(
    vault: Path,
    *,
    run_id: str,
    baseline_branch: int,
    candidate_branch: int,
    baseline_nonempty: int,
    candidate_nonempty: int,
    decision: str,
    supporting_targets: list[str] | None = None,
    risk_flags: list[str] | None = None,
    changed_files: list[dict] | None = None,
) -> MechanismRunSnapshot:
    primary_targets = ["ops/scripts/promotion_gate.py"]
    resolved_supporting_targets = list(supporting_targets or [])
    return MechanismRunSnapshot(
        run_id=run_id,
        promotion_report_path=f"runs/{run_id}/promotion-report.json",
        primary_targets=primary_targets,
        supporting_targets=resolved_supporting_targets,
        decision=decision,
        baseline_eval=eval_report(vault, 10),
        candidate_eval=eval_report(vault, 10),
        baseline_mechanism=mechanism_report(
            vault,
            primary_targets=primary_targets,
            nonempty=baseline_nonempty,
            functions=4,
            branches=baseline_branch,
            test_file_count=1,
            test_case_count=2,
            complexity_score=60,
        ),
        candidate_mechanism=mechanism_report(
            vault,
            primary_targets=primary_targets,
            nonempty=candidate_nonempty,
            functions=4,
            branches=candidate_branch,
            test_file_count=1,
            test_case_count=2,
            complexity_score=85,
            risk_flags=risk_flags,
        ),
        changed_files_manifest=changed_files_manifest(
            run_id,
            changed_files=changed_files,
            primary_targets=primary_targets,
            supporting_targets=resolved_supporting_targets,
        ),
    )


class MechanismReviewCandidateRuntimeTest(unittest.TestCase):
    def test_session_calibration_diagnostics_stays_on_session_runtime_surface(self) -> None:
        self.assertNotIn(
            "build_session_calibration_diagnostics",
            mechanism_review_candidate_runtime.__dict__,
        )

    def test_candidate_template_clamps_priority_and_normalizes_identity_fields(self) -> None:
        policy, _policy_path = load_policy(REPO_ROOT)

        candidate = candidate_template(
            policy,
            candidate_type=SCHEMA_DRIFT_CANDIDATE,
            family="schema_drift",
            primary_targets=["ops/schemas/Foo.schema.json"],
            supporting_targets=["ops/scripts/helper.py"],
            metrics_triggered=["schema_change_without_test_growth"],
            priority=125,
            rationale="schema drift signal",
            suggested_experiments=["add schema contract regression"],
            run_ids=["run-b", "run-a"],
            evidence={"runs_examined": 2},
        )

        self.assertEqual(
            candidate["candidate_id"],
            f"{SCHEMA_DRIFT_CANDIDATE}__foo-schema",
        )
        self.assertEqual(candidate["tier"], "core")
        self.assertEqual(candidate["priority"], 100)
        self.assertEqual(candidate["run_ids"], ["run-a", "run-b"])

    def test_build_candidates_uses_injected_loader_and_reuses_run_session_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            policy, _policy_path = load_policy(REPO_ROOT)

            write_run_session_context(vault, "run-a", session_id="session-shared")
            write_run_session_context(vault, "run-b", session_id="session-shared")
            write_session_report(
                vault,
                "session-shared",
                failure_taxonomy_counts={"validation_blocked": 1},
                executor_role_counts={"validator": 1},
            )

            telemetry_read_counts: dict[str, int] = {}
            session_report_read_counts: dict[str, int] = {}

            def counting_load_optional_json(path: Path) -> dict | None:
                key = report_path(vault, path)
                if path.name == "run-telemetry.json":
                    telemetry_read_counts[key] = telemetry_read_counts.get(key, 0) + 1
                if "auto-improve-sessions" in path.parts:
                    session_report_read_counts[key] = session_report_read_counts.get(key, 0) + 1
                return load_optional_json(path)

            snapshots = [
                mechanism_snapshot(
                    vault,
                    run_id="run-a",
                    baseline_branch=20,
                    candidate_branch=26,
                    baseline_nonempty=20,
                    candidate_nonempty=28,
                    decision="DISCARD",
                ),
                mechanism_snapshot(
                    vault,
                    run_id="run-b",
                    baseline_branch=26,
                    candidate_branch=28,
                    baseline_nonempty=28,
                    candidate_nonempty=36,
                    decision="DISCARD",
                ),
            ]

            candidates = build_candidates(
                vault,
                policy,
                snapshots,
                load_optional_json_func=counting_load_optional_json,
            )

        candidate_types = {candidate["candidate_type"] for candidate in candidates}
        self.assertTrue(
            {
                BRANCH_GROWTH_CANDIDATE,
                HIGH_COMPLEXITY_CANDIDATE,
                EVAL_STAGNATION_CANDIDATE,
            }.issubset(candidate_types)
        )
        self.assertEqual(
            telemetry_read_counts,
            {
                "runs/run-a/run-telemetry.json": 1,
                "runs/run-b/run-telemetry.json": 1,
            },
        )
        self.assertEqual(
            session_report_read_counts,
            {"ops/reports/auto-improve-sessions/session-shared.json": 1},
        )
        stagnation_candidate = next(
            candidate
            for candidate in candidates
            if candidate["candidate_type"] == EVAL_STAGNATION_CANDIDATE
        )
        self.assertEqual(
            stagnation_candidate["session_calibration"]["validation_blocked_sessions"],
            1,
        )
        self.assertEqual(stagnation_candidate["session_calibration"]["priority_delta"], 7)

    def test_schema_drift_uses_changed_files_not_declared_supporting_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            policy, _policy_path = load_policy(REPO_ROOT)
            supporting_schema = ["ops/schemas/run-telemetry.schema.json"]
            snapshots = [
                mechanism_snapshot(
                    vault,
                    run_id=f"run-schema-supporting-only-{index}",
                    baseline_branch=4,
                    candidate_branch=4,
                    baseline_nonempty=20,
                    candidate_nonempty=20,
                    decision="PROMOTE",
                    supporting_targets=supporting_schema,
                    risk_flags=["schema_change"],
                    changed_files=[
                        {
                            "path": "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py",
                            "change_type": "modified",
                        }
                    ],
                )
                for index in range(2)
            ]

            candidates = build_candidates(vault, policy, snapshots)

            self.assertNotIn(
                SCHEMA_DRIFT_CANDIDATE,
                {candidate["candidate_type"] for candidate in candidates},
            )
            detail = mechanism_review_candidate_runtime.non_trigger_detail(
                policy,
                SCHEMA_DRIFT_CANDIDATE,
                snapshots,
            )
            self.assertIn("schema_change_runs=0", detail)
            self.assertIn("latest_schema_changed_files=[]", detail)

    def test_session_report_for_run_falls_back_to_session_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            run_id = "run-standalone"
            (vault / "runs" / run_id).mkdir(parents=True)
            (vault / "runs" / run_id / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/run-telemetry.schema.json",
                        "session_id": "",
                        "run_id": run_id,
                        "generated_at": "2026-04-15T00:00:00Z",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            session_dir = vault / "ops" / "reports" / "auto-improve-sessions"
            session_dir.mkdir(parents=True)
            (session_dir / "standalone-run-telemetry.json").write_text(
                json.dumps(
                    {
                        "session_id": "standalone-run-telemetry",
                        "generated_at": "2026-04-15T12:00:00Z",
                        "run_ids": [run_id],
                        "learning_summary": {
                            "session_context_status": "session_context_available",
                        },
                        "rollups": {},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            session_id, session_report = session_report_for_run(vault, run_id, {}, {})

            self.assertEqual(session_id, "standalone-run-telemetry")
            self.assertIsInstance(session_report, dict)
            self.assertEqual(session_report["run_ids"], [run_id])

    def test_session_report_for_run_resolves_archived_telemetry_and_session_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            run_id = "run-archived-session"
            session_id = "archived-session"
            run_dir = vault / "runs" / "archive" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "run-telemetry.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/run-telemetry.schema.json",
                        "session_id": session_id,
                        "run_id": run_id,
                        "generated_at": "2026-04-15T00:00:00Z",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            session_dir = vault / "ops" / "reports" / "archive" / "auto-improve-sessions"
            session_dir.mkdir(parents=True)
            (session_dir / f"{session_id}.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "generated_at": "2026-04-15T12:00:00Z",
                        "run_ids": [run_id],
                        "learning_summary": {
                            "session_context_status": "session_context_available",
                        },
                        "rollups": {"status": "present"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            resolved_session_id, session_report = session_report_for_run(vault, run_id, {}, {})

            self.assertEqual(resolved_session_id, session_id)
            self.assertIsInstance(session_report, dict)
            self.assertEqual(session_report["rollups"], {"status": "present"})

    def test_session_calibration_diagnostics_aggregates_candidates_by_family(self) -> None:
        candidates = [
            {
                "family": "contract_regression_signals",
                "session_calibration": {
                    "runs_with_session_context": 2,
                    "sessions_considered": 1,
                    "sessions_with_rollups": 1,
                    "validation_blocked_sessions": 1,
                    "validator_dispatch_sessions": 1,
                    "priority_delta": 7,
                },
            },
            {
                "family": "self_mod_stability",
                "session_calibration": {
                    "runs_with_session_context": 0,
                    "sessions_considered": 0,
                    "sessions_with_rollups": 0,
                    "priority_delta": 0,
                },
            },
        ]

        diagnostics = build_session_calibration_diagnostics(candidates, enabled=True)
        disabled = build_session_calibration_diagnostics(candidates, enabled=False)

        self.assertEqual(diagnostics["status"], "active")
        self.assertEqual(diagnostics["candidate_count"], 2)
        self.assertEqual(diagnostics["candidates_with_session_context"], 1)
        self.assertEqual(diagnostics["candidates_without_session_context"], 1)
        self.assertEqual(diagnostics["total_priority_delta"], 7)
        self.assertEqual(
            [entry["family"] for entry in diagnostics["by_family"]],
            ["contract_regression_signals", "self_mod_stability"],
        )
        self.assertEqual(disabled["status"], "disabled")
        self.assertFalse(disabled["enabled"])


if __name__ == "__main__":
    unittest.main()
