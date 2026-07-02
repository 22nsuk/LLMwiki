from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.core.artifact_freshness_payload_runtime import (
    embed_artifact_envelope_metadata,
)
from ops.scripts.core.executor_noop_runtime import (
    EXECUTOR_NOOP_MUTATION_FAILURE_MARKER,
    executor_noop_mutation_failure_message,
)
from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.mechanism.auto_improve_next_run_decision_runtime import (
    CARRY_FORWARD_DECISION,
    OPEN_DECISION_STATUS,
)
from ops.scripts.mechanism.failure_taxonomy_runtime import (
    GENERATED_EVIDENCE_SETTLE_REQUIRED,
)
from ops.scripts.mechanism.mutation_proposal_candidate_runtime import (
    MutationProposal,
    fixed_priority_breakdown,
    generated_must_change_tests,
    must_change_test_paths,
    must_not_expand_apply_roots,
    proposal_blast_radius_score,
    required_artifacts,
    resolve_must_change_tests,
    with_generated_supporting_targets,
)
from ops.scripts.mechanism.next_run_repair_queue_runtime import (
    SOURCE_SESSION_REPORT_DECISION_KEY,
    NextRunRepairProposalDependencies,
    _changed_manifest_extra_scope,
    _diagnostic_note_extra_scope,
    next_run_repair_proposal,
    open_carry_forward_decisions,
)
from tests.test_mechanism_assess import seed_policy

pytestmark = pytest.mark.runtime_hotspot_smoke


def _carry_forward_decision(**overrides: object) -> dict[str, object]:
    decision: dict[str, object] = {
        "decision": CARRY_FORWARD_DECISION,
        "status": OPEN_DECISION_STATUS,
        "decision_id": "next-run-decision:run-1",
        "observed_at": "2026-01-01T00:00:00Z",
        "target_proposal_id": "next_run_failure_repair__target",
        "primary_targets": ["ops/scripts/mechanism/mutation_proposal_runtime.py"],
        "failure_taxonomy": "review_blocked",
    }
    decision.update(overrides)
    return decision


def _next_run_repair_dependencies() -> NextRunRepairProposalDependencies:
    return NextRunRepairProposalDependencies(
        with_generated_supporting_targets=with_generated_supporting_targets,
        must_change_test_paths=must_change_test_paths,
        generated_must_change_tests=generated_must_change_tests,
        resolve_must_change_tests=resolve_must_change_tests,
        proposal_blast_radius_score=proposal_blast_radius_score,
        must_not_expand_apply_roots=must_not_expand_apply_roots,
        required_artifacts=required_artifacts,
        proposal_factory=MutationProposal,
        priority_breakdown_factory=lambda: fixed_priority_breakdown(100),
    )


def test_open_carry_forward_decisions_keeps_latest_decision_per_target() -> None:
    decisions = [
        _carry_forward_decision(
            decision_id="next-run-decision:old",
            observed_at="2026-01-01T00:00:00Z",
            reason="old repair",
        ),
        _carry_forward_decision(
            decision_id="next-run-decision:new",
            observed_at="2026-01-02T00:00:00Z",
            reason="new repair",
        ),
    ]

    open_decisions = open_carry_forward_decisions(
        decisions,
        recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
        recent_log_overlap_unblock_family="queue_unblock",
    )

    assert [decision["decision_id"] for decision in open_decisions] == [
        "next-run-decision:new"
    ]


def test_open_carry_forward_decisions_suppresses_consumed_ids_only() -> None:
    decisions = [
        _carry_forward_decision(decision_id="next-run-decision:consumed"),
        _carry_forward_decision(
            decision_id="next-run-decision:open",
            target_proposal_id="next_run_failure_repair__other",
            primary_targets=["ops/scripts/mechanism/run_mechanism_experiment_runtime.py"],
        ),
    ]

    open_decisions = open_carry_forward_decisions(
        decisions,
        consumed_decision_ids={"next-run-decision:consumed"},
        recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
        recent_log_overlap_unblock_family="queue_unblock",
    )

    assert [decision["decision_id"] for decision in open_decisions] == [
        "next-run-decision:open"
    ]


