from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest
from ops.scripts.learning_readiness_signoff import (
    SIGNOFF_REPORT_REL_PATH,
    SUPPORTED_BLOCKER_ID,
    LearningReadinessSignoffRequest,
    build_signoff_report,
    write_signoff_report,
)
from ops.scripts.learning_readiness_signoff_refresh import (
    REFRESH_SOURCE_COMMAND,
    build_refreshed_signoff_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import LEARNING_READINESS_SIGNOFF_SCHEMA_PATH
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)

from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.report_contract


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 29, 8, 30, tzinfo=dt.UTC),
    )


class LearningReadinessSignoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        (self.vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builds_and_writes_schema_valid_current_signoff(self) -> None:
        report = build_signoff_report(
            self.vault,
            LearningReadinessSignoffRequest(
                accepted_by="operator@example.test",
                accepted_at="2026-04-29T08:30:00Z",
                expires_at="2026-04-30T08:30:00Z",
                risk_owner="runtime-maintainer",
                revalidation_condition="rerun release evidence closeout before the next release",
                rollback_trigger="learning telemetry regresses or auto-improve queue blocks",
            ),
            context=fixed_context(),
        )

        schema = load_schema_with_vault_override(self.vault, LEARNING_READINESS_SIGNOFF_SCHEMA_PATH)
        self.assertEqual(validate_with_schema(report, schema), [])
        self.assertEqual(report["artifact_kind"], "learning_readiness_signoff")
        self.assertEqual(report["artifact_status"], "current")
        self.assertEqual(report["retention_policy"], "canonical_report")
        self.assertEqual(report["currentness"], {"status": "current", "checked_at": "2026-04-29T08:30:00Z"})
        self.assertEqual(report["linked_blocker_id"], SUPPORTED_BLOCKER_ID)

        destination = write_signoff_report(self.vault, report)
        self.assertEqual(destination, self.vault / SIGNOFF_REPORT_REL_PATH)
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted["accepted_by"], "operator@example.test")
        self.assertEqual(persisted["expires_at"], "2026-04-30T08:30:00Z")

    def test_rejects_unsupported_blocker_id_before_write(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported learning readiness blocker id"):
            build_signoff_report(
                self.vault,
                LearningReadinessSignoffRequest(
                    accepted_by="operator@example.test",
                    expiry_days=1,
                    risk_owner="runtime-maintainer",
                    revalidation_condition="rerun release evidence closeout before the next release",
                    rollback_trigger="learning telemetry regresses or auto-improve queue blocks",
                    linked_blocker_id="other_learning_blocker",
                ),
                context=fixed_context(),
            )

    def test_expiry_days_uses_runtime_context_for_deterministic_timestamps(self) -> None:
        report = build_signoff_report(
            self.vault,
            LearningReadinessSignoffRequest(
                accepted_by="operator@example.test",
                expiry_days=3,
                risk_owner="runtime-maintainer",
                revalidation_condition="rerun release evidence closeout before the next release",
                rollback_trigger="learning telemetry regresses or auto-improve queue blocks",
            ),
            context=fixed_context(),
        )

        self.assertEqual(report["generated_at"], "2026-04-29T08:30:00Z")
        self.assertEqual(report["accepted_at"], "2026-04-29T08:30:00Z")
        self.assertEqual(report["expires_at"], "2026-05-02T08:30:00Z")
        self.assertEqual(report["currentness"]["checked_at"], "2026-04-29T08:30:00Z")

    def test_template_is_schema_valid_for_supported_blocker(self) -> None:
        template = json.loads(
            (REPO_ROOT / "ops" / "templates" / "learning-readiness-signoff.json").read_text(
                encoding="utf-8",
            )
        )
        schema = load_schema_with_vault_override(REPO_ROOT, LEARNING_READINESS_SIGNOFF_SCHEMA_PATH)

        self.assertEqual(validate_with_schema(template, schema), [])
        self.assertEqual(template["linked_blocker_id"], SUPPORTED_BLOCKER_ID)
        self.assertEqual(template["source_revision"], "template")
        self.assertEqual(template["artifact_status"], "template_only")
        self.assertEqual(template["retention_policy"], "template")
        self.assertEqual(template["currentness"]["status"], "unknown")

    def test_refresh_reuses_existing_acceptance_metadata_with_new_currentness(self) -> None:
        original = build_signoff_report(
            self.vault,
            LearningReadinessSignoffRequest(
                accepted_by="operator-requested-via-codex-20260526",
                accepted_at="2026-04-29T08:30:00Z",
                expires_at="2026-05-13T08:30:00Z",
                risk_owner="runtime-maintainer",
                revalidation_condition="rerun release evidence closeout before release",
                rollback_trigger="learning telemetry regresses",
                notes="carry forward accepted-risk review until expiry",
            ),
            context=fixed_context(),
        )
        write_signoff_report(self.vault, original)

        refresh_context = RuntimeContext(
            display_timezone=dt.UTC,
            clock=lambda: dt.datetime(2026, 5, 2, 9, 15, tzinfo=dt.UTC),
        )
        refreshed = build_refreshed_signoff_report(
            self.vault,
            context=refresh_context,
        )

        schema = load_schema_with_vault_override(self.vault, LEARNING_READINESS_SIGNOFF_SCHEMA_PATH)
        self.assertEqual(validate_with_schema(refreshed, schema), [])
        self.assertEqual(refreshed["accepted_by"], original["accepted_by"])
        self.assertEqual(refreshed["accepted_at"], original["accepted_at"])
        self.assertEqual(refreshed["expires_at"], original["expires_at"])
        self.assertEqual(refreshed["risk_owner"], original["risk_owner"])
        self.assertEqual(
            refreshed["revalidation_condition"],
            original["revalidation_condition"],
        )
        self.assertEqual(refreshed["rollback_trigger"], original["rollback_trigger"])
        self.assertEqual(refreshed["notes"], original["notes"])
        self.assertEqual(refreshed["generated_at"], "2026-05-02T09:15:00Z")
        self.assertEqual(
            refreshed["currentness"],
            {"status": "current", "checked_at": "2026-05-02T09:15:00Z"},
        )
        self.assertEqual(refreshed["source_command"], REFRESH_SOURCE_COMMAND)

    def test_refresh_rejects_non_signoff_reuse_payload(self) -> None:
        (self.vault / SIGNOFF_REPORT_REL_PATH).write_text(
            json.dumps({"artifact_kind": "other_artifact"}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "artifact_kind=learning_readiness_signoff"):
            build_refreshed_signoff_report(self.vault)


if __name__ == "__main__":
    unittest.main()
