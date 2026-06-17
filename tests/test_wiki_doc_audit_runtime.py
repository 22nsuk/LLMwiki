from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.scripts.eval.wiki_doc_audit_runtime import (
    documentation_markdown_surfaces,
    external_report_reference_issues,
    router_summary_count_issues,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class WikiDocAuditRuntimeTests(unittest.TestCase):
    def test_router_summary_count_issues_reports_registry_entry_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(
                vault / "system" / "system-raw-registry.md",
                """# System Raw Registry

## Summary
- total registered paths: `2`
""",
            )
            doc_audit_policy = {
                "router_summary_targets": [
                    {
                        "page": "system/system-raw-registry.md",
                        "summary_section": "Summary",
                        "metrics": [
                            {
                                "label": "total registered paths",
                                "source": {"kind": "registry_entry_count"},
                            }
                        ],
                    }
                ]
            }

            issues = router_summary_count_issues(
                vault=vault,
                pages={},
                page_lookup={},
                registry_entries=[{"id": "R-100"}],
                doc_audit_policy=doc_audit_policy,
            )

            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["type"], "router_summary_count_drift")
            self.assertEqual(issues[0]["page"], "system/system-raw-registry.md")
            self.assertEqual(issues[0]["detail"]["label"], "total registered paths")
            self.assertEqual(issues[0]["detail"]["declared"], 2)
            self.assertEqual(issues[0]["detail"]["actual"], 1)

    def test_router_summary_count_issues_respects_policy_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(
                vault / "system" / "system-raw-registry.md",
                """# System Raw Registry

## Summary
- total registered paths: `2`
""",
            )
            doc_audit_policy = {
                "router_summary_targets": [
                    {
                        "page": "system/system-index.md",
                        "summary_section": "Summary",
                        "metrics": [
                            {
                                "label": "total registered paths",
                                "source": {"kind": "registry_entry_count"},
                            }
                        ],
                    }
                ]
            }

            issues = router_summary_count_issues(
                vault=vault,
                pages={},
                page_lookup={},
                registry_entries=[{"id": "R-100"}],
                doc_audit_policy=doc_audit_policy,
            )

            self.assertEqual(issues, [])

    def test_router_summary_count_issues_accepts_precomputed_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(
                vault / "system" / "system-index.md",
                """# System Index

## Summary
- wiki pages: `1`
""",
            )
            doc_audit_policy = {
                "router_summary_targets": [
                    {
                        "page": "system/system-index.md",
                        "summary_section": "Summary",
                        "metrics": [
                            {
                                "label": "wiki pages",
                                "source": {"kind": "page_prefix_count", "prefix": "wiki/"},
                            }
                        ],
                    }
                ]
            }

            issues = router_summary_count_issues(
                vault=vault,
                pages={"concept--fake": Path("/outside/unused.md")},
                page_lookup={},
                registry_entries=[],
                doc_audit_policy=doc_audit_policy,
                relative_paths={"concept--fake": "wiki/concept--fake.md"},
            )

            self.assertEqual(len(issues), 0)

    def test_router_summary_count_issues_falls_back_when_relative_paths_are_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(
                vault / "system" / "system-index.md",
                """# System Index

## Summary
- wiki pages: `2`
""",
            )
            page_a = _write(vault / "wiki" / "concept--a.md", "# A\n")
            page_b = _write(vault / "wiki" / "concept--b.md", "# B\n")
            doc_audit_policy = {
                "router_summary_targets": [
                    {
                        "page": "system/system-index.md",
                        "summary_section": "Summary",
                        "metrics": [
                            {
                                "label": "wiki pages",
                                "source": {"kind": "page_prefix_count", "prefix": "wiki/"},
                            }
                        ],
                    }
                ]
            }

            issues = router_summary_count_issues(
                vault=vault,
                pages={"concept--a": page_a, "concept--b": page_b},
                page_lookup={},
                registry_entries=[],
                doc_audit_policy=doc_audit_policy,
                relative_paths={"concept--a": "wiki/concept--a.md"},
            )

            self.assertEqual(issues, [])

    def test_router_summary_count_issues_supports_heading_and_section_wikilink_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(
                vault / "wiki" / "index.md",
                """# Index

## Summary
- news / market / geopolitics sources: `1`
- query artifacts: `2`

### News / market / geopolitics
- [[source--a]]
- [[source--b]]
- [[source--a]]

## Queries
- [[query--one]]
""",
            )
            doc_audit_policy = {
                "router_summary_targets": [
                    {
                        "page": "wiki/index.md",
                        "summary_section": "Summary",
                        "metrics": [
                            {
                                "label": "news / market / geopolitics sources",
                                "source": {
                                    "kind": "heading_unique_wikilinks",
                                    "heading": "News / market / geopolitics",
                                    "heading_level": 3,
                                },
                            },
                            {
                                "label": "query artifacts",
                                "source": {
                                    "kind": "section_unique_wikilinks",
                                    "section": "Queries",
                                },
                            },
                        ],
                    }
                ]
            }

            issues = router_summary_count_issues(
                vault=vault,
                pages={},
                page_lookup={
                    "source--a": "source--a",
                    "source--b": "source--b",
                    "query--one": "query--one",
                },
                registry_entries=[],
                doc_audit_policy=doc_audit_policy,
            )

            self.assertEqual(len(issues), 2)
            by_label = {issue["detail"]["label"]: issue for issue in issues}
            self.assertEqual(by_label["news / market / geopolitics sources"]["detail"]["actual"], 2)
            self.assertEqual(by_label["query artifacts"]["detail"]["actual"], 1)

    def test_external_report_reference_issues_for_bare_readme_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "external-reports" / "llm_wiki_review_report.pdf", "fake")
            _write(vault / "README.md", "See `llm_wiki_review_report.pdf` for details.\n")

            issues = external_report_reference_issues(vault, pages={})
            warning = next(issue for issue in issues if issue["page"] == "README.md")

            self.assertEqual(warning["type"], "external_report_reference_mismatch")
            self.assertEqual(
                warning["detail"]["context"],
                "documentation_surface_requires_external_reports_path",
            )
            self.assertEqual(warning["detail"]["basename"], "llm_wiki_review_report.pdf")
            self.assertEqual(
                warning["detail"]["expected"],
                "external-reports/llm_wiki_review_report.pdf",
            )

    def test_external_report_reference_issues_uses_policy_extensions_for_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "external-reports" / "llm_wiki_review_report.md", "fake")
            _write(vault / "README.md", "See `llm_wiki_review_report.md` for details.\n")

            issues = external_report_reference_issues(
                vault,
                pages={},
                doc_audit_policy={"external_report_extensions": [".md"]},
            )
            warning = next(issue for issue in issues if issue["page"] == "README.md")

            self.assertEqual(warning["type"], "external_report_reference_mismatch")
            self.assertEqual(warning["detail"]["basename"], "llm_wiki_review_report.md")
            self.assertEqual(
                warning["detail"]["expected"],
                "external-reports/llm_wiki_review_report.md",
            )

    def test_external_report_reference_issues_accepts_precomputed_surfaces_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "external-reports" / "llm_wiki_review_report.pdf", "fake")
            readme = _write(vault / "README.md", "See `llm_wiki_review_report.pdf` for details.\n")
            page = _write(
                vault / "wiki" / "concept--fake.md",
                """# Concept

## Source trace
- `external-reports/llm_wiki_review_report.pdf`
""",
            )
            _write(vault / "raw" / "llm_wiki_review_report.pdf", "fake")

            issues = external_report_reference_issues(
                vault,
                pages={"concept--fake": page},
                relative_paths={"concept--fake": "wiki/custom-concept.md"},
                documentation_surfaces=[("docs/custom-readme.md", readme)],
            )

            documentation_issue = next(issue for issue in issues if issue["page"] == "docs/custom-readme.md")
            corpus_issue = next(issue for issue in issues if issue["page"] == "wiki/custom-concept.md")
            self.assertEqual(documentation_issue["type"], "external_report_reference_mismatch")
            self.assertEqual(corpus_issue["detail"]["expected"], "raw/llm_wiki_review_report.pdf")

    def test_external_report_reference_issues_for_ops_doc_using_raw_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "external-reports" / "llm_wiki_review_report.pdf", "fake")
            _write(vault / "raw" / "llm_wiki_review_report.pdf", "fake")
            _write(
                vault / "ops" / "evals" / "wiki-quality-evals.md",
                "- `raw/llm_wiki_review_report.pdf`\n",
            )

            issues = external_report_reference_issues(vault, pages={})
            warning = next(
                issue for issue in issues if issue["page"] == "ops/evals/wiki-quality-evals.md"
            )

            self.assertEqual(warning["type"], "external_report_reference_mismatch")
            self.assertEqual(
                warning["detail"]["context"],
                "documentation_surface_requires_external_reports_path",
            )
            self.assertEqual(warning["detail"]["found"], "raw/llm_wiki_review_report.pdf")
            self.assertEqual(
                warning["detail"]["expected"],
                "external-reports/llm_wiki_review_report.pdf",
            )

    def test_external_report_reference_issues_respects_explicit_empty_documentation_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "external-reports" / "llm_wiki_review_report.pdf", "fake")
            _write(vault / "README.md", "See `llm_wiki_review_report.pdf` for details.\n")

            issues = external_report_reference_issues(
                vault,
                pages={},
                documentation_surfaces=[],
            )

            self.assertEqual(issues, [])

    def test_external_report_reference_issues_for_source_trace_external_path_when_raw_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "external-reports" / "llm_wiki_review_report.pdf", "fake")
            _write(vault / "raw" / "llm_wiki_review_report.pdf", "fake")
            page = _write(
                vault / "wiki" / "concept--fake.md",
                """# Concept

## Source trace
- `external-reports/llm_wiki_review_report.pdf`
""",
            )

            issues = external_report_reference_issues(vault, pages={"concept--fake": page})
            warning = next(issue for issue in issues if issue["page"] == "wiki/concept--fake.md")

            self.assertEqual(warning["type"], "external_report_reference_mismatch")
            self.assertEqual(warning["detail"]["section"], "Source trace")
            self.assertEqual(warning["detail"]["expected"], "raw/llm_wiki_review_report.pdf")
            self.assertEqual(
                warning["detail"]["found"],
                "external-reports/llm_wiki_review_report.pdf",
            )

    def test_documentation_markdown_surfaces_discovers_root_ops_and_runs_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "README.md", "# Readme\n")
            _write(vault / "ops" / "guide.md", "# Guide\n")
            _write(vault / "runs" / "run-a" / "notes.md", "# Notes\n")
            _write(vault / "ops" / "ignored.txt", "skip\n")

            surfaces = documentation_markdown_surfaces(vault)

            self.assertEqual(
                [relative for relative, _ in surfaces],
                ["README.md", "ops/guide.md", "runs/run-a/notes.md"],
            )

    def test_documentation_markdown_surfaces_dedupes_by_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _write(vault / "README.md", "# Readme\n")
            _write(vault / "ops" / "duplicate.md", "# Duplicate ops\n")
            _write(vault / "runs" / "run-a" / "duplicate.md", "# Duplicate runs\n")

            with patch(
                "ops.scripts.eval.wiki_doc_audit_runtime.report_path",
                side_effect=lambda _vault, path: path.name,
            ):
                surfaces = documentation_markdown_surfaces(vault)

            self.assertEqual(
                [relative for relative, _ in surfaces],
                ["README.md", "duplicate.md"],
            )


if __name__ == "__main__":
    unittest.main()
