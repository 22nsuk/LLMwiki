from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.scripts.release.release_status_v2 import (
    decide_legacy_strict_clean_sealed_status,
    decide_sealed_release_status,
    release_status_v2_payload,
    release_status_v2_view,
    release_status_v2_view_with_readiness_fallback,
)


pytestmark = [pytest.mark.public, pytest.mark.release_sealing]

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSUMER_INVENTORY_PATH = (
    REPO_ROOT / "ops" / "policies" / "release-status-v2-consumers.json"
)


def test_status_v2_payload_separates_legacy_authority_and_seal_axes() -> None:
    payload = release_status_v2_payload(
        status="fail",
        release_authority_status="clean_pass",
        semantic_release_status="clean_pass",
        sealed_release_status="unsealed_distribution_not_provided",
        release_authority_vocabulary={
            "authority_reason_ids": [],
            "sealed_reason_ids": [
                "sealed_release_not_clean_pass",
                "distribution_package_not_materialized",
            ],
            "blocker_reason_ids": [
                "sealed_release_not_clean_pass",
                "distribution_package_not_materialized",
            ],
        },
    )

    assert payload["schema_version"] == 2
    assert payload["migration_readiness_status"] == "active"
    assert payload["compatibility_status_value"] == "fail"
    assert payload["status_classification"] == "semantic_clean_unsealed"
    assert payload["status_axes"] == {
        "release_authority_status": "clean_pass",
        "semantic_release_status": "clean_pass",
        "sealed_release_status": "unsealed_distribution_not_provided",
    }
    assert payload["blocker_reason_ids"] == [
        "sealed_release_not_clean_pass",
        "distribution_package_not_materialized",
    ]


def test_status_v2_view_prefers_v2_axes_and_reports_legacy_fallbacks() -> None:
    view = release_status_v2_view(
        {
            "status": "fail",
            "release_authority_status": "blocked",
            "semantic_release_status": "blocked",
            "sealed_release_status": "unsealed_release_blocked",
            "release_authority_vocabulary": {
                "blocker_reason_ids": ["legacy_reason_should_not_win"]
            },
            "status_v2": {
                "schema_version": 2,
                "compatibility_status_value": "pass",
                "status_axes": {
                    "release_authority_status": "clean_pass",
                    "semantic_release_status": "clean_pass",
                    "sealed_release_status": "sealed_clean_pass",
                },
                "blocker_reason_ids": [],
            },
        }
    )

    assert view["status_v2_available"] is True
    assert view["compatibility_status_value"] == "pass"
    assert view["release_authority_status"] == "clean_pass"
    assert view["semantic_release_status"] == "clean_pass"
    assert view["sealed_release_status"] == "sealed_clean_pass"
    assert view["blocker_reason_ids"] == []
    assert view["used_legacy_fallback_fields"] == []


def test_status_v2_view_keeps_legacy_fallback_explicit() -> None:
    view = release_status_v2_view(
        {
            "status": "fail",
            "release_authority_status": "conditional_pass",
            "semantic_release_status": "conditional_pass",
            "sealed_release_status": "sealed_conditional_pass",
        }
    )

    assert view["status_v2_available"] is False
    assert view["compatibility_status_value"] == "fail"
    assert view["release_authority_status"] == "conditional_pass"
    assert view["sealed_release_status"] == "sealed_conditional_pass"
    assert view["used_legacy_fallback_fields"] == [
        "release_authority_status",
        "sealed_release_status",
        "semantic_release_status",
        "status",
    ]


def test_status_v2_view_can_use_readiness_state_as_declared_transition_fallback() -> None:
    view = release_status_v2_view_with_readiness_fallback(
        {
            "status": "pass",
            "release_readiness_state": "conditional_pass",
        }
    )

    assert view["release_authority_status"] == "conditional_pass"
    assert view["semantic_release_status"] == "conditional_pass"
    assert view["sealed_release_status"] == "unknown"
    assert "release_readiness_state" in view["used_legacy_fallback_fields"]


def test_release_status_decisions_are_small_pure_functions() -> None:
    sealed = decide_sealed_release_status(
        batch_integrity_status="pass",
        distribution_unsealed_status="",
        clean_release_ready=True,
        machine_release_allowed=True,
        release_readiness_state="clean_pass",
    )

    assert sealed == "sealed_clean_pass"
    assert (
        decide_legacy_strict_clean_sealed_status(
            all_required_present=True,
            all_required_current=True,
            clean_release_ready=True,
            machine_release_allowed=True,
            sealed_release_status=sealed,
        )
        == "pass"
    )


def test_release_status_v2_consumer_inventory_is_actionable() -> None:
    inventory = json.loads(CONSUMER_INVENTORY_PATH.read_text(encoding="utf-8"))

    assert inventory["status_contract"]["active_status_field"] == "status_v2"
    assert inventory["status_contract"]["legacy_top_level_status_field"] == "status"
    consumers = inventory["consumers"]
    assert consumers
    assert any(
        consumer["migration_status"] == "v2_primary_with_legacy_fallback"
        for consumer in consumers
    )
    for consumer in consumers:
        assert (REPO_ROOT / consumer["path"]).is_file()
        assert consumer["required_fields"]
        if consumer["migration_status"] == "v2_primary_with_legacy_fallback":
            assert consumer["status_v2_helper"] in {
                "release_status_v2_view",
                "release_status_v2_view_with_readiness_fallback",
            }
            assert all(
                field.startswith("status_v2.")
                for field in consumer["required_fields"]
            )
            source = (REPO_ROOT / consumer["path"]).read_text(encoding="utf-8")
            assert "release_status_v2_view" in source


def test_compatibility_status_consumers_are_declared_in_inventory() -> None:
    inventory = json.loads(CONSUMER_INVENTORY_PATH.read_text(encoding="utf-8"))
    inventoried_paths = {consumer["path"] for consumer in inventory["consumers"]}
    consumer_paths = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "ops" / "scripts").rglob("*.py")
        if path.name != "release_status_v2.py"
        and '["compatibility_status_value"]' in path.read_text(encoding="utf-8")
    )

    assert consumer_paths
    assert set(consumer_paths) <= inventoried_paths
