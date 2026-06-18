from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.runtime_context import RuntimeContext

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"
LIVE_POLICY_VERSION = load_policy(REPO_ROOT)[0]["version"]
SCHEMA_NAMES = (
    "wiki-maintainer-policy.schema.json",
    "mechanism-review-candidates.schema.json",
    "mutation-proposals.schema.json",
    "structural-complexity-budget-report.schema.json",
)


def seed_vault(vault: Path) -> None:
    (vault / "ops" / "policies").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
    (vault / "system").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
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
    mutation_proposal_test_stub = (
        "from ops.scripts.mechanism import mutation_proposal_runtime\n\n"
        "def test_placeholder():\n"
        "    assert mutation_proposal_runtime is not None\n"
    )
    for rel_path in (
        "tests/test_promotion_gate.py",
        "tests/test_wiki_lint.py",
        "tests/test_mechanism_assess.py",
        "tests/test_example.py",
        "tests/test_report_generation_smoke.py",
        "tests/test_mechanism_run_validation_runtime.py",
    ):
        (vault / rel_path).write_text(
            "def test_placeholder():\n    assert True\n",
            encoding="utf-8",
        )
    for rel_path in (
        "tests/test_mutation_proposal_build_report.py",
        "tests/test_mutation_proposal_promotion.py",
    ):
        (vault / rel_path).write_text(mutation_proposal_test_stub, encoding="utf-8")
    for rel_path in (
        "ops/scripts/mechanism/mutation_proposal_runtime.py",
        "ops/scripts/mechanism/mechanism_run_validation_runtime.py",
    ):
        (vault / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (vault / rel_path).write_text(
            "def placeholder() -> None:\n    return None\n",
            encoding="utf-8",
        )


FIXED_GENERATED_AT = "2026-04-14T12:00:00Z"


def write_json(path: Path, payload: dict) -> None:
    payload_to_write = copy.deepcopy(payload)
    if "generated_at" in payload_to_write:
        timestamp = FIXED_GENERATED_AT
        payload_to_write["generated_at"] = timestamp
        currentness = payload_to_write.get("currentness")
        if isinstance(currentness, dict):
            currentness["checked_at"] = timestamp
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload_to_write, ensure_ascii=False, indent=2), encoding="utf-8")


def write_json_exact(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def auto_improve_session_envelope(generated_at: str) -> dict:
    return {
        "$schema": "ops/schemas/auto-improve-session.schema.json",
        "generated_at": generated_at,
        "artifact_kind": "auto_improve_session",
        "producer": "tests.test_mutation_proposal",
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {"fixture": "fixture"},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": generated_at,
        },
    }


def shadow_priority_diagnostics(*, attempts_considered: int = 0) -> dict:
    return {
        "status": "disabled",
        "gate_effect": "none",
        "min_attempts_considered": 10,
        "min_target_attempts": 2,
        "shadow_priority_max_delta": 10,
        "attempts_considered": attempts_considered,
        "current_order": [],
        "shadow_order": [],
        "order_changed": False,
        "ordering_deltas": [],
    }


def fixed_context(
    policy: dict,
    iso_timestamp: str = "2026-04-14T12:00:00Z",
) -> RuntimeContext:
    instant = dt.datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return RuntimeContext.from_policy(policy, clock=lambda: instant)


def _mechanism_review_envelope() -> dict:
    return {
        "$schema": "ops/schemas/mechanism-review-candidates.schema.json",
        "vault": ".",
        "generated_at": "2026-04-14T00:00:00Z",
        "artifact_kind": "mechanism_review_candidates_report",
        "producer": "tests.test_mutation_proposal",
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
        "status": "pass",
        "summary": {
            "runs_discovered": 3,
            "runs_considered": 3,
            "runs_excluded": 0,
            "runs_skipped": 0,
            "candidates_emitted": 3,
        },
    }


def _mechanism_review_bootstrap_diagnostics() -> dict:
    return {
        "status": "ready",
        "summary": "comparable mechanism run history is sufficient and candidates were emitted.",
        "recommended_next_step": "review current candidates",
        "trend_candidate_requirements": [
            {
                "candidate_type": "mechanism_branch_growth_without_test_growth_candidate",
                "evaluation_min_runs": 2,
                "full_window_runs": 2,
            },
            {
                "candidate_type": "mechanism_eval_stagnation_candidate",
                "evaluation_min_runs": 2,
                "full_window_runs": 5,
            },
        ],
        "target_groups_under_min_history": [],
    }


def _session_calibration_family(family: str, candidate_count: int) -> dict:
    return {
        "family": family,
        "candidates_with_session_context": 0,
        "candidates_with_rollups": 0,
        "candidates_without_session_context": candidate_count,
        "runs_with_session_context": 0,
        "sessions_considered": 0,
        "sessions_with_rollups": 0,
        "validation_blocked_sessions": 0,
        "review_blocked_sessions": 0,
        "mutation_failed_sessions": 0,
        "validator_dispatch_sessions": 0,
        "reviewer_dispatch_sessions": 0,
        "high_risk_routing_sessions": 0,
        "total_priority_delta": 0,
        "boosted_candidates": 0,
        "lowered_candidates": 0,
        "unchanged_candidates": candidate_count,
    }


def _mechanism_review_session_calibration() -> dict:
    return {
        "enabled": True,
        "status": "no_session_context",
        "candidate_count": 3,
        "candidates_with_session_context": 0,
        "candidates_with_rollups": 0,
        "candidates_without_session_context": 3,
        "runs_with_session_context": 0,
        "sessions_considered": 0,
        "sessions_with_rollups": 0,
        "validation_blocked_sessions": 0,
        "review_blocked_sessions": 0,
        "mutation_failed_sessions": 0,
        "validator_dispatch_sessions": 0,
        "reviewer_dispatch_sessions": 0,
        "high_risk_routing_sessions": 0,
        "total_priority_delta": 0,
        "boosted_candidates": 0,
        "lowered_candidates": 0,
        "unchanged_candidates": 3,
        "by_family": [
            _session_calibration_family("contract_regression_signals", 1),
            _session_calibration_family("self_mod_stability", 2),
        ],
    }


