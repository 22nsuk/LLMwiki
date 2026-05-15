from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from ops.scripts.wiki_lint import lint
from tests.minimal_vault_runtime import (
    seed_doc_audit_smoke_vault,
    set_summary_count,
    summary_count,
)
from tests.vault_test_runtime import SeededMinimalVaultTestCase

pytestmark = pytest.mark.slow


class DocAuditChecksTest(SeededMinimalVaultTestCase):
    @classmethod
    def seed_vault(cls, vault: Path) -> None:
        seed_doc_audit_smoke_vault(vault)

    def test_lint_wires_doc_audit_warnings(self) -> None:
        with self.fresh_vault() as vault:
            registry_summary = vault / "system" / "system-raw-registry.md"
            current_count = summary_count(registry_summary, "total registered paths")
            set_summary_count(registry_summary, "total registered paths", current_count + 1)
            (vault / "external-reports").mkdir(parents=True, exist_ok=True)
            (vault / "external-reports" / "llm_wiki_review_report.md").write_text(
                "fake",
                encoding="utf-8",
            )
            (vault / "README.md").write_text(
                "See `llm_wiki_review_report.md` for details.\n",
                encoding="utf-8",
            )

            report = lint(vault)
            router_warning = next(
                issue
                for issue in report["warnings"]
                if issue["type"] == "router_summary_count_drift"
                and issue["page"] == "system/system-raw-registry.md"
            )
            external_warning = next(
                issue
                for issue in report["warnings"]
                if issue["type"] == "external_report_reference_mismatch"
                and issue["page"] == "README.md"
            )
            self.assertEqual(router_warning["detail"]["label"], "total registered paths")
            self.assertEqual(external_warning["detail"]["basename"], "llm_wiki_review_report.md")


if __name__ == "__main__":
    unittest.main()