def test_open_carry_forward_decisions_suppresses_all_missing_leaf_evidence() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    evidence_paths=[
                        "runs/missing-run/run-telemetry.json",
                        "runs/missing-run/reviewer-executor-report.json",
                    ]
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_keeps_structural_missing_leaf_evidence_with_source_session_report() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        session_report = "ops/reports/auto-improve-sessions/session-a.json"
        (vault / session_report).parent.mkdir(parents=True)
        (vault / session_report).write_text('{"next_run_decisions": []}\n', encoding="utf-8")

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="structural_complexity_non_regression",
                    evidence_paths=[
                        "runs/missing-run/run-telemetry.json",
                        "runs/missing-run/promotion-report.json",
                    ],
                    **{SOURCE_SESSION_REPORT_DECISION_KEY: session_report},
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert [decision["decision_id"] for decision in open_decisions] == [
            "next-run-decision:run-1"
        ]


def test_open_carry_forward_decisions_suppresses_source_after_noop_repair_attempt() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        primary_target = "ops/scripts/mechanism/auto_improve_loop.py"
        source_run_id = "run-source"
        source_evidence = vault / "runs" / source_run_id / "worker-executor-report.json"
        source_evidence.parent.mkdir(parents=True, exist_ok=True)
        source_evidence.write_text("{}", encoding="utf-8")
        noop_run_id = "run-noop"
        noop_run = vault / "runs" / noop_run_id
        noop_run.mkdir(parents=True, exist_ok=True)
        (noop_run / "mutation-command.stderr.txt").write_text(
            executor_noop_mutation_failure_message("worker", [primary_target]),
            encoding="utf-8",
        )

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    decision_id="next-run-decision:source",
                    observed_at="2026-01-01T00:00:00Z",
                    proposal_family="queue_unblock",
                    proposal_id="recent_log_overlap_queue_blocked__auto-improve-loop",
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-loop__repo-health-blocked"
                    ),
                    source_run_id=source_run_id,
                    primary_targets=[primary_target],
                    failure_taxonomy="repo_health_blocked",
                    evidence_paths=[
                        f"runs/{source_run_id}/worker-executor-report.json"
                    ],
                ),
                _carry_forward_decision(
                    decision_id="next-run-decision:noop",
                    observed_at="2026-01-02T00:00:00Z",
                    proposal_family="next_run_failure_repair",
                    proposal_id=(
                        "next_run_failure_repair__auto-improve-loop__repo-health-blocked"
                    ),
                    source_candidate_id="next-run-decision:source",
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-loop__mutation-failed"
                    ),
                    source_run_id=noop_run_id,
                    primary_targets=[primary_target],
                    failure_taxonomy="mutation_failed",
                    evidence_paths=[
                        f"runs/{noop_run_id}/mutation-command.stderr.txt"
                    ],
                ),
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_keeps_partially_present_leaf_evidence() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        evidence_path = vault / "runs" / "run-a" / "run-telemetry.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("{}", encoding="utf-8")

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    evidence_paths=[
                        "runs/run-a/run-telemetry.json",
                        "runs/run-a/reviewer-executor-report.json",
                    ]
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert [decision["decision_id"] for decision in open_decisions] == [
            "next-run-decision:run-1"
        ]


def test_open_carry_forward_decisions_keeps_latest_surviving_decision_per_target() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        target_proposal_id = "next_run_failure_repair__target__review-blocked"
        older_evidence = vault / "runs" / "older-run" / "worker-executor-report.json"
        older_evidence.parent.mkdir(parents=True, exist_ok=True)
        older_evidence.write_text("{}", encoding="utf-8")

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    decision_id="next-run-decision:older",
                    observed_at="2026-01-01T00:00:00Z",
                    source_run_id="older-run",
                    target_proposal_id=target_proposal_id,
                    evidence_paths=[
                        "runs/older-run/worker-executor-report.json",
                    ],
                ),
                _carry_forward_decision(
                    decision_id="next-run-decision:newer-missing-evidence",
                    observed_at="2026-01-02T00:00:00Z",
                    source_run_id="newer-run",
                    target_proposal_id=target_proposal_id,
                    evidence_paths=[
                        "runs/newer-run/worker-executor-report.json",
                    ],
                ),
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert [decision["decision_id"] for decision in open_decisions] == [
            "next-run-decision:older"
        ]


