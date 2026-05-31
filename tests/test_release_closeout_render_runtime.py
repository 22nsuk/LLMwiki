from __future__ import annotations

from types import SimpleNamespace

from ops.scripts.release.release_closeout_render_runtime import (
    closeout_snapshot_phase,
    closeout_status_decision,
    closeout_summary_payload,
    status_semantics,
)


def _readiness(
    *,
    checked_in_release_ready: bool = True,
    clean_release_ready: bool = True,
    machine_release_allowed: bool = True,
    release_readiness_state: str = "clean_pass",
) -> SimpleNamespace:
    return SimpleNamespace(
        checked_in_release_ready=checked_in_release_ready,
        live_rerun_release_ready=clean_release_ready,
        conditional_release_ready=False,
        clean_release_ready=clean_release_ready,
        release_readiness_state=release_readiness_state,
        machine_release_allowed=machine_release_allowed,
        operator_release_allowed=checked_in_release_ready,
        requires_accepted_risk_review=False,
    )


def test_closeout_status_decision_preserves_unsealed_summary_semantics() -> None:
    decision = closeout_status_decision(_readiness())

    assert decision.status == "pass"
    assert decision.release_authority_status == "clean_pass"
    assert decision.semantic_release_status == "clean_pass"
    assert decision.sealed_release_status == "unsealed_distribution_not_provided"
    assert (
        decision.pre_distribution_package_binding_status
        == "not_materialized_by_summary"
    )
    assert (
        decision.status_v2["status_axes"]["sealed_release_status"]
        == "unsealed_distribution_not_provided"
    )


def test_status_semantics_names_legacy_top_level_status() -> None:
    semantics = status_semantics()

    assert semantics["top_level_status_meaning"] == "legacy_checked_in_release_ready_claim"
    assert "status_v2" in semantics["summary"]


def test_closeout_snapshot_phase_distinguishes_prefinalization_mismatch() -> None:
    assert (
        closeout_snapshot_phase({"status": "mismatch"}, _readiness())
        == "pre_finalization"
    )
    assert (
        closeout_snapshot_phase({"status": "match"}, _readiness())
        == "sealed_snapshot"
    )
    assert (
        closeout_snapshot_phase(
            {"status": "match"},
            _readiness(
                checked_in_release_ready=False,
                clean_release_ready=False,
                machine_release_allowed=False,
                release_readiness_state="blocked",
            ),
        )
        == "post_finalization"
    )


def test_closeout_summary_payload_counts_risk_and_gate_axes() -> None:
    inputs = SimpleNamespace(
        collection=SimpleNamespace(
            components=[
                {"ready": True},
                {"ready": False},
            ]
        ),
        risk_state=SimpleNamespace(
            blockers=[{"code": "blocker"}],
            source_clean_blockers=[{"code": "blocker"}],
            accepted_risks=[
                {"source": "s", "code": "risk_a"},
                {"source": "s", "code": "risk_a"},
            ],
            accepted_risk_scope_counts={
                "release_blocking_family_count": 0,
                "conditional_operator_review_family_count": 1,
                "learning_claim_blocking_family_count": 0,
                "advisory_lifecycle_family_count": 1,
                "advisory_only_family_count": 1,
            },
        ),
        gates=SimpleNamespace(
            source_tree_coherence={"status": "pass"},
            artifact_freshness_gate={
                "status": "attention",
                "schema_invalid_artifact_count": 2,
            },
            release_smoke_boundedness_gate={"status": "pass"},
            live_make_check={"status": "fail"},
            test_failure_lanes=[
                {"status": "fail"},
                {"status": "not_run"},
                {"status": "pass"},
            ],
        ),
    )

    summary = closeout_summary_payload(inputs)

    assert summary["component_count"] == 2
    assert summary["ready_component_count"] == 1
    assert summary["blocker_count"] == 1
    assert summary["accepted_risk_instance_count"] == 2
    assert summary["accepted_risk_family_count"] == 1
    assert summary["artifact_freshness_schema_invalid_artifact_count"] == 2
    assert summary["test_failure_lane_fail_count"] == 1
    assert summary["test_failure_lane_not_run_count"] == 1