def _mechanism_review_outcome_metrics_calibration() -> dict:
    return {
        "enabled": True,
        "status": "missing_outcome_metrics",
        "mode": "audit_only",
        "gate_effect": "none",
        "source_report": "ops/reports/outcome-metrics.json",
        "recent_window": 20,
        "candidate_count": 3,
        "candidates_with_outcome_context": 0,
        "target_count": 0,
        "thresholds": {
            "high_rework_count": 1,
            "hold_or_discard_moving_average": 0.25,
            "rollback_signal_ratio": 0.2,
            "defect_escape_pair_count": 1,
        },
        "global_signals": {
            "attempt_count": 0,
            "recent_attempt_count": 0,
            "moving_averages": {
                "hold": 0.0,
                "discard": 0.0,
                "rollback_signal": 0.0,
            },
            "rework_count": 0,
            "rollback_signal_count": 0,
            "defect_escape_pair_count": 0,
        },
        "target_signals": [],
        "family_signals": [],
        "high_rework_targets": [],
        "defect_escape_pairs": [],
        "shadow_priority": shadow_priority_diagnostics(),
        "evidence_gaps": [],
        "notes": [
            (
                "audit-only preview: outcome metrics are reported for calibration "
                "review and do not change candidate priority."
            ),
            (
                "priority_delta and gate integration remain disabled until a later "
                "explicit policy step."
            ),
        ],
    }


def _mechanism_review_diagnostics() -> dict:
    return {
        "skipped_runs": [],
        "excluded_runs": [],
        "bootstrap": _mechanism_review_bootstrap_diagnostics(),
        "session_calibration": _mechanism_review_session_calibration(),
        "outcome_metrics_calibration": _mechanism_review_outcome_metrics_calibration(),
        "candidate_blockers": [],
    }


def _mechanism_eval_stagnation_candidate() -> dict:
    return {
        "candidate_id": "mechanism_eval_stagnation_candidate__promotion-gate",
        "candidate_type": "mechanism_eval_stagnation_candidate",
        "family": "contract_regression_signals",
        "tier": "supporting",
        "objective": "detect repeated non-improvement against current contract-eval surfaces",
        "priority": 80,
        "primary_targets": ["ops/scripts/promotion_gate.py"],
        "supporting_targets": ["ops/scripts/promotion_gate_mechanism_runtime.py"],
        "metrics_triggered": ["stage1_same_eval_rate", "repeated_discard_runs"],
        "run_ids": ["run-a", "run-b", "run-c"],
        "signal_run_ids": {
            "repeated_discard_runs": ["run-a", "run-b"],
            "repeated_same_eval_after_promote": ["run-a", "run-b", "run-c"],
        },
        "evidence": {
            "runs_examined": 3,
            "same_eval_runs": 3,
            "discard_runs": 2,
        },
        "rationale": "same eval or discard repeated",
        "suggested_experiments": [
            "try one mechanism-only experiment on ops/scripts/promotion_gate.py"
        ],
    }


def _branch_growth_without_test_growth_candidate() -> dict:
    return {
        "candidate_id": "mechanism_branch_growth_without_test_growth_candidate__wiki-lint",
        "candidate_type": "mechanism_branch_growth_without_test_growth_candidate",
        "family": "self_mod_stability",
        "tier": "core",
        "objective": "iterative self-modification degradation and structural erosion",
        "priority": 70,
        "primary_targets": ["ops/scripts/wiki_lint.py"],
        "supporting_targets": ["ops/scripts/wiki_lint_page_runtime.py"],
        "metrics_triggered": ["branch_growth_without_test_growth", "verbosity_growth"],
        "run_ids": ["run-l1", "run-l2", "run-l3"],
        "evidence": {
            "runs_examined": 3,
            "branch_growth_runs": 3,
            "branch_growth_without_test_growth_runs": 2,
        },
        "rationale": "branch growth repeated without test growth",
        "suggested_experiments": [
            "increase mechanism-specific test coverage for ops/scripts/wiki_lint.py"
        ],
    }


def _high_complexity_low_test_pressure_candidate() -> dict:
    return {
        "candidate_id": "mechanism_high_complexity_low_test_pressure_candidate__mechanism-assess",
        "candidate_type": "mechanism_high_complexity_low_test_pressure_candidate",
        "family": "self_mod_stability",
        "tier": "core",
        "objective": "iterative self-modification degradation and structural erosion",
        "priority": 60,
        "primary_targets": ["ops/scripts/mechanism_assess.py"],
        "supporting_targets": [],
        "metrics_triggered": ["high_complexity_low_test_pressure"],
        "run_ids": ["run-m1"],
        "evidence": {
            "runs_examined": 1,
            "latest_complexity_score": 90,
            "latest_candidate_test_case_count": 2,
        },
        "rationale": "high complexity with low tests",
        "suggested_experiments": [
            "increase mechanism-specific test coverage for ops/scripts/mechanism_assess.py"
        ],
    }


def _mechanism_review_candidates() -> list[dict]:
    return [
        _mechanism_eval_stagnation_candidate(),
        _branch_growth_without_test_growth_candidate(),
        _high_complexity_low_test_pressure_candidate(),
    ]


def mechanism_review_report() -> dict:
    report = _mechanism_review_envelope()
    report["diagnostics"] = _mechanism_review_diagnostics()
    report["candidates"] = _mechanism_review_candidates()
    return report