def test_open_carry_forward_decisions_suppresses_superseded_queue_rotation() -> None:
    open_decisions = open_carry_forward_decisions(
        [
            _carry_forward_decision(
                failure_taxonomy="mutation_failed",
                proposal_family="queue_unblock",
                proposal_id="recent_log_overlap_queue_blocked__old",
            )
        ],
        current_proposal_ids={"recent_log_overlap_queue_blocked__current"},
        recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
        recent_log_overlap_unblock_family="queue_unblock",
    )

    assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_superseded_queue_validation() -> None:
    open_decisions = open_carry_forward_decisions(
        [
            _carry_forward_decision(
                failure_taxonomy="validation_blocked",
                proposal_family="queue_unblock",
                proposal_id="recent_log_overlap_queue_blocked__retired",
            )
        ],
        current_proposal_ids={"recent_log_overlap_queue_blocked__current"},
        recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
        recent_log_overlap_unblock_family="queue_unblock",
    )

    assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_noop_mutation_repair() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        source_run_id = "run-noop-repair"
        stderr_path = vault / "runs" / source_run_id / "mutation-command.stderr.txt"
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text(
            f"worker {EXECUTOR_NOOP_MUTATION_FAILURE_MARKER}; primary_targets=[target]\n",
            encoding="utf-8",
        )

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="mutation_failed",
                    proposal_family="next_run_failure_repair",
                    proposal_id="next_run_failure_repair__target__repo-health-blocked",
                    source_run_id=source_run_id,
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_resolved_structural_budget() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        seed_policy(vault)
        target = "ops/scripts/mechanism/auto_improve_readiness_runtime.py"
        target_path = vault / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("def ready():\n    return True\n", encoding="utf-8")

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="structural_complexity_non_regression",
                    proposal_family="next_run_failure_repair",
                    proposal_id=(
                        "next_run_failure_repair__auto-improve-readiness-runtime__"
                        "repo-health-blocked"
                    ),
                    primary_targets=[target],
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-readiness-runtime__"
                        "structural-complexity-non-regression"
                    ),
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_keeps_contract_structural_without_source_change_evidence() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        seed_policy(vault)
        target = "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
        target_path = vault / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("def persist():\n    return True\n", encoding="utf-8")

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="structural_complexity_non_regression",
                    proposal_family="contract_regression_signals",
                    proposal_id=(
                        "repeated_same_eval_after_promote__"
                        "auto-improve-iteration-persistence-runtime"
                    ),
                    primary_targets=[target],
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-iteration-persistence-runtime__"
                        "structural-complexity-non-regression"
                    ),
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert [
            decision["target_proposal_id"] for decision in open_decisions
        ] == [
            "next_run_failure_repair__auto-improve-iteration-persistence-runtime__"
            "structural-complexity-non-regression"
        ]


