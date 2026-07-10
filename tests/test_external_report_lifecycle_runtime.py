from __future__ import annotations

import json
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given

from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.release.external_report_lifecycle_runtime import (
    ACTION_LIFECYCLE_CURRENTLY_VALID,
    ACTION_LIFECYCLE_HISTORICALLY_TRUE,
    ACTION_LIFECYCLE_RESOLVED,
    ACTION_LIFECYCLE_SUPERSEDED,
    ACTION_LIFECYCLES,
    canonical_artifact_freshness_state,
    classify_external_report_action_lifecycle,
    external_report_action_lifecycle_record,
    external_report_action_lifecycle_summary,
)


def _artifact_freshness_payload(
    vault: Path,
    *,
    artifact_count: int,
    stale_artifact_count: int,
    operational_attention_artifact_count: int,
    source_revision: str | None = None,
    source_tree_fingerprint: str | None = None,
) -> dict:
    return {
        "artifact_kind": "artifact_freshness_report",
        "artifact_status": "current",
        "currentness": {"status": "current"},
        "source_revision": source_revision or resolve_source_revision(vault).revision,
        "source_tree_fingerprint": (
            source_tree_fingerprint or release_source_tree_fingerprint(vault)
        ),
        "status": "pass",
        "summary": {
            "artifact_count": artifact_count,
            "stale_artifact_count": stale_artifact_count,
            "operational_attention_artifact_count": operational_attention_artifact_count,
        },
    }


def _artifact_freshness_state(
    *,
    artifact_count: int,
    stale_artifact_count: int,
    operational_attention_artifact_count: int,
) -> dict:
    return {
        "evidence_status": "current",
        "evidence_path": "ops/reports/artifact-freshness-report.json",
        "stale_artifact_count": stale_artifact_count,
        "total_artifact_count": artifact_count,
        "operational_attention_artifact_count": operational_attention_artifact_count,
        "summary": f"{stale_artifact_count} stale / {artifact_count} total; "
        f"{operational_attention_artifact_count} operational attention",
        "reason_id": "artifact_freshness_report_current",
        "owner_target": "artifact-freshness",
    }


def _unavailable_artifact_freshness_state(
    *, evidence_status: str, reason_id: str
) -> dict:
    return {
        "evidence_status": evidence_status,
        "evidence_path": "ops/reports/artifact-freshness-report.json",
        "stale_artifact_count": None,
        "total_artifact_count": None,
        "operational_attention_artifact_count": None,
        "summary": (
            f"artifact freshness evidence {evidence_status}; "
            "current canonical artifact freshness state unavailable"
        ),
        "reason_id": reason_id,
        "owner_target": "artifact-freshness",
    }


@given(
    lifecycle_hint=st.sampled_from(
        [
            "resolved",
            "historical_46_stale",
            "superseded",
            "currently_valid_generic",
        ]
    )
)
def test_property_10_external_report_lifecycle_partition_and_active_set_derivation(
    lifecycle_hint: str,
) -> None:
    """Feature: release-evidence-sync, Property 10: external report lifecycle partition and active-set derivation"""
    claim_text_by_hint = {
        "resolved": "implemented runtime evidence is now present",
        "historical_46_stale": "top-level canonical report 46/46 stale",
        "superseded": "superseded by the 2026-05-29 revalidation report",
        "currently_valid_generic": "current active external report item needs operator action",
    }
    status_by_hint = {
        "resolved": "implemented",
        "historical_46_stale": "planned",
        "superseded": "planned",
        "currently_valid_generic": "requires_release_run_verification",
    }
    item = {
        "action_id": lifecycle_hint,
        "theme": "external report lifecycle",
        "current_status": status_by_hint[lifecycle_hint],
        "claim_text": claim_text_by_hint[lifecycle_hint],
    }

    record = external_report_action_lifecycle_record(item)
    summary = external_report_action_lifecycle_summary([{**item, **record}])

    assert record["lifecycle"] in ACTION_LIFECYCLES
    assert record["is_active"] is (
        record["lifecycle"] == ACTION_LIFECYCLE_CURRENTLY_VALID
    )
    assert set(summary["active_action_ids"]).isdisjoint(summary["archived_action_ids"])
    if lifecycle_hint == "historical_46_stale":
        assert record["lifecycle"] == ACTION_LIFECYCLE_HISTORICALLY_TRUE
        assert record["is_active"] is False
    elif lifecycle_hint == "superseded":
        assert record["lifecycle"] == ACTION_LIFECYCLE_SUPERSEDED
        assert record["is_active"] is False
    elif lifecycle_hint == "resolved":
        assert record["lifecycle"] == ACTION_LIFECYCLE_RESOLVED
        assert record["is_active"] is False
    else:
        assert record["lifecycle"] == ACTION_LIFECYCLE_CURRENTLY_VALID
        assert record["is_active"] is True


