from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from ops.scripts.executor_noop_runtime import (
    EXECUTOR_NOOP_MUTATION_FAILURE_MARKER,
    executor_noop_mutation_failure_message,
)

from ops.scripts.mechanism.auto_improve_next_run_decision_runtime import (
    CARRY_FORWARD_DECISION,
    OPEN_DECISION_STATUS,
)
from ops.scripts.mechanism.failure_taxonomy_runtime import (
    GENERATED_EVIDENCE_SETTLE_REQUIRED,
)
from ops.scripts.mechanism.next_run_repair_queue_runtime import (
    open_carry_forward_decisions,
)
from tests.test_mechanism_assess import seed_policy


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


def test_open_carry_forward_decisions_keeps_standard_structural_non_regression() -> None:
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
