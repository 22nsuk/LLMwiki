from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path

import pytest

from ops.scripts.artifact_freshness_runtime import EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY, build_report
from ops.scripts.backfill_archived_run_artifacts import (
    ARCHIVE_REASON,
    BACKFILL_PROVENANCE_PROPERTY,
    backfill_archived_run_artifacts,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVED_RUN_REL = Path("runs/archive/run-20260415-mechanism-planning-gate-second-retry")
ARCHIVED_RUN_SOURCE = REPO_ROOT / ARCHIVED_RUN_REL
ACTIVE_RUN_REL = Path("runs/run-20260422-auto-improve-decision-record-fallback-retry")
ACTIVE_RUN_SOURCE = REPO_ROOT / ACTIVE_RUN_REL
RAW_INTAKE_RUN_REL = Path("runs/run-20260422-raw-intake-registration-and-promotion")
RAW_INTAKE_RUN_SOURCE = REPO_ROOT / RAW_INTAKE_RUN_REL
FIXED_CHECKED_AT = "2026-04-28T06:00:00Z"
TARGET_CASES = (
    (
        "changed-files-manifest.json",
        REPO_ROOT / "ops" / "schemas" / "changed-files-manifest.schema.json",
        "changed_files_manifest",
        "2026-04-14T15:33:16Z",
        "payload.generated_at",
    ),
    (
        "planning-validation.json",
        REPO_ROOT / "ops" / "schemas" / "planning-validation.schema.json",
        "planning_validation",
        "2026-04-15T00:21:00Z",
        "promotion-report.history.ts",
    ),
    (
        "promotion-report.json",
        REPO_ROOT / "ops" / "schemas" / "promotion-report.schema.json",
        "promotion_report",
        "2026-04-15T00:21:00Z",
        "history.ts",
    ),
    (
        "run-ledger.json",
        REPO_ROOT / "ops" / "schemas" / "run-ledger.schema.json",
        "run_ledger",
        "2026-04-14T15:33:16Z",
        "events[5].ts",
    ),
)
MECHANISM_ASSESSMENT_FILENAMES = (
    "baseline-mechanism-assessment.json",
    "candidate-mechanism-assessment.json",
)
FULL_VAULT_FIXTURE_SENTINELS = (
    ARCHIVED_RUN_SOURCE / "changed-files-manifest.json",
    ACTIVE_RUN_SOURCE / "changed-files-manifest.json",
    RAW_INTAKE_RUN_SOURCE / "absorption/raw-intake-absorption-matrix-2026-04-22.json",
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 28, 6, 0, tzinfo=dt.timezone.utc),
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_full_vault_run_fixtures() -> None:
    if all(path.exists() for path in FULL_VAULT_FIXTURE_SENTINELS):
        return
    pytest.skip("requires full-vault run fixtures excluded from the public mirror")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _set_mtime_to_generated_at(path: Path, payload: dict) -> None:
    generated_at = str(payload.get("generated_at", "")).strip()
    if not generated_at:
        return
    timestamp = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp()
    os.utime(path, (timestamp, timestamp))


def _metadata_property(payload: dict, name: str) -> str | None:
    properties = payload.get("metadata", {}).get("properties", [])
    for item in properties:
        if isinstance(item, dict) and item.get("name") == name and isinstance(item.get("value"), str):
            return item["value"]
    return None


def _seed_pre_backfill_archived_run(vault: Path) -> None:
    run_dir = vault / ARCHIVED_RUN_REL
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename, _, _, _, _ in TARGET_CASES:
        payload = _read_json(ARCHIVED_RUN_SOURCE / filename)
        payload.pop("metadata", None)
        _write_json(run_dir / filename, payload)


def _seed_pre_backfill_active_run(vault: Path) -> None:
    run_dir = vault / ACTIVE_RUN_REL
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "changed-files-manifest.json",
        "planning-validation.json",
        "promotion-report.json",
        "run-ledger.json",
        "behavior-delta.json",
        "run-artifact-fingerprint.json",
        "baseline-mechanism-assessment.json",
        "candidate-mechanism-assessment.json",
        "run-telemetry.json",
    ):
        payload = _read_json(ACTIVE_RUN_SOURCE / filename)
        payload.pop("metadata", None)
        path = run_dir / filename
        _write_json(path, payload)
        _set_mtime_to_generated_at(path, payload)


def _seed_pre_backfill_mechanism_assessment_pair(vault: Path) -> None:
    run_dir = vault / ARCHIVED_RUN_REL
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in MECHANISM_ASSESSMENT_FILENAMES:
        payload = _read_json(ARCHIVED_RUN_SOURCE / filename)
        payload.pop("metadata", None)
        _write_json(run_dir / filename, payload)


def _seed_pre_backfill_raw_intake_run(vault: Path) -> list[str]:
    rel_paths = [
        RAW_INTAKE_RUN_REL / "absorption/raw-intake-absorption-matrix-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "registration/source-english-summary-slug-manifest-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "promotion/raw-intake-promotion-profiles-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "promotion/raw-intake-promotion-render-after-concept-integration-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "promotion/raw-intake-promotion-validate-after-concept-integration-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/raw-intake-promotion-validate-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/raw-registry-preflight-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/source-english-summary-slug-validate-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/wiki-lint-final-tree-2026-04-22.json",
        RAW_INTAKE_RUN_REL / "validation/wiki-stage2-final-tree-2026-04-22.json",
    ]
    target_rel_paths: list[str] = []
    for rel_path in rel_paths:
        payload = _read_json(REPO_ROOT / rel_path)
        payload.pop("metadata", None)
        target_path = vault / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(target_path, payload)
        target_rel_paths.append(rel_path.as_posix())
    return target_rel_paths