def test_missing_artifact_freshness_report_returns_unavailable_state() -> None:
    state = canonical_artifact_freshness_state()

    assert state == _unavailable_artifact_freshness_state(
        evidence_status="missing",
        reason_id="artifact_freshness_report_not_provided",
    )


def test_current_external_report_state_uses_artifact_freshness_summary(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "ops" / "reports" / "artifact-freshness-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            _artifact_freshness_payload(
                tmp_path,
                artifact_count=123,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
            )
        ),
        encoding="utf-8",
    )

    state = canonical_artifact_freshness_state(tmp_path)
    summary = external_report_action_lifecycle_summary(
        [],
        canonical_artifact_freshness_state_record=state,
    )

    assert state == _artifact_freshness_state(
        artifact_count=123,
        stale_artifact_count=0,
        operational_attention_artifact_count=0,
    )
    assert summary["canonical_artifact_freshness_state"] == state


def test_invalid_artifact_freshness_json_returns_unavailable_state(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "ops" / "reports" / "artifact-freshness-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("{", encoding="utf-8")

    state = canonical_artifact_freshness_state(tmp_path)

    assert state == _unavailable_artifact_freshness_state(
        evidence_status="invalid",
        reason_id="artifact_freshness_report_invalid",
    )


def test_invalid_artifact_freshness_summary_returns_unavailable_state(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "ops" / "reports" / "artifact-freshness-report.json"
    report_path.parent.mkdir(parents=True)
    payload = _artifact_freshness_payload(
        tmp_path,
        artifact_count=123,
        stale_artifact_count=0,
        operational_attention_artifact_count=0,
    )
    payload["summary"].pop("artifact_count")
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    state = canonical_artifact_freshness_state(tmp_path)

    assert state == _unavailable_artifact_freshness_state(
        evidence_status="invalid",
        reason_id="artifact_freshness_summary_artifact_count_invalid",
    )


def test_artifact_freshness_source_identity_mismatch_returns_unavailable_state(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "ops" / "reports" / "artifact-freshness-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            _artifact_freshness_payload(
                tmp_path,
                artifact_count=123,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
                source_revision=resolve_source_revision(tmp_path).revision,
                source_tree_fingerprint="previous-fingerprint",
            )
        ),
        encoding="utf-8",
    )

    state = canonical_artifact_freshness_state(tmp_path)

    assert state == _unavailable_artifact_freshness_state(
        evidence_status="source_identity_mismatch",
        reason_id="artifact_freshness_source_tree_fingerprint_mismatch",
    )


def test_artifact_freshness_revision_alias_is_current_when_source_tree_matches(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "ops" / "reports" / "artifact-freshness-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            _artifact_freshness_payload(
                tmp_path,
                artifact_count=123,
                stale_artifact_count=0,
                operational_attention_artifact_count=0,
                source_revision="previous-revision-same-tree",
                source_tree_fingerprint=release_source_tree_fingerprint(tmp_path),
            )
        ),
        encoding="utf-8",
    )

    state = canonical_artifact_freshness_state(tmp_path)

    assert state == _artifact_freshness_state(
        artifact_count=123,
        stale_artifact_count=0,
        operational_attention_artifact_count=0,
    )


def test_46_of_46_stale_claim_is_historical_not_current() -> None:
    lifecycle = classify_external_report_action_lifecycle(
        {
            "current_status": "planned",
            "claim_text": "The previous report said 46/46 top-level canonical reports were stale.",
        }
    )

    assert lifecycle == ACTION_LIFECYCLE_HISTORICALLY_TRUE
