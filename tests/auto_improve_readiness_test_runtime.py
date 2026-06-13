from __future__ import annotations

import dataclasses
import datetime as dt
import json
import tempfile
from pathlib import Path

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext

from tests.minimal_vault_runtime import seed_minimal_vault
from tests.runtime_test_context import frozen_context

REPO_ROOT = Path(__file__).resolve().parents[1]
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"
FIXED_GENERATED_AT = "2026-04-22T04:00:00Z"
VOLATILE_ENVELOPE_DIGEST_FIELDS = {
    "input_fingerprints",
    "source_revision",
    "source_tree_fingerprint",
}
PRIMARY_REPORT_SPECS = {
    "ops/reports/outcome-metrics.json": {
        "schema_path": "ops/schemas/outcome-metrics.schema.json",
        "artifact_kind": "outcome_metrics_report",
    },
    "ops/reports/mechanism-review-candidates.json": {
        "schema_path": "ops/schemas/mechanism-review-candidates.schema.json",
        "artifact_kind": "mechanism_review_candidates_report",
    },
    "ops/reports/mutation-proposals.json": {
        "schema_path": "ops/schemas/mutation-proposals.schema.json",
        "artifact_kind": "mutation_proposals_report",
    },
    "ops/reports/artifact-freshness-report.json": {
        "schema_path": "ops/schemas/artifact-freshness-report.schema.json",
        "artifact_kind": "artifact_freshness_report",
    },
    "ops/reports/test-execution-summary.json": {
        "schema_path": "ops/schemas/test-execution-summary.schema.json",
        "artifact_kind": "test_execution_summary",
    },
    "ops/reports/source-package-clean-extract.json": {
        "schema_path": "ops/schemas/source-package-clean-extract.schema.json",
        "artifact_kind": "source_package_clean_extract",
    },
    "ops/reports/release-closeout-summary.json": {
        "schema_path": "ops/schemas/release-closeout-summary.schema.json",
        "artifact_kind": "release_closeout_summary",
    },
    "ops/reports/release-closeout-batch-manifest.json": {
        "schema_path": "ops/schemas/release-closeout-batch-manifest.schema.json",
        "artifact_kind": "release_closeout_batch_manifest",
    },
    "ops/reports/release-closeout-finality-attestation.json": {
        "schema_path": "ops/schemas/release-closeout-finality-attestation.schema.json",
        "artifact_kind": "release_closeout_finality_attestation",
    },
    "ops/reports/release-evidence-cohort.json": {
        "schema_path": "ops/schemas/release-evidence-cohort.schema.json",
        "artifact_kind": "release_evidence_cohort",
    },
    "tmp/release-closeout-post-check-finalizer.json": {
        "schema_path": "ops/schemas/release-closeout-post-check-finalizer.schema.json",
        "artifact_kind": "release_closeout_post_check_finalizer",
    },
    "ops/reports/remediation-backlog.json": {
        "schema_path": "ops/schemas/remediation-backlog.schema.json",
        "artifact_kind": "remediation_backlog",
    },
}
READINESS_FIXTURE_SCHEMA_NAMES = frozenset(
    {Path(spec["schema_path"]).name for spec in PRIMARY_REPORT_SPECS.values()}
    | {
        "artifact-envelope.schema.json",
        "auto-improve-readiness-report.schema.json",
        "goal-worktree-guard.schema.json",
        "run-telemetry.schema.json",
        "wiki-maintainer-policy.schema.json",
    }
)


def fixed_context() -> RuntimeContext:
    return frozen_context(dt.datetime(2026, 4, 22, 4, 0, tzinfo=dt.UTC))


def _canonical_jsonable(value: object, *, vault_root: Path | None = None) -> object:
    if isinstance(value, RuntimeContext):
        return {
            "display_timezone": value.display_timezone.tzname(None)
            or str(value.display_timezone),
            "generated_at": value.isoformat_z(),
            "session_id": value.session_id,
            "iteration": value.iteration,
            "executor_id": value.executor_id,
        }
    if isinstance(value, Path):
        if vault_root is not None:
            try:
                return value.relative_to(vault_root).as_posix()
            except ValueError:
                pass
        return value.as_posix()
    if dataclasses.is_dataclass(value):
        return {
            field.name: _canonical_jsonable(getattr(value, field.name), vault_root=vault_root)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): (
                f"<normalized:{key}>"
                if str(key) in VOLATILE_ENVELOPE_DIGEST_FIELDS
                else _canonical_jsonable(item, vault_root=vault_root)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_jsonable(item, vault_root=vault_root) for item in value]
    return value