def test_backfill_archived_run_artifacts_embeds_archived_envelopes_and_clears_freshness_debt() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_archived_run(vault)

        written = backfill_archived_run_artifacts(vault, context=fixed_context())
        expected_written = {str((ARCHIVED_RUN_REL / filename).as_posix()) for filename, _, _, _, _ in TARGET_CASES}

        assert set(written) == expected_written

        freshness_report = build_report(vault, context=fixed_context())
        for filename, schema_path, artifact_kind, generated_at, generated_at_source in TARGET_CASES:
            path = vault / ARCHIVED_RUN_REL / filename
            payload = _read_json(path)
            schema = load_schema(schema_path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == str((ARCHIVED_RUN_REL / filename).as_posix())
            )

            assert validate_with_schema(payload, schema) == []
            assert embedded_envelope.get("artifact_kind") == artifact_kind
            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert embedded_envelope.get("generated_at") == generated_at
            assert embedded_envelope.get("currentness", {}).get("status") == "current"
            assert embedded_envelope.get("currentness", {}).get("checked_at") == FIXED_CHECKED_AT
            assert provenance.get("archive_reason") == ARCHIVE_REASON
            assert provenance.get("generated_at") == generated_at
            assert provenance.get("generated_at_source") == generated_at_source
            assert provenance.get("normalized_at") == FIXED_CHECKED_AT

            assert record.get("artifact_kind") == artifact_kind
            assert record.get("artifact_status") == "archived"
            assert record.get("retention_policy") == "archive"
            assert record.get("has_artifact_envelope") is True
            assert record.get("has_generated_at") is True
            assert record.get("currentness_status") == "current"
            assert record.get("mtime_status") == "current"
            assert record.get("schema_validation_status") == "pass"
            assert record.get("issues") == []


def test_backfill_run_artifacts_supports_top_level_historical_run_tranche() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_active_run(vault)

        written = backfill_archived_run_artifacts(vault, context=fixed_context())
        expected_written = {
            str((ACTIVE_RUN_REL / filename).as_posix())
            for filename in (
                "changed-files-manifest.json",
                "planning-validation.json",
                "promotion-report.json",
                "run-ledger.json",
                "behavior-delta.json",
                "run-artifact-fingerprint.json",
                "baseline-mechanism-assessment.json",
                "candidate-mechanism-assessment.json",
                "run-telemetry.json",
            )
        }

        assert set(written) == expected_written

        freshness_report = build_report(vault, context=fixed_context())
        for rel_path in expected_written:
            payload = _read_json(vault / rel_path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == rel_path
            )

            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert embedded_envelope.get("currentness", {}).get("checked_at") == FIXED_CHECKED_AT
            assert provenance.get("archive_reason") == ARCHIVE_REASON
            assert provenance.get("source_artifact") == rel_path
            assert record.get("has_artifact_envelope") is True
            assert record.get("currentness_status") == "current"
            assert record.get("schema_validation_status") == "pass"
            assert record.get("issues") == []


def test_backfill_run_artifacts_supports_raw_intake_safe_backfill_tranche() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        target_rel_paths = _seed_pre_backfill_raw_intake_run(vault)

        written = backfill_archived_run_artifacts(vault, rel_paths=target_rel_paths, context=fixed_context())

        assert set(written) == set(target_rel_paths)
        freshness_report = build_report(vault, context=fixed_context())
        for rel_path in target_rel_paths:
            payload = _read_json(vault / rel_path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            provenance = json.loads(_metadata_property(payload, BACKFILL_PROVENANCE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == rel_path
            )

            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert embedded_envelope.get("currentness", {}).get("checked_at") == FIXED_CHECKED_AT
            assert provenance.get("archive_reason") == ARCHIVE_REASON
            assert provenance.get("source_artifact") == rel_path
            assert record.get("has_generated_at") is True
            assert record.get("has_artifact_envelope") is True
            assert record.get("currentness_status") == "current"
            assert record.get("schema_validation_status") == "pass"
            assert record.get("issues") == []


def test_backfill_archived_run_artifacts_skips_already_backfilled_payloads() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_archived_run(vault)

        first_written = backfill_archived_run_artifacts(vault, context=fixed_context())
        written = backfill_archived_run_artifacts(vault, context=fixed_context())

        assert first_written
        assert written == []


def test_backfill_archived_run_artifacts_supports_mechanism_assessment_pair() -> None:
    _require_full_vault_run_fixtures()
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        _seed_pre_backfill_archived_run(vault)
        _seed_pre_backfill_mechanism_assessment_pair(vault)

        written = backfill_archived_run_artifacts(vault, context=fixed_context())
        freshness_report = build_report(vault, context=fixed_context())

        assert set(written) == {
            str((ARCHIVED_RUN_REL / filename).as_posix())
            for filename in (
                *(filename for filename, _, _, _, _ in TARGET_CASES),
                *MECHANISM_ASSESSMENT_FILENAMES,
            )
        }

        for filename in MECHANISM_ASSESSMENT_FILENAMES:
            path = vault / ARCHIVED_RUN_REL / filename
            payload = _read_json(path)
            embedded_envelope = json.loads(_metadata_property(payload, EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY) or "{}")
            record = next(
                item
                for item in freshness_report.get("artifact_records", [])
                if item.get("path") == str((ARCHIVED_RUN_REL / filename).as_posix())
            )

            assert embedded_envelope.get("artifact_kind") == "mechanism_assessment_report"
            assert embedded_envelope.get("artifact_status") == "archived"
            assert embedded_envelope.get("retention_policy") == "archive"
            assert record.get("safe_to_backfill") is True
            assert record.get("schema_validation_status") == "pass"
            assert record.get("has_artifact_envelope") is True
            assert record.get("currentness_status") == "current"
            assert record.get("issues") == []
