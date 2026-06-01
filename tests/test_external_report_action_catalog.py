from __future__ import annotations

from ops.scripts.release.external_report_action_catalog import (
    ACTION_CATALOG,
    ALL_EVIDENCE_OR_PLANNED_ACTION_IDS,
    IMPLEMENTED_ARTIFACT_ACTIONS,
    ROADMAP_SOURCE_ONLY_ACTION_IDS,
    SOURCE_REVISION_RELEASE_AUTHORITY_REPORTS,
    SPRINT_PRIORITIES,
)


def test_action_catalog_has_unique_ids_and_required_fields() -> None:
    action_ids = [str(action.get("action_id", "")) for action in ACTION_CATALOG]

    assert action_ids
    assert len(action_ids) == len(set(action_ids))
    for action in ACTION_CATALOG:
        assert str(action.get("action_id", "")).strip()
        assert str(action.get("priority", "")).strip()
        assert str(action.get("theme", "")).strip()
        assert isinstance(action.get("patterns"), list)
        assert isinstance(action.get("evidence_paths"), list)
        assert str(action.get("recommended_target", "")).strip()


def test_catalog_policy_sets_reference_catalog_actions_or_known_artifacts() -> None:
    action_ids = {str(action["action_id"]) for action in ACTION_CATALOG}

    assert action_ids >= ROADMAP_SOURCE_ONLY_ACTION_IDS
    assert action_ids >= ALL_EVIDENCE_OR_PLANNED_ACTION_IDS
    assert set(IMPLEMENTED_ARTIFACT_ACTIONS) <= action_ids
    assert set(SPRINT_PRIORITIES) <= action_ids
    assert all(path.startswith("ops/reports/") for path in SOURCE_REVISION_RELEASE_AUTHORITY_REPORTS)
