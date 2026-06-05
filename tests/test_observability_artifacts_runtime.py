from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.experiment_telemetry_runtime import (
    write_run_telemetry,
    write_timeout_failure_artifact,
)
from ops.scripts.observability_artifacts_runtime import (
    write_outcome_metrics_report,
    write_promotion_decision_trends,
    write_routing_provenance_aggregate,
    write_run_artifact_fingerprint,
)
from ops.scripts.observability_routing_provenance_runtime import (
    write_latest_routing_provenance_aggregate,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"

pytestmark = pytest.mark.report_contract


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 12, 0, tzinfo=dt.UTC),
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_ledger(vault: Path, run_id: str, *, ts: str, status: str = "complete") -> None:
    _write_json(
        vault / "runs" / run_id / "run-ledger.json",
        {
            "$schema": "ops/schemas/run-ledger.schema.json",
            "run_id": run_id,
            "status": status,
            "events": [
                {
                    "ts": ts,
                    "type": "promotion_recorded",
                    "summary": "promotion recorded",
                    "artifacts": [f"runs/{run_id}/promotion-report.json"],
                    "decision": "PROMOTE",
                }
            ],
        },
    )


def _write_promotion_report(
    vault: Path,
    run_id: str,
    *,
    decision: str,
    primary_targets: list[str],
) -> None:
    _write_json(
        vault / "runs" / run_id / "promotion-report.json",
        {
            "$schema": "ops/schemas/promotion-report.schema.json",
            "run_id": run_id,
            "mode": "report_only",
            "artifact_class": "system_mechanism",
            "decision": decision,
            "summary": "promotion summary",
            "primary_targets": primary_targets,
            "supporting_targets": [],
            "checks": [{"id": "candidate_eval", "status": "PASS", "detail": "ok"}],
            "signoff": {
                "required": False,
                "status": "not_required",
                "by": "auto-improve",
                "ts": "2026-04-15T12:00:00Z",
            },
            "log": {
                "required": True,
                "page": "system/system-log.md",
                "summary": "log summary",
                "status": "recorded",
                "entry_ref": "system/system-log.md#run",
            },
            "history": {
                "status": "active",
                "reason": "",
                "by": "auto-improve",
                "ts": "2026-04-15T12:00:00Z",
            },
            "next_action": "monitor",
        },
    )


