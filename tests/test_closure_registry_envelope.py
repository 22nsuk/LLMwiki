from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.closure_registry_envelope import refresh_registries
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import seed_minimal_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFECT_SCHEMA = REPO_ROOT / "ops" / "schemas" / "defect-escape-closures.schema.json"
REWORK_SCHEMA = REPO_ROOT / "ops" / "schemas" / "rework-closures.schema.json"
ENVELOPE_SCHEMA = REPO_ROOT / "ops" / "schemas" / "artifact-envelope.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 5, 8, 1, 0, tzinfo=dt.timezone.utc),
    )


class ClosureRegistryEnvelopeTests(unittest.TestCase):
    def test_refresh_registries_backfills_envelope_without_changing_closures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            reports_dir = vault / "ops" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            defect_closures = [
                {
                    "target": "ops/scripts/example.py",
                    "promoted_run_id": "run-promoted",
                    "escaped_run_id": "run-escaped",
                    "closure_status": "superseded",
                    "closure_reason": "newer run superseded the escaped decision",
                    "superseding_run_id": "run-new",
                    "closed_at": "2026-05-08T00:00:00Z",
                    "evidence_refs": ["runs/run-new/promotion-report.json"],
                }
            ]
            rework_closures = [
                {
                    "rework_key": "target:ops/scripts/example.py",
                    "primary_targets": ["ops/scripts/example.py"],
                    "closure_status": "superseded",
                    "closure_reason": "later run closed the repeated rework",
                    "superseding_run_id": "run-new",
                    "closed_at": "2026-05-08T00:00:00Z",
                    "closed_run_ids": ["run-old", "run-new"],
                    "evidence_refs": ["runs/run-new/run-telemetry.json"],
                },
                {
                    "rework_key": "open:ops/scripts/other.py",
                    "primary_targets": ["ops/scripts/other.py"],
                    "closure_status": "open",
                    "closure_reason": "operator review still pending",
                    "superseding_run_id": "",
                    "closed_at": "",
                    "closed_run_ids": ["run-open"],
                    "evidence_refs": ["ops/reports/outcome-metrics.json"],
                },
            ]
            (reports_dir / "defect-escape-closures.json").write_text(
                json.dumps({"closures": defect_closures}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (reports_dir / "rework-closures.json").write_text(
                json.dumps({"closures": rework_closures}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            written = refresh_registries(vault, context=fixed_context())
            defect = json.loads((reports_dir / "defect-escape-closures.json").read_text(encoding="utf-8"))
            rework = json.loads((reports_dir / "rework-closures.json").read_text(encoding="utf-8"))

            self.assertEqual({path.name for path in written}, {"defect-escape-closures.json", "rework-closures.json"})
            self.assertEqual(defect["closures"], defect_closures)
            self.assertEqual(rework["closures"], rework_closures)
            self.assertEqual(defect["producer"], "ops.scripts.closure_registry_envelope")
            self.assertEqual(rework["producer"], "ops.scripts.closure_registry_envelope")
            self.assertEqual(defect["generated_at"], "2026-05-08T01:00:00Z")
            self.assertEqual(defect["currentness"], {"status": "current", "checked_at": "2026-05-08T01:00:00Z"})
            self.assertEqual(defect["summary"], {"closure_count": 1})
            self.assertEqual(rework["summary"], {"closure_count": 2, "closed_rework_count": 2})
            self.assertEqual(validate_with_schema(defect, load_schema(DEFECT_SCHEMA)), [])
            self.assertEqual(validate_with_schema(rework, load_schema(REWORK_SCHEMA)), [])
            self.assertEqual(validate_with_schema(defect, load_schema(ENVELOPE_SCHEMA)), [])
            self.assertEqual(validate_with_schema(rework, load_schema(ENVELOPE_SCHEMA)), [])


if __name__ == "__main__":
    unittest.main()