class AutoImproveReadinessRuntimeFixture:
    temp_dir: tempfile.TemporaryDirectory[str]
    vault: Path

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault, schema_names=READINESS_FIXTURE_SCHEMA_NAMES)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
        self._write_report(
            "ops/reports/artifact-freshness-report.json",
            {
                "status": "pass",
                "summary": {
                    "schema_invalid_artifact_count": 0,
                    "stable_contract_debt_issue_count": 0,
                },
                "artifact_records": [],
            },
        )
        self._write_report(
            "ops/reports/test-execution-summary.json",
            {
                "status": "pass",
                "deselection_lifecycle": {"status": "pass"},
            },
        )
        self._write_report(
            "ops/reports/source-package-clean-extract.json",
            {
                "status": "pass",
                "source_package_reproducibility_status": "pass",
                "deselection_budget_status": {"status": "pass"},
            },
        )
        self._write_report(
            "ops/reports/release-closeout-summary.json",
            {
                "status": "pass",
                "clean_release_ready": True,
                "release_readiness_state": "clean_pass",
                "machine_release_allowed": True,
                "operator_release_allowed": True,
            },
        )
        self._write_report(
            "ops/reports/release-closeout-batch-manifest.json",
            {
                "status": "pass",
                "release_authority_status": "clean_pass",
                "sealed_release_status": "sealed_clean_pass",
                "distribution_package": {"status": "materialized"},
            },
        )
        self._write_report(
            "ops/reports/release-closeout-finality-attestation.json",
            {
                "finality_status": "pass",
                "finality_failures": [],
            },
        )
        self._write_report(
            "ops/reports/release-evidence-cohort.json",
            {
                "status": "pass",
                "summary": {"clean_lane_contract_status": "pass"},
                "cohort": {
                    "strict_same_fingerprint": True,
                    "component_fingerprint_count": 1,
                },
            },
        )
        self._write_report(
            "tmp/release-closeout-post-check-finalizer.json",
            {
                "status": "pass",
                "refresh_required": False,
                "affected_path_count": 0,
            },
        )
        self._write_report(
            "ops/reports/release-closeout-sealed-rehearsal-check.json",
            {
                "artifact_kind": "release_closeout_sealed_rehearsal_check",
                "status": "pass",
                "preflight_status": "sealed_clean_pass",
                "distribution_binding_status": "pass",
                "authority_preflight_status": "clean",
                "expected_blocked_preflight": False,
                "failures": [],
                "failure_details": [],
                "blocking_reason_ids": [],
                "summary": "sealed release evidence clean",
            },
            enveloped=False,
        )
        self._write_report(
            "ops/reports/remediation-backlog.json",
            {
                "status": "pass",
                "summary": {
                    "backlog_item_count": 0,
                    "repeated_blocker_count": 0,
                    "active_blocker_count": 0,
                    "open_total_count": 0,
                    "open_promotion_count": 0,
                    "open_repeat_count": 0,
                    "promotion_policy": (
                        "do_not_retry_repeated_blockers_until_backlog_item_closed"
                    ),
                    "next_action": "none",
                },
                "items": [],
                "inputs": {
                    "self_improvement_negative_lessons": (
                        "ops/reports/self-improvement-negative-lessons.json"
                    ),
                    "session_synopsis": "ops/reports/session-synopsis.json",
                    "learning_claim_activation": (
                        "ops/reports/learning_claim_activation_report.json"
                    ),
                    "auto_improve_sessions": "ops/reports/auto-improve-sessions",
                    "goal_runtime_certificate": (
                        "ops/reports/goal-runtime-certificate.json"
                    ),
                    "goal_worktree_guard": "ops/reports/goal-worktree-guard.json",
                    "learning_readiness_signoff": (
                        "ops/reports/learning-readiness-signoff.json"
                    ),
                    "status_overrides": (
                        "ops/policies/remediation-backlog-status-overrides.json"
                    ),
                },
            },
        )
        self._write_goal_worktree_guard()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _canonical_report_payload(self, relative_path: str, payload: dict) -> dict:
        policy, resolved_policy_path = load_policy(
            self.vault, "ops/policies/wiki-maintainer-policy.yaml"
        )
        spec = PRIMARY_REPORT_SPECS[relative_path]
        return {
            **build_canonical_report_envelope(
                self.vault,
                generated_at=FIXED_GENERATED_AT,
                artifact_kind=spec["artifact_kind"],
                producer="tests.auto_improve_readiness_test_runtime",
                source_command="pytest",
                resolved_policy_path=resolved_policy_path,
                schema_path=spec["schema_path"],
                source_paths=[],
            ),
            "vault": ".",
            "policy": {
                "path": report_path(self.vault, resolved_policy_path),
                "version": policy["version"],
            },
            **payload,
        }

    def _write_report(
        self, relative_path: str, payload: dict, *, enveloped: bool = True
    ) -> None:
        if (
            enveloped
            and relative_path in PRIMARY_REPORT_SPECS
            and "artifact_kind" not in payload
        ):
            payload = self._canonical_report_payload(relative_path, payload)
        path = self.vault / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_goal_worktree_guard(
        self,
        *,
        status: str = "pass",
        detected_mode: str = "git_worktree",
        dirty_entry_count: int = 0,
        fatal_blockers: list[str] | None = None,
        promotion_blockers: list[str] | None = None,
        can_execute: bool = True,
        can_promote: bool = True,
    ) -> None:
        _policy, resolved_policy_path = load_policy(
            self.vault, "ops/policies/wiki-maintainer-policy.yaml"
        )
        fatal_blockers = fatal_blockers or []
        promotion_blockers = promotion_blockers or []
        payload = {
            **build_canonical_report_envelope(
                self.vault,
                generated_at=FIXED_GENERATED_AT,
                artifact_kind="goal_worktree_guard",
                producer="ops.scripts.goal_worktree_guard",
                source_command="pytest",
                resolved_policy_path=resolved_policy_path,
                schema_path="ops/schemas/goal-worktree-guard.schema.json",
                source_paths=[],
            ),
            "vault": ".",
            "requested_mode": "git",
            "detected_mode": detected_mode,
            "public_source_layout": {
                "required_paths": [
                    "ops",
                    "tests",
                    "mk",
                    "docs",
                    "README.md",
                    "Makefile",
                ],
                "present": True,
                "missing_paths": [],
            },
            "git": {
                "available": True,
                "inside_worktree": detected_mode == "git_worktree",
                "worktree_root": ".",
                "head_sha": "0" * 40,
                "branch": "main",
                "dirty_entry_count": dirty_entry_count,
                "status_porcelain_sha256": "0" * 64,
                "status_codes": {},
                "error": "",
            },
            "decisions": {
                "can_execute_goal_runtime": can_execute,
                "can_promote_result": can_promote,
                "zip_mode_replay_only": detected_mode == "zip_extract",
                "fatal_blockers": fatal_blockers,
                "promotion_blockers": promotion_blockers,
            },
            "blockers": [
                {
                    "blocker_id": blocker_id,
                    "severity": "fatal" if blocker_id in fatal_blockers else "blocking",
                    "summary": blocker_id,
                    "next_action": "clear goal worktree guard blocker",
                }
                for blocker_id in [*fatal_blockers, *promotion_blockers]
            ],
            "status": status,
        }
        path = self.vault / "ops" / "reports" / "goal-worktree-guard.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_ready_queue_reports(self) -> None:
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
        )
        self._write_report(
            "ops/reports/mechanism-review-candidates.json",
            {
                "summary": {"candidates_emitted": 1},
                "diagnostics": {
                    "bootstrap": {"summary": "candidate queue is available"}
                },
            },
        )
        self._write_report(
            "ops/reports/mutation-proposals.json",
            {
                "summary": {
                    "source_candidates_read": 1,
                    "proposals_emitted": 1,
                    "blocked_proposals": 0,
                    "queue_pressure_summary": "ready",
                },
                "diagnostics": {"evidence_gaps": []},
                "proposals": [
                    {
                        "proposal_id": "proposal-ready",
                        "blocked_by": [],
                        "priority": 55,
                    }
                ],
            },
        )