class ObservabilityArtifactsRuntimeTests(unittest.TestCase):
    def test_run_artifact_fingerprint_records_schema_backed_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-observe"
            telemetry_rel = write_run_telemetry(
                vault,
                run_id,
                {
                    "$schema": "ops/schemas/run-telemetry.schema.json",
                    "session_id": "session-observe",
                    "run_id": run_id,
                    "generated_at": "2026-04-15T12:00:00Z",
                    "proposal_id": "proposal-observe",
                    "proposal_snapshot": "",
                    "scope_freeze": "",
                    "routing_reports": [],
                    "executor_reports": [],
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "test_files": ["tests/test_example.py"],
                    "phase_durations": {"routing": 1.0},
                    "failure_taxonomy": "",
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {"run_id": run_id},
                },
            )

            _write_json(
                vault / "ops" / "reports" / "supply-chain-provenance.json",
                {
                    "generated_at": "2026-04-15T11:00:00Z",
                    "status": "pass",
                    "inputs": [],
                    "ci_install_proof": {},
                    "lock_evidence": {},
                }
            )
            provenance_bytes = (vault / "ops" / "reports" / "supply-chain-provenance.json").read_bytes()

            rel_path = write_run_artifact_fingerprint(vault, run_id, context=fixed_context())
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            telemetry_bytes = (vault / telemetry_rel).read_bytes()

            self.assertEqual(rel_path, f"runs/{run_id}/run-artifact-fingerprint.json")
            self.assertEqual(payload["generated_at"], "2026-04-15T12:00:00Z")
            self.assertEqual(payload["summary"]["artifact_count"], 1)
            self.assertEqual(payload["summary"]["schema_backed_count"], 1)
            self.assertEqual(payload["artifacts"][0]["path"], telemetry_rel)
            self.assertEqual(payload["artifacts"][0]["artifact_role"], "run_telemetry")
            self.assertEqual(payload["artifacts"][0]["schema"], "ops/schemas/run-telemetry.schema.json")
            self.assertEqual(payload["repo_provenance_snapshot"]["exists_at_run_start"], True)
            self.assertEqual(payload["repo_provenance_snapshot"]["report_status"], "pass")
            self.assertEqual(payload["repo_provenance_snapshot"]["report_generated_at"], "2026-04-15T11:00:00Z")
            self.assertEqual(payload["repo_provenance_snapshot"]["report_sha256"], hashlib.sha256(provenance_bytes).hexdigest())
            self.assertEqual(payload["artifacts"][0]["sha256"], hashlib.sha256(telemetry_bytes).hexdigest())

    def test_run_artifact_fingerprint_writes_archive_path_for_archived_only_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-archived-fingerprint"
            run_dir = vault / "runs" / "archive" / run_id
            run_dir.mkdir(parents=True)
            archived_stdout = run_dir / "mutation-command.stdout.txt"
            archived_stdout.write_text("", encoding="utf-8")

            rel_path = write_run_artifact_fingerprint(
                vault,
                run_id,
                context=fixed_context(),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            stdout_entry = next(
                item
                for item in payload["artifacts"]
                if item["path"] == f"runs/archive/{run_id}/mutation-command.stdout.txt"
            )

            self.assertEqual(
                rel_path,
                f"runs/archive/{run_id}/run-artifact-fingerprint.json",
            )
            self.assertFalse((vault / "runs" / run_id).exists())
            self.assertEqual(stdout_entry["artifact_role"], "command_stdout")
            self.assertEqual(stdout_entry["schema"], "")
            self.assertEqual(stdout_entry["size_bytes"], 0)
            self.assertEqual(stdout_entry["sha256"], hashlib.sha256(b"").hexdigest())
            self.assertFalse(
                payload["repo_provenance_snapshot"]["exists_at_run_start"]
            )
            self.assertEqual(payload["repo_provenance_snapshot"]["report_sha256"], "")

    def test_run_artifact_fingerprint_classifies_timeout_failure_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-timeout-fingerprint"
            timeout_rel = write_timeout_failure_artifact(
                vault,
                run_id,
                phase="repo_health",
                command={"argv": ["python", "-m", "pytest"]},
                result={
                    "returncode": -15,
                    "timed_out": True,
                    "timeout_seconds": 10,
                    "termination_reason": "timeout",
                },
                artifacts={
                    "stdout": f"runs/{run_id}/repo-health.stdout.txt",
                    "stderr": f"runs/{run_id}/repo-health.stderr.txt",
                },
                context=fixed_context(),
            )

            rel_path = write_run_artifact_fingerprint(vault, run_id, context=fixed_context())
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            timeout_entry = next(item for item in payload["artifacts"] if item["path"] == timeout_rel)

            self.assertEqual(timeout_entry["artifact_role"], "timeout_failure")
            self.assertEqual(timeout_entry["schema"], "ops/schemas/timeout-failure.schema.json")

    def test_run_artifact_fingerprint_classifies_structural_complexity_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-structural-fingerprint"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True)
            _write_json(
                run_dir / "structural-complexity-budget.json",
                {
                    "$schema": "ops/schemas/structural-complexity-budget-report.schema.json",
                    "artifact_kind": "structural_complexity_budget_report",
                    "status": "pass",
                },
            )

            rel_path = write_run_artifact_fingerprint(vault, run_id, context=fixed_context())
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            structural_entry = next(
                item
                for item in payload["artifacts"]
                if item["path"] == f"runs/{run_id}/structural-complexity-budget.json"
            )

            self.assertEqual(structural_entry["artifact_role"], "structural_complexity_budget")
            self.assertEqual(
                structural_entry["schema"],
                "ops/schemas/structural-complexity-budget-report.schema.json",
            )

    def test_run_artifact_fingerprint_uses_bundled_schema_when_vault_schema_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-fallback-fingerprint"
            write_run_telemetry(
                vault,
                run_id,
                {
                    "$schema": "ops/schemas/run-telemetry.schema.json",
                    "session_id": "session-fallback",
                    "run_id": run_id,
                    "generated_at": "2026-04-15T12:00:00Z",
                    "proposal_id": "proposal-fallback",
                    "proposal_snapshot": "",
                    "scope_freeze": "",
                    "routing_reports": [],
                    "executor_reports": [],
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "test_files": ["tests/test_example.py"],
                    "phase_durations": {"routing": 1.0},
                    "failure_taxonomy": "",
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {"run_id": run_id},
                },
            )
            (vault / "ops" / "schemas" / "run-artifact-fingerprint.schema.json").unlink()

            rel_path = write_run_artifact_fingerprint(vault, run_id, context=fixed_context())
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            self.assertEqual(rel_path, f"runs/{run_id}/run-artifact-fingerprint.json")
            self.assertEqual(payload["$schema"], "ops/schemas/run-artifact-fingerprint.schema.json")

    def test_promotion_decision_trends_rolls_up_all_runs_and_truncates_recent_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")

            _write_ledger(vault, "run-older", ts="2026-04-15T10:00:00Z")
            _write_promotion_report(
                vault,
                "run-older",
                decision="HOLD",
                primary_targets=["ops/scripts/older.py"],
            )
            _write_ledger(vault, "run-newer", ts="2026-04-15T11:00:00Z")
            _write_promotion_report(
                vault,
                "run-newer",
                decision="PROMOTE",
                primary_targets=["ops/scripts/newer.py"],
            )

            rel_path = write_promotion_decision_trends(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
                recent_window=1,
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            self.assertEqual(rel_path, "ops/reports/promotion-decision-trends.json")
            self.assertEqual(payload["summary"]["runs_discovered"], 2)
            self.assertEqual(payload["summary"]["promotion_reports_considered"], 2)
            self.assertEqual(payload["summary"]["finalized_count"], 2)
            self.assertEqual(payload["decision_counts"], {"HOLD": 1, "PROMOTE": 1})
            self.assertEqual(payload["artifact_class_counts"], {"system_mechanism": 2})
            self.assertEqual([item["run_id"] for item in payload["recent_runs"]], ["run-newer"])
            self.assertEqual(payload["recent_runs"][0]["decision_record"]["decision"], "PROMOTE")
            self.assertEqual(
                payload["recent_runs"][0]["decision_record"]["source_rule"],
                "legacy_top_level_decision",
            )

    def test_promotion_decision_trends_does_not_fallback_from_invalid_vault_schema_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")

            _write_ledger(vault, "run-schema-error", ts="2026-04-15T10:00:00Z")
            _write_promotion_report(
                vault,
                "run-schema-error",
                decision="PROMOTE",
                primary_targets=["ops/scripts/example.py"],
            )
            (vault / "ops" / "schemas" / "promotion-decision-trends.schema.json").write_text(
                "{not-json",
                encoding="utf-8",
            )

            with self.assertRaises(json.JSONDecodeError):
                write_promotion_decision_trends(
                    vault,
                    policy,
                    policy_path,
                    context=fixed_context(),
                    recent_window=5,
                )

    def test_outcome_metrics_report_uses_sessions_and_telemetry_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            target = "ops/scripts/example.py"

            _write_json(
                vault / "runs" / "run-a" / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T01:00:00Z",
                    "session_id": "auto-session",
                    "proposal_id": "proposal-a",
                    "source_candidate_id": "candidate-a",
                    "primary_targets": [target],
                    "executor_reports": [],
                    "phase_durations": {"experiment": 1.0},
                    "decision": "PROMOTE",
                },
            )
            _write_json(
                vault / "runs" / "run-b" / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T02:00:00Z",
                    "session_id": "auto-session",
                    "proposal_id": "proposal-a",
                    "source_candidate_id": "candidate-a",
                    "primary_targets": [target],
                    "executor_reports": [],
                    "phase_durations": {"experiment": 2.0},
                    "rollback_rehearsal_report": "runs/run-b/rollback-rehearsal-report.json",
                    "decision": "HOLD",
                },
            )
            _write_json(vault / "runs" / "run-b" / "rollback-rehearsal-report.json", {"status": "fail"})
            _write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "auto-session.json",
                {
                    "session_id": "auto-session",
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "proposal-a",
                            "source_candidate_id": "candidate-a",
                            "run_id": "run-a",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                        {
                            "index": 2,
                            "proposal_id": "proposal-a",
                            "source_candidate_id": "candidate-a",
                            "run_id": "run-b",
                            "status": "blocked",
                            "outcome": "hold",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            _write_json(
                vault / "runs" / "run-c" / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T03:00:00Z",
                    "proposal_id": "",
                    "primary_targets": ["ops/scripts/standalone.py"],
                    "executor_reports": [],
                    "phase_durations": {"experiment": 3.0},
                    "decision": "DISCARD",
                },
            )

            rel_path = write_outcome_metrics_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
                recent_window=2,
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            envelope_schema = load_schema(ENVELOPE_SCHEMA_PATH)

            self.assertEqual(rel_path, "ops/reports/outcome-metrics.json")
            self.assertEqual(validate_with_schema(payload, envelope_schema), [])
            self.assertEqual(payload["summary"]["attempts_considered"], 3)
            self.assertEqual(payload["summary"]["session_reports_considered"], 1)
            self.assertEqual(payload["metrics"]["rework_count"], 1)
            self.assertEqual(payload["metrics"]["moving_averages"]["hold"], 0.5)
            self.assertEqual(payload["metrics"]["moving_averages"]["discard"], 0.5)
            self.assertEqual(payload["metrics"]["moving_averages"]["rollback_signal"], 0.5)
            self.assertEqual(payload["metrics"]["rollback_signal_count"], 1)
            self.assertEqual(payload["metrics"]["defect_escape_proxy"]["count"], 1)
            self.assertEqual(payload["recent_attempts"][0]["run_id"], "run-c")
            self.assertEqual(payload["recent_attempts"][0]["source_candidate_id"], "")
            self.assertEqual(payload["recent_attempts"][0]["run_telemetry"], "runs/run-c/run-telemetry.json")
            self.assertEqual(payload["recent_attempts"][0]["promotion_report"], "")
            self.assertEqual(payload["recent_attempts"][1]["run_id"], "run-b")
            self.assertEqual(payload["recent_attempts"][1]["source_candidate_id"], "candidate-a")

    def test_outcome_metrics_filters_closed_defect_escape_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            target = "ops/scripts/example.py"
            _write_json(
                vault / "runs" / "run-promote" / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T01:00:00Z",
                    "proposal_id": "proposal-a",
                    "primary_targets": [target],
                    "decision": "PROMOTE",
                },
            )
            _write_json(
                vault / "runs" / "run-hold" / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T02:00:00Z",
                    "proposal_id": "proposal-a",
                    "primary_targets": [target],
                    "decision": "HOLD",
                },
            )
            _write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "auto-session.json",
                {
                    "session_id": "auto-session",
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "proposal-a",
                            "run_id": "run-promote",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                        {
                            "index": 2,
                            "proposal_id": "proposal-a",
                            "run_id": "run-hold",
                            "status": "blocked",
                            "outcome": "hold",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            _write_json(
                vault / "ops" / "reports" / "defect-escape-closures.json",
                {
                    "$schema": "ops/schemas/defect-escape-closures.schema.json",
                    "artifact_kind": "defect_escape_closures",
                    "generated_at": "2026-04-15T12:00:00Z",
                    "summary": {"closure_count": 1},
                    "closures": [
                        {
                            "target": target,
                            "promoted_run_id": "run-promote",
                            "escaped_run_id": "run-hold",
                            "closure_status": "superseded",
                            "closure_reason": "newer run closed the escaped HOLD",
                            "superseding_run_id": "run-followup",
                            "closed_at": "2026-04-15T12:00:00Z",
                            "evidence_refs": ["runs/run-followup/promotion-report.json"],
                        }
                    ],
                },
            )

            rel_path = write_outcome_metrics_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            defect_escape = payload["metrics"]["defect_escape_proxy"]
            self.assertEqual(defect_escape["count"], 0)
            self.assertEqual(defect_escape["pairs"], [])
            self.assertEqual(defect_escape["closed_count"], 1)
            self.assertEqual(defect_escape["closed_pairs"][0]["target"], target)
            self.assertEqual(defect_escape["closed_pairs"][0]["closure_status"], "superseded")

    def test_outcome_metrics_filters_closed_rework_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            target = "ops/scripts/example.py"
            for index, run_id in enumerate(("run-a", "run-b"), start=1):
                _write_json(
                    vault / "runs" / run_id / "run-telemetry.json",
                    {
                        "generated_at": f"2026-04-15T0{index}:00:00Z",
                        "proposal_id": "proposal-a",
                        "primary_targets": [target],
                        "decision": "PROMOTE",
                    },
                )
            _write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "auto-session.json",
                {
                    "session_id": "auto-session",
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "proposal-a",
                            "run_id": "run-a",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                        {
                            "index": 2,
                            "proposal_id": "proposal-a",
                            "run_id": "run-b",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                    ],
                },
            )
            _write_json(
                vault / "ops" / "reports" / "rework-closures.json",
                {
                    "$schema": "ops/schemas/rework-closures.schema.json",
                    "artifact_kind": "rework_closures",
                    "generated_at": "2026-04-15T12:00:00Z",
                    "summary": {"closure_count": 1, "closed_rework_count": 1},
                    "closures": [
                        {
                            "rework_key": "proposal:proposal-a",
                            "primary_targets": [target],
                            "closure_status": "superseded",
                            "closure_reason": "newer run closed repeated rework",
                            "superseding_run_id": "run-followup",
                            "closed_at": "2026-04-15T12:00:00Z",
                            "closed_run_ids": ["run-a", "run-b"],
                            "evidence_refs": ["runs/run-followup/promotion-report.json"],
                        }
                    ],
                },
            )

            rel_path = write_outcome_metrics_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            metrics = payload["metrics"]
            self.assertEqual(metrics["raw_rework_count"], 1)
            self.assertEqual(metrics["rework_count"], 0)
            self.assertEqual(metrics["rework_keys"], [])
            self.assertEqual(metrics["closed_rework_count"], 1)
            self.assertEqual(metrics["closed_rework_keys"][0]["key"], "proposal:proposal-a")
            self.assertEqual(metrics["closed_rework_keys"][0]["closure_status"], "superseded")

    def test_outcome_metrics_keeps_open_rework_closures_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            target = "ops/scripts/example.py"
            _write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "auto-session.json",
                {
                    "session_id": "auto-session",
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "proposal-a",
                            "run_id": "run-a",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                        {
                            "index": 2,
                            "proposal_id": "proposal-a",
                            "run_id": "run-b",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                    ],
                },
            )
            for index, run_id in enumerate(("run-a", "run-b"), start=1):
                _write_json(
                    vault / "runs" / run_id / "run-telemetry.json",
                    {
                        "generated_at": f"2026-04-15T0{index}:00:00Z",
                        "proposal_id": "proposal-a",
                        "primary_targets": [target],
                        "decision": "PROMOTE",
                    },
                )
            _write_json(
                vault / "ops" / "reports" / "rework-closures.json",
                {
                    "$schema": "ops/schemas/rework-closures.schema.json",
                    "artifact_kind": "rework_closures",
                    "generated_at": "2026-04-15T12:00:00Z",
                    "summary": {"closure_count": 1, "closed_rework_count": 0},
                    "closures": [
                        {
                            "rework_key": "proposal:proposal-a",
                            "closure_status": "open",
                            "closure_reason": "operator has not approved closure",
                            "superseding_run_id": "",
                            "closed_at": "",
                            "closed_run_ids": ["run-a", "run-b"],
                            "evidence_refs": [],
                        }
                    ],
                },
            )

            rel_path = write_outcome_metrics_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            metrics = payload["metrics"]
            self.assertEqual(metrics["raw_rework_count"], 1)
            self.assertEqual(metrics["rework_count"], 1)
            self.assertEqual(metrics["closed_rework_count"], 0)
            self.assertEqual(metrics["closed_rework_keys"], [])

    def test_outcome_metrics_and_promotion_trends_share_run_set_for_overlapping_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")

            _write_ledger(vault, "run-a", ts="2026-04-15T01:00:00Z")
            _write_promotion_report(
                vault,
                "run-a",
                decision="PROMOTE",
                primary_targets=["ops/scripts/example_a.py"],
            )
            _write_json(
                vault / "runs" / "run-a" / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T01:00:00Z",
                    "session_id": "auto-session-consistency",
                    "proposal_id": "proposal-a",
                    "primary_targets": ["ops/scripts/example_a.py"],
                    "executor_reports": [],
                    "phase_durations": {"experiment": 1.0},
                    "decision": "PROMOTE",
                },
            )

            _write_ledger(vault, "run-b", ts="2026-04-15T02:00:00Z")
            _write_promotion_report(
                vault,
                "run-b",
                decision="HOLD",
                primary_targets=["ops/scripts/example_b.py"],
            )
            _write_json(
                vault / "runs" / "run-b" / "run-telemetry.json",
                {
                    "generated_at": "2026-04-15T02:00:00Z",
                    "session_id": "auto-session-consistency",
                    "proposal_id": "proposal-b",
                    "primary_targets": ["ops/scripts/example_b.py"],
                    "executor_reports": [],
                    "phase_durations": {"experiment": 2.0},
                    "decision": "HOLD",
                },
            )

            _write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "auto-session-consistency.json",
                {
                    "session_id": "auto-session-consistency",
                    "run_ids": ["run-a", "run-b"],
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "proposal-a",
                            "run_id": "run-a",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                        {
                            "index": 2,
                            "proposal_id": "proposal-b",
                            "run_id": "run-b",
                            "status": "blocked",
                            "outcome": "hold",
                            "decision": "HOLD",
                        },
                    ],
                },
            )

            outcome_rel = write_outcome_metrics_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
                recent_window=10,
            )
            trends_rel = write_promotion_decision_trends(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
                recent_window=10,
            )
            outcome_payload = json.loads((vault / outcome_rel).read_text(encoding="utf-8"))
            trends_payload = json.loads((vault / trends_rel).read_text(encoding="utf-8"))

            self.assertEqual(outcome_payload["summary"]["attempts_considered"], 2)
            self.assertEqual(outcome_payload["summary"]["session_reports_considered"], 1)
            self.assertEqual(
                {item["run_id"] for item in outcome_payload["recent_attempts"]},
                {"run-a", "run-b"},
            )
            self.assertEqual(
                {item["run_id"] for item in trends_payload["recent_runs"]},
                {"run-a", "run-b"},
            )
            self.assertEqual(outcome_payload["recent_attempts"][0]["run_id"], "run-b")
            self.assertEqual(trends_payload["recent_runs"][0]["run_id"], "run-b")

    def test_outcome_metrics_uses_standalone_session_only_for_missing_session_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")

            for run_id, decision in (("run-a", "HOLD"), ("run-b", "PROMOTE")):
                _write_json(
                    vault / "runs" / run_id / "run-telemetry.json",
                    {
                        "generated_at": f"2026-04-15T0{1 if run_id == 'run-a' else 2}:00:00Z",
                        "proposal_id": f"proposal-{run_id}",
                        "primary_targets": ["ops/scripts/example.py"],
                        "decision": decision,
                    },
                )
            _write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "auto-session-specific.json",
                {
                    "session_id": "auto-session-specific",
                    "run_ids": ["run-a"],
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "proposal-run-a",
                            "run_id": "run-a",
                            "status": "blocked",
                            "outcome": "hold",
                            "decision": "HOLD",
                        }
                    ],
                },
            )
            _write_json(
                vault / "ops" / "reports" / "auto-improve-sessions" / "standalone-run-telemetry.json",
                {
                    "session_id": "standalone-run-telemetry",
                    "run_ids": ["run-a", "run-b"],
                    "iterations": [
                        {
                            "index": 1,
                            "proposal_id": "proposal-run-a",
                            "run_id": "run-a",
                            "status": "blocked",
                            "outcome": "hold",
                            "decision": "HOLD",
                        },
                        {
                            "index": 2,
                            "proposal_id": "proposal-run-b",
                            "run_id": "run-b",
                            "status": "complete",
                            "outcome": "promoted",
                            "decision": "PROMOTE",
                        },
                    ],
                },
            )

            outcome_rel = write_outcome_metrics_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
                recent_window=10,
            )
            outcome_payload = json.loads((vault / outcome_rel).read_text(encoding="utf-8"))

            self.assertEqual(outcome_payload["summary"]["attempts_considered"], 2)
            self.assertEqual(
                [item["run_id"] for item in outcome_payload["recent_attempts"]],
                ["run-b", "run-a"],
            )
            self.assertEqual(
                {item["session_id"] for item in outcome_payload["recent_attempts"]},
                {"standalone-run-telemetry", "auto-session-specific"},
            )

    def test_outcome_metrics_falls_back_to_top_level_decision_when_decision_record_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            run_id = "run-invalid-decision-record"

            _write_promotion_report(
                vault,
                run_id,
                decision="PROMOTE",
                primary_targets=["ops/scripts/example.py"],
            )
            promotion_report_path = vault / "runs" / run_id / "promotion-report.json"
            promotion_payload = json.loads(promotion_report_path.read_text(encoding="utf-8"))
            promotion_payload["decision_record"] = {"decision": "PROMOTE"}
            promotion_report_path.write_text(
                json.dumps(promotion_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            outcome_rel = write_outcome_metrics_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(),
                recent_window=10,
            )
            outcome_payload = json.loads((vault / outcome_rel).read_text(encoding="utf-8"))

            self.assertEqual(outcome_payload["summary"]["attempts_considered"], 1)
            self.assertEqual(outcome_payload["recent_attempts"][0]["run_id"], run_id)
            self.assertEqual(outcome_payload["recent_attempts"][0]["decision"], "PROMOTE")
            self.assertEqual(outcome_payload["recent_attempts"][0]["outcome"], "promoted")

    def test_routing_provenance_aggregate_links_session_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-session"
            policy, policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            policy_identity = {"path": str(policy_path.relative_to(vault)), "version": policy["version"]}

            _write_json(
                vault / "runs" / run_id / "scope-freeze.json",
                {
                    "$schema": "ops/schemas/proposal-scope.schema.json",
                    "run_id": run_id,
                    "proposal_id": "proposal-session",
                    "source_candidate_id": "candidate-session",
                    "generated_at": "2026-04-15T12:00:00Z",
                    "policy": policy_identity,
                    "status": "runnable",
                    "inputs": {
                        "primary_targets": ["ops/scripts/example.py"],
                        "supporting_targets": ["tests/test_example.py"],
                    },
                    "resolution": {
                        "test_files": ["tests/test_example.py"],
                        "risk_flags": ["contract_change"],
                        "blocked_by": [],
                    },
                    "apply_guardrails": {"allowed_apply_roots": ["ops/", "tests/"]},
                    "dispatch": {"worker": True, "validator": True, "reviewer": False, "auditors": []},
                },
            )
            _write_json(
                vault / "runs" / run_id / "subagent-routing.worker.json",
                {
                    "role": "worker",
                    "complexity_profile": {"risk_flags": ["contract_change"]},
                    "routing_decision": {
                        "selected_rung": 2,
                        "score_band": "low",
                        "sandbox_mode": "workspace-write",
                        "model": "gpt-5.5",
                        "reasoning_effort": "high",
                    },
                },
            )
            _write_json(
                vault / "runs" / run_id / "worker-executor-report.json",
                {
                    "$schema": "ops/schemas/executor-report.schema.json",
                    "run_id": run_id,
                    "role": "worker",
                    "status": "pass",
                    "result": {"returncode": 0},
                },
            )
            write_run_telemetry(
                vault,
                run_id,
                {
                    "$schema": "ops/schemas/run-telemetry.schema.json",
                    "session_id": "auto-session",
                    "run_id": run_id,
                    "generated_at": "2026-04-15T12:00:00Z",
                    "proposal_id": "proposal-session",
                    "source_candidate_id": "candidate-session",
                    "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                    "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                    "routing_reports": [f"runs/{run_id}/subagent-routing.worker.json"],
                    "executor_reports": [f"runs/{run_id}/worker-executor-report.json"],
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": ["tests/test_example.py"],
                    "test_files": ["tests/test_example.py"],
                    "phase_durations": {"routing": 0.5, "execution": 2.0},
                    "failure_taxonomy": "",
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {"run_id": run_id},
                },
            )
            write_run_artifact_fingerprint(vault, run_id, context=fixed_context())
            session = {
                "session_id": "auto-session",
                "path": "ops/reports/auto-improve-sessions/auto-session.json",
                "policy": policy_identity,
                "run_ids": [run_id],
                "iterations": [
                    {
                        "index": 0,
                        "proposal_id": "proposal-session",
                        "source_candidate_id": "candidate-session",
                        "run_id": run_id,
                        "status": "complete",
                        "outcome": "promoted",
                        "decision": "PROMOTE",
                    }
                ],
            }

            rel_path = write_routing_provenance_aggregate(vault, session, context=fixed_context())
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            self.assertEqual(rel_path, "ops/reports/routing-provenance-aggregates/auto-session.json")
            self.assertEqual(payload["summary"]["run_count"], 1)
            self.assertEqual(payload["summary"]["routing_report_count"], 1)
            self.assertEqual(payload["summary"]["executor_report_count"], 1)
            self.assertEqual(payload["summary"]["artifact_fingerprint_count"], 1)
            self.assertEqual(payload["audit_rollup"]["coverage"]["runs_with_routing"], 1)
            self.assertEqual(payload["audit_rollup"]["coverage"]["runs_with_executor"], 1)
            self.assertEqual(payload["audit_rollup"]["routing"]["role_counts"], {"worker": 1})
            self.assertEqual(payload["audit_rollup"]["routing"]["selected_rung_counts"], {"2": 1})
            self.assertEqual(payload["audit_rollup"]["routing"]["risk_flag_counts"], {"contract_change": 1})
            self.assertEqual(payload["audit_rollup"]["executor"]["status_counts"], {"pass": 1})
            self.assertEqual(payload["audit_rollup"]["telemetry"]["phase_totals_seconds"]["execution"], 2.0)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["attempt_count"], 1)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["finalized_run_count"], 1)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["coverage_ratios"]["telemetry"], 1.0)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["health_flags"], [])
            self.assertEqual(payload["runs"][0]["roles"], ["worker"])
            self.assertEqual(payload["runs"][0]["source_candidate_id"], "candidate-session")
            self.assertEqual(payload["runs"][0]["risk_flags"], ["contract_change"])
            self.assertEqual(
                payload["runs"][0]["artifacts"]["run_artifact_fingerprint"],
                f"runs/{run_id}/run-artifact-fingerprint.json",
            )
            event_log = (
                vault
                / "ops"
                / "reports"
                / "runtime-events"
                / "observability-artifacts"
                / "auto-session.jsonl"
            )
            events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["phase"], "routing_provenance_aggregate")
            self.assertEqual(events[0]["decision"], "written")

    def test_routing_provenance_aggregate_tolerates_malformed_routing_report_and_missing_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            run_id = "run-routing-fault"
            run_dir = vault / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                run_dir / "scope-freeze.json",
                {
                    "$schema": "ops/schemas/proposal-scope.schema.json",
                    "run_id": run_id,
                    "proposal_id": "proposal-fault",
                    "source_candidate_id": "candidate-fault",
                    "generated_at": "2026-04-15T12:00:00Z",
                    "policy": {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": policy["version"]},
                    "status": "runnable",
                    "inputs": {
                        "primary_targets": ["ops/scripts/faulty.py"],
                        "supporting_targets": ["tests/test_faulty.py"],
                    },
                    "resolution": {
                        "test_files": ["tests/test_faulty.py"],
                        "risk_flags": ["manual_review"],
                        "blocked_by": [],
                    },
                    "apply_guardrails": {"allowed_apply_roots": ["ops/", "tests/"]},
                    "dispatch": {
                        "worker": True,
                        "validator": False,
                        "reviewer": False,
                        "auditors": [],
                    },
                },
            )
            _write_json(
                run_dir / "proposal-snapshot.json",
                {
                    "$schema": "ops/schemas/proposal-snapshot.schema.json",
                    "run_id": run_id,
                    "source_report": "ops/reports/mutation-proposals.json",
                    "captured_at": "2026-04-15T12:00:00Z",
                    "proposal": {
                        "proposal_id": "proposal-fault",
                        "source_candidate_id": "candidate-fault",
                        "source_candidate_type": "mechanism_eval_stagnation_candidate",
                        "family": "contract_regression_signals",
                        "tier": "supporting",
                        "priority": 40,
                        "primary_targets": ["ops/scripts/faulty.py"],
                        "supporting_targets": ["tests/test_faulty.py"],
                        "metrics_triggered": ["stage1_same_eval_rate"],
                        "run_ids": ["run-fault-a"],
                        "failure_mode": "repeated_same_eval_or_discard",
                        "single_mechanism_scope": "change faulty.py only",
                        "change_hypothesis": "narrowed change should help",
                        "expected_binary_signal": "PROMOTE or DISCARD",
                        "blast_radius_score": 18,
                        "must_change_tests": ["tests/test_faulty.py"],
                        "must_change_budget_signal": {
                            "signal": "candidate_eval.total_score",
                            "expected_change": "increase_or_equal_score_secondary",
                        },
                        "must_not_expand_apply_roots": True,
                        "must_not_increase_untyped_surface": True,
                        "required_artifacts": ["runs/<run-id>/promotion-report.json"],
                        "blocked_by": [],
                        "priority_breakdown": {
                            "base_priority": 40,
                            "historical_calibration_delta": 0,
                            "session_calibration_delta": 0,
                            "review_candidate_priority": 40,
                            "recent_log_overlap_penalty": 0,
                            "final_priority": 40,
                        },
                        "why_now": "test",
                    },
                },
            )
            (run_dir / "subagent-routing.worker.json").write_text("{", encoding="utf-8")
            session = {
                "session_id": "auto-session-fault",
                "path": "ops/reports/auto-improve-sessions/auto-session-fault.json",
                "policy": {
                    "path": "ops/policies/wiki-maintainer-policy.yaml",
                    "version": policy["version"],
                },
                "run_ids": [run_id],
                "iterations": [
                    {
                        "index": 1,
                        "proposal_id": "proposal-fault",
                        "run_id": run_id,
                        "status": "blocked",
                        "outcome": "validation_blocked",
                        "decision": "HOLD",
                    }
                ],
            }

            rel_path = write_routing_provenance_aggregate(vault, session, context=fixed_context())
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            self.assertEqual(payload["summary"]["run_count"], 1)
            self.assertEqual(payload["summary"]["routing_report_count"], 1)
            self.assertEqual(payload["summary"]["telemetry_report_count"], 0)
            self.assertEqual(payload["audit_rollup"]["routing"]["report_count"], 0)
            self.assertEqual(payload["audit_rollup"]["coverage"]["runs_with_routing"], 1)
            self.assertEqual(payload["audit_rollup"]["coverage"]["runs_with_telemetry"], 0)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["routing_report_parse_gap_count"], 1)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["coverage_ratios"]["telemetry"], 0.0)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["finalized_run_count"], 0)
            self.assertCountEqual(
                payload["audit_rollup"]["loop_health"]["health_flags"],
                [
                    "missing_telemetry_coverage",
                    "routing_report_parse_gap",
                    "unfinalized_runs_present",
                    "recent_hold_present",
                ],
            )
            self.assertEqual(payload["runs"][0]["roles"], [])
            self.assertEqual(payload["runs"][0]["risk_flags"], ["manual_review"])
            self.assertEqual(
                payload["runs"][0]["artifacts"]["proposal_snapshot"],
                f"runs/{run_id}/proposal-snapshot.json",
            )
            self.assertEqual(payload["runs"][0]["artifacts"]["run_telemetry"], "")

    def test_routing_provenance_aggregate_resolves_archived_session_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            run_id = "auto-improve-archive-run-01"
            run_dir = vault / "runs" / "archive" / run_id
            _write_json(
                run_dir / "scope-freeze.json",
                {
                    "$schema": "ops/schemas/proposal-scope.schema.json",
                    "run_id": run_id,
                    "proposal_id": "proposal-archive",
                    "source_candidate_id": "candidate-archive",
                    "generated_at": "2026-04-15T12:00:00Z",
                    "policy": {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": policy["version"]},
                    "status": "runnable",
                    "inputs": {
                        "primary_targets": ["ops/scripts/archive.py"],
                        "supporting_targets": ["tests/test_archive.py"],
                    },
                    "resolution": {
                        "test_files": ["tests/test_archive.py"],
                        "risk_flags": [],
                        "blocked_by": [],
                    },
                    "apply_guardrails": {"allowed_apply_roots": ["ops/", "tests/"]},
                    "dispatch": {"worker": True, "validator": False, "reviewer": False, "auditors": []},
                },
            )
            _write_json(
                run_dir / "subagent-routing.worker.json",
                {
                    "role": "worker",
                    "routing_decision": {
                        "selected_rung": 2,
                        "score_band": "low",
                        "sandbox_mode": "workspace-write",
                        "model": "gpt-5.5",
                        "reasoning_effort": "high",
                    },
                },
            )
            _write_json(
                run_dir / "worker-executor-report.json",
                {"run_id": run_id, "role": "worker", "status": "pass", "result": {"returncode": 0}},
            )
            _write_json(
                run_dir / "run-artifact-fingerprint.json",
                {"artifact_kind": "run_artifact_fingerprint", "run_id": run_id},
            )
            _write_json(
                run_dir / "run-telemetry.json",
                {
                    "$schema": "ops/schemas/run-telemetry.schema.json",
                    "session_id": "auto-session-archive",
                    "run_id": run_id,
                    "generated_at": "2026-04-15T12:00:00Z",
                    "proposal_id": "proposal-archive",
                    "source_candidate_id": "candidate-archive",
                    "proposal_snapshot": f"runs/{run_id}/proposal-snapshot.json",
                    "scope_freeze": f"runs/{run_id}/scope-freeze.json",
                    "routing_reports": [f"runs/{run_id}/subagent-routing.worker.json"],
                    "executor_reports": [f"runs/{run_id}/worker-executor-report.json"],
                    "primary_targets": ["ops/scripts/archive.py"],
                    "supporting_targets": ["tests/test_archive.py"],
                    "test_files": ["tests/test_archive.py"],
                    "phase_durations": {"execution": 1.25},
                    "failure_taxonomy": "",
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {"run_id": run_id},
                },
            )
            session = {
                "session_id": "auto-session-archive",
                "path": "ops/reports/auto-improve-sessions/auto-session-archive.json",
                "policy": {
                    "path": "ops/policies/wiki-maintainer-policy.yaml",
                    "version": policy["version"],
                },
                "run_ids": [run_id],
                "iterations": [
                    {
                        "index": 1,
                        "proposal_id": "proposal-archive",
                        "run_id": run_id,
                        "status": "complete",
                        "outcome": "promoted",
                        "decision": "PROMOTE",
                        "run_telemetry": f"runs/{run_id}/run-telemetry.json",
                    }
                ],
            }

            rel_path = write_routing_provenance_aggregate(vault, session, context=fixed_context())
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            self.assertEqual(payload["summary"]["telemetry_report_count"], 1)
            self.assertEqual(payload["audit_rollup"]["coverage"]["runs_with_telemetry"], 1)
            self.assertEqual(payload["audit_rollup"]["telemetry"]["phase_totals_seconds"], {"execution": 1.25})
            self.assertEqual(payload["audit_rollup"]["loop_health"]["finalized_run_count"], 1)
            self.assertEqual(
                payload["runs"][0]["artifacts"]["run_telemetry"],
                f"runs/archive/{run_id}/run-telemetry.json",
            )
            self.assertEqual(
                payload["runs"][0]["artifacts"]["scope_freeze"],
                f"runs/archive/{run_id}/scope-freeze.json",
            )
            self.assertEqual(payload["runs"][0]["roles"], ["worker"])

    def test_latest_routing_provenance_reconstructs_standalone_run_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _policy_path = load_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            run_id = "run-standalone-telemetry"
            write_run_telemetry(
                vault,
                run_id,
                {
                    "$schema": "ops/schemas/run-telemetry.schema.json",
                    "session_id": "",
                    "run_id": run_id,
                    "generated_at": "2026-04-15T12:00:00Z",
                    "proposal_id": "proposal-standalone",
                    "source_candidate_id": "candidate-standalone",
                    "proposal_snapshot": "",
                    "scope_freeze": "",
                    "routing_reports": [],
                    "executor_reports": [],
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "test_files": ["tests/test_example.py"],
                    "phase_durations": {},
                    "failure_taxonomy": "",
                    "decision": "PROMOTE",
                    "finalized": True,
                    "finalize_result": {"run_id": run_id},
                },
            )
            _write_promotion_report(
                vault,
                run_id,
                decision="PROMOTE",
                primary_targets=["ops/scripts/example.py"],
            )
            _write_json(
                vault
                / "ops"
                / "reports"
                / "auto-improve-sessions"
                / "auto-improve-empty.json",
                {
                    "$schema": "ops/schemas/auto-improve-session.schema.json",
                    "session_id": "auto-improve-empty",
                    "generated_at": "2026-04-16T12:00:00Z",
                    "policy": {
                        "path": "ops/policies/wiki-maintainer-policy.yaml",
                        "version": policy["version"],
                    },
                    "status": "blocked",
                    "budget": {
                        "max_proposals": 1,
                        "max_minutes": 1,
                        "max_consecutive_failures": 1,
                    },
                    "executor": {"name": "codex_exec"},
                    "attempted_proposal_ids": [],
                    "quarantined_proposal_ids": [],
                    "run_ids": [],
                    "iterations": [],
                    "learning_summary": {
                        "attempt_count": 0,
                        "rework_count": 0,
                        "rollback_signal_count": 0,
                        "defect_escape_pair_count": 0,
                        "session_context_status": "no_iterations",
                        "evidence_gaps": ["session.iterations is empty", "session.run_ids is empty"],
                    },
                    "loop_state": {
                        "consecutive_failures": 0,
                        "last_outcome": "",
                        "last_decision": "",
                        "last_run_id": "",
                        "last_blocking_reason": "",
                        "updated_at": "2026-04-16T12:00:00Z",
                    },
                    "rollups": {
                        "iterations": {
                            "count": 0,
                            "outcome_counts": {},
                            "decision_counts": {},
                            "status_counts": {},
                            "quarantined_proposal_count": 0,
                        },
                        "routing": {
                            "report_count": 0,
                            "role_counts": {},
                            "selected_rung_counts": {},
                            "score_band_counts": {},
                            "sandbox_mode_counts": {},
                            "model_counts": {},
                            "reasoning_effort_counts": {},
                            "risk_flag_counts": {},
                        },
                        "executor": {
                            "report_count": 0,
                            "role_counts": {},
                            "status_counts": {},
                            "blocking_role_counts": {},
                            "returncode_counts": {},
                        },
                        "telemetry": {
                            "report_count": 0,
                            "failure_taxonomy_counts": {},
                            "phase_totals_seconds": {},
                            "phase_max_seconds": {},
                        },
                        "outcome_metrics": {
                            "attempt_count": 0,
                            "recent_window": 20,
                            "recent_attempt_count": 0,
                            "rework_count": 0,
                            "rollback_signal_count": 0,
                            "rollback_rehearsal_coverage_count": 0,
                            "moving_averages": {
                                "hold": 0.0,
                                "discard": 0.0,
                                "rollback_signal": 0.0,
                            },
                            "operator_effort_proxy": {
                                "phase_totals_seconds": {},
                                "executor_report_count": 0,
                                "reviewer_dispatch_count": 0,
                                "validator_dispatch_count": 0,
                                "auditor_dispatch_count": 0,
                                "hold_count": 0,
                            },
                            "rework_keys": [],
                            "defect_escape_proxy": {"count": 0, "pairs": []},
                        },
                    },
                    "stop_reason": "blocked_by_learning_gate",
                },
            )

            rel_path = write_latest_routing_provenance_aggregate(
                vault,
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                context=fixed_context(),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            session_payload = json.loads(
                (
                    vault
                    / "ops"
                    / "reports"
                    / "auto-improve-sessions"
                    / "standalone-run-telemetry.json"
                ).read_text(encoding="utf-8")
            )

            self.assertEqual(rel_path, "ops/reports/routing-provenance-aggregates/standalone-run-telemetry.json")
            self.assertEqual(session_payload["session_id"], "standalone-run-telemetry")
            self.assertEqual(session_payload["run_ids"], [run_id])
            self.assertEqual(session_payload["learning_summary"]["session_context_status"], "session_context_available")
            self.assertEqual(payload["summary"]["run_count"], 1)
            self.assertEqual(payload["audit_rollup"]["coverage"]["runs_with_telemetry"], 1)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["coverage_ratios"]["telemetry"], 1.0)
            self.assertEqual(payload["audit_rollup"]["loop_health"]["attempt_count"], 1)
            self.assertNotIn("missing_telemetry_coverage", payload["audit_rollup"]["loop_health"]["health_flags"])


if __name__ == "__main__":
    unittest.main()
