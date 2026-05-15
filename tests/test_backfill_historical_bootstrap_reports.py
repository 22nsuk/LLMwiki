from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.backfill_historical_bootstrap_reports import (
    ARCHIVE_REASON,
    backfill_historical_bootstrap_reports,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 28, 6, 0, tzinfo=dt.timezone.utc),
    )


class HistoricalBootstrapBackfillTests(unittest.TestCase):
    def test_backfill_normalizes_bootstrap_reports_into_archived_schema_backed_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "schemas" / "bundle-manifest.schema.json").write_text(
                (REPO_ROOT / "ops" / "schemas" / "bundle-manifest.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "eval-initial-2026-04-12.json").write_text(
                json.dumps(
                    {
                        "vault": "/mnt/data/build_llm_wiki_package/LLM Wiki vNext",
                        "generated_at": "2026-04-12T08:59:35.099781Z",
                        "max_score": 2,
                        "total_score": 2,
                        "pages": [
                            {
                                "page": "/mnt/data/build_llm_wiki_package/LLM Wiki vNext/wiki/source--sample.md",
                                "score": 2,
                                "max_score": 2,
                                "results": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "lint-initial-2026-04-12.json").write_text(
                json.dumps(
                    {
                        "vault": "/mnt/data/build_llm_wiki_package/LLM Wiki vNext",
                        "generated_at": "2026-04-12T08:59:33.179351Z",
                        "status": "pass",
                        "errors": [],
                        "warnings": [],
                        "stats": {
                            "page_count": 1,
                            "error_count": 0,
                            "warning_count": 0,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (vault / "ops" / "reports" / "manifest-2026-04-12.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-12T08:59:37.088426Z",
                        "files": [
                            {
                                "path": "README.md",
                                "sha256": "abc",
                                "size_bytes": 1,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            written = backfill_historical_bootstrap_reports(vault, context=fixed_context())

            self.assertEqual(
                written,
                [
                    "ops/reports/eval-initial-2026-04-12.json",
                    "ops/reports/lint-initial-2026-04-12.json",
                    "ops/reports/manifest-2026-04-12.json",
                ],
            )

            eval_payload = json.loads(
                (vault / "ops" / "reports" / "eval-initial-2026-04-12.json").read_text(encoding="utf-8")
            )
            lint_payload = json.loads(
                (vault / "ops" / "reports" / "lint-initial-2026-04-12.json").read_text(encoding="utf-8")
            )
            manifest_payload = json.loads(
                (vault / "ops" / "reports" / "manifest-2026-04-12.json").read_text(encoding="utf-8")
            )

            eval_schema = load_schema(vault / "ops" / "schemas" / "eval-report.schema.json")
            lint_schema = load_schema(vault / "ops" / "schemas" / "lint-report.schema.json")
            manifest_schema = load_schema(vault / "ops" / "schemas" / "bundle-manifest.schema.json")

            self.assertEqual(validate_with_schema(eval_payload, eval_schema), [])
            self.assertEqual(validate_with_schema(lint_payload, lint_schema), [])
            self.assertEqual(validate_with_schema(manifest_payload, manifest_schema), [])

            for payload in (eval_payload, lint_payload, manifest_payload):
                self.assertEqual(payload.get("artifact_status"), "archived")
                self.assertEqual(payload.get("retention_policy"), "archive")
                self.assertEqual(payload.get("currentness", {}).get("status"), "current")
                self.assertEqual(payload.get("currentness", {}).get("checked_at"), "2026-04-28T06:00:00Z")
                self.assertEqual(payload.get("historical_bootstrap", {}).get("archive_reason"), ARCHIVE_REASON)

            self.assertEqual(eval_payload.get("vault"), ".")
            self.assertEqual(eval_payload.get("generated_at"), "2026-04-12T08:59:35Z")
            self.assertEqual(eval_payload.get("status"), "pass")
            self.assertEqual(eval_payload.get("policy"), {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 0})
            self.assertEqual(eval_payload.get("pages", [])[0].get("page"), "wiki/source--sample.md")
            self.assertNotIn("/mnt/data/", eval_payload.get("pages", [])[0].get("page", ""))

            self.assertEqual(lint_payload.get("vault"), ".")
            self.assertEqual(lint_payload.get("generated_at"), "2026-04-12T08:59:33Z")
            self.assertEqual(lint_payload.get("policy"), {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 0})
            self.assertEqual(lint_payload.get("review_candidates"), [])
            self.assertEqual(lint_payload.get("stats", {}).get("review_candidate_count"), 0)

            self.assertEqual(manifest_payload.get("generated_at"), "2026-04-12T08:59:37Z")
            self.assertEqual(manifest_payload.get("artifact_kind"), "bundle_manifest")