def test_open_carry_forward_decisions_suppresses_contract_structural_after_source_change() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        seed_policy(vault)
        target = "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
        target_path = vault / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("def persist():\n    return True\n", encoding="utf-8")
        source_run_id = "run-structural-contract-repair"
        telemetry_path = vault / "runs" / source_run_id / "run-telemetry.json"
        telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        telemetry_path.write_text(
            json.dumps(
                embed_artifact_envelope_metadata(
                    {"run_id": source_run_id},
                    {
                        "artifact_kind": "run_telemetry",
                        "source_revision": "old",
                        "source_tree_fingerprint": "old-tree",
                    },
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="structural_complexity_non_regression",
                    proposal_family="contract_regression_signals",
                    proposal_id=(
                        "repeated_same_eval_after_promote__"
                        "auto-improve-iteration-persistence-runtime"
                    ),
                    source_run_id=source_run_id,
                    primary_targets=[target],
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-iteration-persistence-runtime__"
                        "structural-complexity-non-regression"
                    ),
                    evidence_paths=[f"runs/{source_run_id}/run-telemetry.json"],
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_worker_structural_preflight_when_current_budget_clean() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        seed_policy(vault)
        target = "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
        target_path = vault / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("def persist():\n    return True\n", encoding="utf-8")
        source_run_id = "run-worker-structural-preflight"
        run_dir = vault / "runs" / source_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "mutation-command.stderr.txt").write_text(
            "worker structural complexity preflight blocked before reviewer/validator/auditor execution\n",
            encoding="utf-8",
        )

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="mutation_failed",
                    proposal_family="contract_regression_signals",
                    proposal_id=(
                        "repeated_same_eval_after_promote__"
                        "auto-improve-iteration-persistence-runtime"
                    ),
                    source_run_id=source_run_id,
                    primary_targets=[target],
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-iteration-persistence-runtime__"
                        "mutation-failed"
                    ),
                    evidence_paths=[
                        f"runs/{source_run_id}/mutation-command.stderr.txt",
                    ],
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_contract_structural_after_source_session_report_change() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        seed_policy(vault)
        target = "ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py"
        target_path = vault / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("def persist():\n    return True\n", encoding="utf-8")
        session_report = "ops/reports/auto-improve-sessions/session-a.json"
        session_report_path = vault / session_report
        session_report_path.parent.mkdir(parents=True, exist_ok=True)
        session_report_path.write_text(
            json.dumps(
                embed_artifact_envelope_metadata(
                    {"session_id": "session-a", "next_run_decisions": []},
                    {
                        "artifact_kind": "auto_improve_session",
                        "source_revision": "old",
                        "source_tree_fingerprint": "old-tree",
                    },
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="structural_complexity_non_regression",
                    proposal_family="contract_regression_signals",
                    proposal_id=(
                        "repeated_same_eval_after_promote__"
                        "auto-improve-iteration-persistence-runtime"
                    ),
                    primary_targets=[target],
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-iteration-persistence-runtime__"
                        "structural-complexity-non-regression"
                    ),
                    evidence_paths=[
                        "runs/missing-run/run-telemetry.json",
                        "runs/missing-run/promotion-report.json",
                    ],
                    **{SOURCE_SESSION_REPORT_DECISION_KEY: session_report},
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_clean_queue_unblock_structural() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        seed_policy(vault)
        target = "ops/scripts/mechanism/auto_improve_execute_runtime.py"
        target_path = vault / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("def execute():\n    return True\n", encoding="utf-8")

        open_decisions = open_carry_forward_decisions(
            [
                _carry_forward_decision(
                    failure_taxonomy="structural_complexity_non_regression",
                    proposal_family="queue_unblock",
                    proposal_id="recent_log_overlap_queue_blocked__auto-improve-execute-runtime",
                    primary_targets=[target],
                    target_proposal_id=(
                        "next_run_failure_repair__auto-improve-execute-runtime__"
                        "structural-complexity-non-regression"
                    ),
                )
            ],
            vault=vault,
            recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
            recent_log_overlap_unblock_family="queue_unblock",
        )

        assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_resolved_generated_evidence_settle() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        source_run_id = "run-generated-evidence-settle"
        report_path = vault / "runs" / source_run_id / "repo-health-artifact-freshness-report-check.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "status": "attention",
                    "recommended_next_action": "regenerate_stale_artifacts",
                    "top_debt_files": [
                        {
                            "path": "ops/reports/generated.json",
                            "issues": ["source_tree_fingerprint_mismatch"],
                            "recommended_next_action": "regenerate_canonical_report",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        with mock.patch(
            "ops.scripts.mechanism.next_run_repair_queue_runtime."
            "_current_artifact_freshness_report",
            return_value={"status": "pass", "top_debt_files": []},
        ):
            open_decisions = open_carry_forward_decisions(
                [
                    _carry_forward_decision(
                        failure_taxonomy=GENERATED_EVIDENCE_SETTLE_REQUIRED,
                        proposal_family="next_run_failure_repair",
                        proposal_id=(
                            "next_run_failure_repair__target__"
                            "generated-evidence-settle-required"
                        ),
                        source_run_id=source_run_id,
                    )
                ],
                vault=vault,
                recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
                recent_log_overlap_unblock_family="queue_unblock",
            )

        assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_resolved_repo_health_generated_evidence() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        source_run_id = "run-repo-health-generated-evidence"
        report_path = vault / "runs" / source_run_id / "repo-health-artifact-freshness-report-check.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "status": "attention",
                    "source_tree_fingerprint": "candidate-workspace-fingerprint",
                    "recommended_next_action": "backfill_artifact_envelope",
                    "top_debt_files": [
                        {
                            "path": "ops/reports/subagent-routing-report.json",
                            "issues": ["missing_artifact_envelope", "unknown_currentness"],
                            "recommended_next_action": "backfill_artifact_envelope",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        with mock.patch(
            "ops.scripts.mechanism.next_run_repair_queue_runtime."
            "_current_artifact_freshness_report",
            return_value={
                "status": "attention",
                "top_debt_files": [
                    {
                        "path": "runs/old-run/command-log-summary.json",
                        "issues": ["missing_artifact_envelope", "unknown_currentness"],
                        "recommended_next_action": "backfill_artifact_envelope",
                    }
                ],
            },
        ):
            open_decisions = open_carry_forward_decisions(
                [
                    _carry_forward_decision(
                        failure_taxonomy="repo_health_blocked",
                        proposal_family="next_run_failure_repair",
                        proposal_id=(
                            "next_run_failure_repair__target__"
                            "repo-health-blocked"
                        ),
                        source_run_id=source_run_id,
                    )
                ],
                vault=vault,
                recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
                recent_log_overlap_unblock_family="queue_unblock",
            )

        assert open_decisions == []


def test_open_carry_forward_decisions_suppresses_stale_run_artifact_schema_debt() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        source_run_id = "run-repo-health-run-artifact-schema-debt"
        report_path = vault / "runs" / source_run_id / "repo-health-artifact-freshness-report-check.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "status": "fail",
                    "source_tree_fingerprint": "candidate-workspace-fingerprint",
                    "recommended_next_action": "regenerate_schema_invalid_artifacts",
                    "top_debt_files": [
                        {
                            "path": "runs/old-run/run-telemetry.json",
                            "issues": ["schema_validation_failed"],
                            "recommended_next_action": "regenerate_canonical_report",
                        },
                        {
                            "path": "runs/old-run/promotion-report.json",
                            "issues": ["missing_artifact_envelope", "unknown_currentness"],
                            "recommended_next_action": "backfill_artifact_envelope",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        with mock.patch(
            "ops.scripts.mechanism.next_run_repair_queue_runtime."
            "_current_artifact_freshness_report",
            return_value={
                "status": "attention",
                "top_debt_files": [
                    {
                        "path": "ops/reports/generated-artifact-index.json",
                        "issues": ["source_tree_fingerprint_mismatch"],
                        "recommended_next_action": "regenerate_canonical_report",
                    }
                ],
            },
        ):
            open_decisions = open_carry_forward_decisions(
                [
                    _carry_forward_decision(
                        failure_taxonomy="repo_health_blocked",
                        proposal_family="next_run_failure_repair",
                        proposal_id=(
                            "next_run_failure_repair__target__"
                            "repo-health-blocked"
                        ),
                        source_run_id=source_run_id,
                    )
                ],
                vault=vault,
                recent_log_overlap_unblock_failure_mode="recent_log_overlap_queue_blocked",
                recent_log_overlap_unblock_family="queue_unblock",
            )

        assert open_decisions == []


def test_changed_manifest_extra_scope_rejects_traversed_source_run_id() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        escape_dir = vault / "escaped" / "run-id"
        escape_dir.mkdir(parents=True)
        extra_test = "tests/test_injected.py"
        (vault / extra_test).parent.mkdir(parents=True, exist_ok=True)
        (vault / extra_test).write_text("def test_injected():\n    assert True\n", encoding="utf-8")
        (escape_dir / "changed-files-manifest.json").write_text(
            json.dumps(
                {
                    "declared_targets": {
                        "primary_targets": ["ops/scripts/example.py"],
                        "test_files": ["tests/test_declared.py"],
                    },
                    "files": [
                        {"path": "tests/test_declared.py"},
                        {"path": extra_test},
                    ],
                }
            ),
            encoding="utf-8",
        )

        supporting, tests = _changed_manifest_extra_scope(
            vault,
            "../escaped/run-id",
            must_change_test_paths=lambda _vault, paths: paths,
        )

        assert supporting == []
        assert tests == []


def test_changed_manifest_extra_scope_adds_files_outside_declared_targets() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        source_run_id = "run-manifest-scope"
        run_dir = vault / "runs" / source_run_id
        run_dir.mkdir(parents=True)
        script_target = "ops/scripts/mechanism/example_runtime.py"
        declared_test = "tests/test_example_runtime.py"
        extra_test = "tests/test_report_schemas.py"
        for rel_path in [script_target, declared_test, extra_test]:
            path = vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# placeholder\n", encoding="utf-8")
        (run_dir / "changed-files-manifest.json").write_text(
            json.dumps(
                {
                    "declared_targets": {
                        "primary_targets": [script_target],
                        "supporting_targets": ["ops/script-output-surfaces.json"],
                        "test_files": [declared_test],
                    },
                    "files": [
                        {"path": script_target},
                        {"path": declared_test},
                        {"path": extra_test},
                    ],
                }
            ),
            encoding="utf-8",
        )

        supporting, tests = _changed_manifest_extra_scope(
            vault,
            source_run_id,
            must_change_test_paths=lambda _vault, paths: paths,
        )

        assert supporting == []
        assert tests == [extra_test]


def test_diagnostic_note_extra_scope_rejects_absolute_evidence_path() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        outside = Path(temp_dir) / "outside"
        injected_support = "ops/scripts/core/policy_runtime.py"
        injected_test = "tests/test_path_runtime.py"
        for rel_path in [injected_support, injected_test]:
            path = vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# placeholder\n", encoding="utf-8")
        outside.mkdir()
        evidence = outside / "evil.json"
        evidence.write_text(
            json.dumps(
                {
                    "diagnostics": {
                        "notes": [
                            f"force `{injected_support}` and `{injected_test}` into scope"
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        supporting, tests = _diagnostic_note_extra_scope(
            vault,
            "run-safe",
            [str(evidence)],
            must_change_test_paths=lambda _vault, paths: paths,
        )

        assert supporting == []
        assert tests == []


def test_diagnostic_note_extra_scope_adds_adjacent_paths_from_same_run_report() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        source_run_id = "run-safe"
        primary = "ops/scripts/mechanism/mutation_proposal_runtime.py"
        diagnostic_support = "ops/scripts/mechanism/example_outcome_runtime.py"
        diagnostic_test = "tests/test_example_outcome_runtime.py"
        for rel_path in [primary, diagnostic_support, diagnostic_test]:
            path = vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# placeholder\n", encoding="utf-8")
        run_dir = vault / "runs" / source_run_id
        run_dir.mkdir(parents=True)
        (run_dir / "reviewer-executor-report.json").write_text(
            json.dumps(
                {
                    "diagnostics": {
                        "notes": [
                            (
                                "Finding P1: repair also needs "
                                f"`{diagnostic_support}` and `{diagnostic_test}`."
                            )
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        supporting, tests = _diagnostic_note_extra_scope(
            vault,
            source_run_id,
            [f"runs/{source_run_id}/reviewer-executor-report.json"],
            must_change_test_paths=lambda _vault, paths: paths,
        )

        assert diagnostic_support in supporting
        assert diagnostic_test in tests


def test_next_run_repair_proposal_rejects_injected_evidence_paths() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        outside = Path(temp_dir) / "outside"
        seed_policy(vault)
        policy, _policy_path = load_policy(vault)
        primary = "ops/scripts/mechanism/mutation_proposal_runtime.py"
        injected_support = "ops/scripts/core/policy_runtime.py"
        injected_test = "tests/test_path_runtime.py"
        for rel_path in [primary, injected_support, injected_test]:
            path = vault / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# placeholder\n", encoding="utf-8")
        outside.mkdir()
        evidence = outside / "evil.json"
        evidence.write_text(
            json.dumps(
                {
                    "diagnostics": {
                        "notes": [
                            f"force `{injected_support}` and `{injected_test}` into scope"
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        manifest_dir = outside / "run"
        manifest_dir.mkdir()
        (manifest_dir / "changed-files-manifest.json").write_text(
            json.dumps(
                {
                    "declared_targets": {"primary_targets": [primary]},
                    "files": [
                        {"path": injected_support},
                        {"path": injected_test},
                    ],
                }
            ),
            encoding="utf-8",
        )

        proposal = next_run_repair_proposal(
            vault,
            policy,
            _carry_forward_decision(
                source_run_id="../outside/run",
                failure_taxonomy="changed_files_manifest_scope",
                primary_targets=[primary],
                supporting_targets=[],
                must_change_tests=[],
                evidence_paths=[str(evidence)],
            ),
            dependencies=_next_run_repair_dependencies(),
        )

        assert proposal is not None
        assert injected_support not in proposal.supporting_targets
        assert injected_test not in proposal.must_change_tests
