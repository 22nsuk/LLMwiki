from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ops.scripts.release.release_source_ready_commit import classify_path, main

LOCAL_GITIGNORE_TEXT = "\n".join(
    [
        "tmp/",
        "AGENTS.local.md",
        "external-reports/",
        "ops/manifest.json",
        "ops/operator/",
        "ops/raw-registry.json",
        "ops/reports/",
        "raw/",
        "runs/",
        "system/",
        "wiki/",
        "",
    ]
)


def _git(vault: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=vault,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


class ReleaseSourceReadyCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        _git(self.vault, "init", "-q")
        _git(self.vault, "config", "user.email", "release-source-ready@example.test")
        _git(self.vault, "config", "user.name", "Release Source Ready Test")
        (self.vault / ".gitignore").write_text(LOCAL_GITIGNORE_TEXT, encoding="utf-8")
        (self.vault / "README.md").write_text("# Test\n", encoding="utf-8")
        (self.vault / "ops").mkdir()
        (self.vault / "ops" / "script-output-surfaces.json").write_text("{}\n", encoding="utf-8")
        (self.vault / "ops" / "reports").mkdir(parents=True)
        (self.vault / "ops" / "reports" / "release-smoke-report.json").write_text(
            "{}\n", encoding="utf-8"
        )
        _git(self.vault, "add", ".")
        _git(self.vault, "commit", "-m", "initial")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_classifies_dot_prefixed_public_surface_paths_without_stripping_dot(self) -> None:
        self.assertEqual(classify_path(".gitignore"), "generated_canonical")
        self.assertEqual(classify_path(".github/workflows/ci.yml"), "public_source")
        self.assertEqual(classify_path("./.github/CODEOWNERS"), "public_source")
        self.assertEqual(classify_path("AGENTS.local.md"), "local_source_contract")
        self.assertEqual(classify_path("docs"), "public_source")
        self.assertEqual(classify_path("docs/development.md"), "public_source")
        self.assertEqual(classify_path("ops/manifest.json"), "local_only_private_inventory")
        self.assertEqual(classify_path("ops/raw-registry.json"), "local_only_private_inventory")
        self.assertEqual(classify_path("ops/operator/operator-release-summary.json"), "unexpected")
        self.assertEqual(classify_path("github/workflows/ci.yml"), "unexpected")

    def test_commits_public_source_and_tracked_generated_contract_together(self) -> None:
        (self.vault / "README.md").write_text("# Test\n\nChanged.\n", encoding="utf-8")
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass"}\n', encoding="utf-8"
        )
        (self.vault / "ops" / "scripts").mkdir(parents=True)
        (self.vault / "ops" / "scripts" / "new_helper.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 0)
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        changed_paths = _git(self.vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("README.md", changed_paths)
        self.assertIn("ops/script-output-surfaces.json", changed_paths)
        self.assertIn("ops/scripts/new_helper.py", changed_paths)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "committed")
        categories = {entry["path"]: entry["category"] for entry in report["entries"]}
        self.assertEqual(categories["README.md"], "public_source")
        self.assertEqual(categories["ops/script-output-surfaces.json"], "generated_canonical")

    def test_only_generated_canonical_commits_tracked_generated_contract(self) -> None:
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass"}\n',
            encoding="utf-8",
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: recover generated contract",
                "--only-generated-canonical",
            ]
        )

        self.assertEqual(rc, 0)
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        changed_paths = _git(self.vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("ops/script-output-surfaces.json", changed_paths)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "committed")
        categories = {entry["path"]: entry["category"] for entry in report["entries"]}
        self.assertEqual(categories["ops/script-output-surfaces.json"], "generated_canonical")

    def test_only_generated_canonical_refuses_source_changes(self) -> None:
        (self.vault / "README.md").write_text("# Test\n\nSource drift.\n", encoding="utf-8")
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass"}\n',
            encoding="utf-8",
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: recover generated contract",
                "--only-generated-canonical",
            ]
        )

        self.assertEqual(rc, 1)
        self.assertIn("README.md", _git(self.vault, "status", "--short"))
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "non_generated_dirty_paths")
        self.assertEqual(report["non_generated_paths"], ["README.md"])

    def test_report_summarizes_release_source_ready_diagnostics_without_changing_commit_policy(
        self,
    ) -> None:
        (self.vault / "README.md").write_text("# Test\n\nChanged.\n", encoding="utf-8")
        (self.vault / "tmp").mkdir()
        (self.vault / "tmp" / "goal-runtime-local-evidence-refresh.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "reason": "converged",
                    "digest_mode": "semantic_without_envelope_fingerprints_or_clock_fields",
                    "summary": {
                        "iteration_count": 4,
                        "command_count": 20,
                        "converged_iteration": 4,
                        "changed_path_count": 0,
                    },
                    "iterations": [
                        {
                            "iteration_index": 1,
                            "status": "changed",
                            "changed_paths": [
                                "runs/goal-test/state/auto-improve-readiness.json",
                                "runs/goal-test/state/session-synopsis.json",
                            ],
                        },
                        {
                            "iteration_index": 4,
                            "status": "pass",
                            "changed_paths": [],
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.vault / "ops" / "reports" / "release-closeout-summary.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "clean_release_ready": False,
                    "machine_release_allowed": False,
                    "release_authority_status": "conditional_pass",
                    "sealed_release_status": "unsealed_distribution_not_provided",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.vault / "ops" / "reports" / "artifact-freshness-report.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "currentness": {"status": "current"},
                    "source_tree_fingerprint": "abc123",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
                "--dry-run",
            ]
        )

        self.assertEqual(rc, 0)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        diagnostics = report["diagnostics"]
        goal_refresh = diagnostics["goal_runtime_local_evidence_refresh"]
        self.assertEqual(goal_refresh["status"], "pass")
        self.assertEqual(goal_refresh["summary"]["iteration_count"], 4)
        self.assertEqual(goal_refresh["iterations"][0]["changed_path_count"], 2)
        closeout = diagnostics["release_closeout_summary"]
        self.assertEqual(
            closeout["classification"],
            "source_release_checks_pass_distribution_unsealed",
        )
        self.assertFalse(closeout["machine_release_allowed"])
        self.assertIn("not a sealed machine release", closeout["operator_note"])
        freshness = diagnostics["artifact_freshness"]
        self.assertEqual(freshness["currentness_status"], "current")

    def test_rejects_unexpected_dirty_paths_before_staging(self) -> None:
        (self.vault / "private").mkdir()
        (self.vault / "private" / "secret.md").write_text("secret corpus\n", encoding="utf-8")

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 1)
        self.assertIn("?? private/", _git(self.vault, "status", "--short"))
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "unexpected_dirty_paths")
        self.assertEqual(report["unexpected_paths"], ["private"])

    def test_rejects_clean_tracked_ignored_local_only_inventory(self) -> None:
        (self.vault / "ops" / "raw-registry.json").write_text(
            '{"entries": []}\n',
            encoding="utf-8",
        )
        _git(self.vault, "add", "-f", "ops/raw-registry.json")
        _git(self.vault, "commit", "-m", "track ignored local inventory")

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 1)
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "tracked_ignored_local_only_inventory_paths")
        self.assertEqual(
            report["tracked_ignored_local_only_inventory_paths"],
            ["ops/raw-registry.json"],
        )

    def test_rejects_dirty_tracked_ignored_local_only_inventory(self) -> None:
        (self.vault / "ops" / "manifest.json").write_text(
            '{"files": []}\n',
            encoding="utf-8",
        )
        _git(self.vault, "add", "-f", "ops/manifest.json")
        _git(self.vault, "commit", "-m", "track ignored manifest")
        (self.vault / "ops" / "manifest.json").write_text(
            '{"files": ["changed"]}\n',
            encoding="utf-8",
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 1)
        self.assertIn("ops/manifest.json", _git(self.vault, "status", "--short"))
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "tracked_ignored_local_only_inventory_paths")
        self.assertEqual(
            report["tracked_ignored_local_only_inventory_paths"],
            ["ops/manifest.json"],
        )
        categories = {entry["path"]: entry["category"] for entry in report["entries"]}
        self.assertEqual(
            categories["ops/manifest.json"],
            "local_only_private_inventory",
        )

    def test_allows_ignored_external_reports_as_local_only_evidence(self) -> None:
        (self.vault / "external-reports").mkdir()
        (self.vault / "external-reports" / "private-new-review.md").write_text(
            "# Review\n",
            encoding="utf-8",
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 0)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "no_changes")
        self.assertEqual(report["entries"], [])
        self.assertIn("external-reports/", report["durable_private_ignored_status_prefixes"])

    def test_allows_ignored_external_report_archive_as_local_only_evidence(self) -> None:
        (self.vault / "external-reports" / "archive").mkdir(parents=True)
        (self.vault / "external-reports" / "report-reference-manifest.json").write_text(
            '{"references": []}\n',
            encoding="utf-8",
        )
        (self.vault / "external-reports" / "archive" / "closed-review.md").write_text(
            "# Closed Review\n",
            encoding="utf-8",
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 0)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "no_changes")
        self.assertEqual(report["entries"], [])
        self.assertIn(
            "external-reports/report-reference-manifest.json",
            report["local_only_retained_private_ignored_status_paths"],
        )
        self.assertIn(
            "external-reports/",
            report["local_only_retained_private_ignored_status_prefixes"],
        )
        self.assertIn("!! external-reports/", _git(self.vault, "status", "--short", "--ignored"))

    def test_rejects_preexisting_staged_changes_by_default(self) -> None:
        (self.vault / "README.md").write_text("# Test\n\nStaged.\n", encoding="utf-8")
        _git(self.vault, "add", "README.md")

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 1)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "preexisting_staged_changes")
        self.assertEqual(report["staged_paths"], ["README.md"])

    def test_allows_staged_external_reports_deindex_when_local_file_remains(self) -> None:
        (self.vault / ".gitignore").write_text(LOCAL_GITIGNORE_TEXT, encoding="utf-8")
        (self.vault / "external-reports" / "archive").mkdir(parents=True)
        archived_report = self.vault / "external-reports" / "archive" / "closed-review.md"
        archived_report.write_text("# Closed Review\n", encoding="utf-8")
        _git(self.vault, "add", "-f", ".gitignore", "external-reports/archive/closed-review.md")
        _git(self.vault, "commit", "-m", "track archived external report")
        _git(self.vault, "rm", "--cached", "external-reports/archive/closed-review.md")

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 0)
        self.assertTrue(archived_report.exists())
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        changed_paths = _git(self.vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("external-reports/archive/closed-review.md", changed_paths)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "committed")
        categories = {entry["path"]: entry["category"] for entry in report["entries"]}
        self.assertEqual(
            categories["external-reports/archive/closed-review.md"],
            "local_only_private_deindex",
        )

    def test_commits_deindex_with_public_and_generated_updates(self) -> None:
        (self.vault / ".gitignore").write_text(LOCAL_GITIGNORE_TEXT, encoding="utf-8")
        (self.vault / "external-reports" / "archive").mkdir(parents=True)
        archived_report = self.vault / "external-reports" / "archive" / "closed-review.md"
        archived_report.write_text("# Closed Review\n", encoding="utf-8")
        _git(self.vault, "add", "-f", ".gitignore", "external-reports/archive/closed-review.md")
        _git(self.vault, "commit", "-m", "track archived external report")
        _git(self.vault, "rm", "--cached", "external-reports/archive/closed-review.md")
        (self.vault / "README.md").write_text("# Test\n\nReady.\n", encoding="utf-8")
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass"}\n',
            encoding="utf-8",
        )

        rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(rc, 0)
        self.assertTrue(archived_report.exists())
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        changed_paths = _git(self.vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("README.md", changed_paths)
        self.assertIn("ops/script-output-surfaces.json", changed_paths)
        self.assertIn("external-reports/archive/closed-review.md", changed_paths)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        categories = {entry["path"]: entry["category"] for entry in report["entries"]}
        self.assertEqual(categories["README.md"], "public_source")
        self.assertEqual(categories["ops/script-output-surfaces.json"], "generated_canonical")
        self.assertEqual(
            categories["external-reports/archive/closed-review.md"],
            "local_only_private_deindex",
        )

    def test_commit_rejects_intervening_head_change_after_snapshot(self) -> None:
        snapshot_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-pre-status.json",
                "--snapshot-only",
            ]
        )
        snapshot_head = _git(self.vault, "rev-parse", "HEAD")
        (self.vault / "README.md").write_text("# Test\n\nIntervening.\n", encoding="utf-8")
        _git(self.vault, "add", "README.md")
        _git(self.vault, "commit", "-m", "intervening")
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass"}\n', encoding="utf-8"
        )

        commit_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--pre-status",
                "tmp/release-source-ready-pre-status.json",
                "--message",
                "release: ready",
            ]
        )

        self.assertEqual(snapshot_rc, 0)
        self.assertEqual(commit_rc, 1)
        self.assertIn("ops/script-output-surfaces.json", _git(self.vault, "status", "--short"))
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-commit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "snapshot_head_mismatch")
        self.assertEqual(report["expected_head_from_snapshot"], snapshot_head)
        self.assertEqual(report["actual_head_before_commit"], _git(self.vault, "rev-parse", "HEAD"))

    def test_amends_release_source_ready_commit_with_post_converge_evidence(self) -> None:
        initial_commit_count = int(_git(self.vault, "rev-list", "--count", "HEAD"))
        (self.vault / "README.md").write_text("# Test\n\nChanged.\n", encoding="utf-8")

        commit_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )
        first_head = _git(self.vault, "rev-parse", "HEAD")
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass", "phase": "post-converge"}\n',
            encoding="utf-8",
        )

        amend_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-amend.json",
                "--amend",
                "--amend-of",
                "tmp/release-source-ready-commit.json",
            ]
        )

        self.assertEqual(commit_rc, 0)
        self.assertEqual(amend_rc, 0)
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        self.assertEqual(int(_git(self.vault, "rev-list", "--count", "HEAD")), initial_commit_count + 1)
        self.assertNotEqual(_git(self.vault, "rev-parse", "HEAD"), first_head)
        self.assertEqual(_git(self.vault, "log", "-1", "--format=%s"), "release: ready")
        changed_paths = _git(self.vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("README.md", changed_paths)
        self.assertIn("ops/script-output-surfaces.json", changed_paths)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-amend.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "amended")
        self.assertTrue(report["amend"])
        self.assertEqual(report["expected_head_before_amend"], first_head)

    def test_allows_chained_final_guard_amend_after_post_converge_amend(self) -> None:
        initial_commit_count = int(_git(self.vault, "rev-list", "--count", "HEAD"))
        (self.vault / "README.md").write_text("# Test\n\nChanged.\n", encoding="utf-8")
        commit_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass", "phase": "post-converge"}\n',
            encoding="utf-8",
        )
        amend_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-amend.json",
                "--amend",
                "--amend-of",
                "tmp/release-source-ready-commit.json",
            ]
        )
        post_converge_head = _git(self.vault, "rev-parse", "HEAD")
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass", "phase": "final-generated-contract"}\n',
            encoding="utf-8",
        )

        final_guard_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-final-guard-amend.json",
                "--amend",
                "--amend-of",
                "tmp/release-source-ready-amend.json",
            ]
        )

        self.assertEqual(commit_rc, 0)
        self.assertEqual(amend_rc, 0)
        self.assertEqual(final_guard_rc, 0)
        self.assertEqual(_git(self.vault, "status", "--short"), "")
        self.assertEqual(int(_git(self.vault, "rev-list", "--count", "HEAD")), initial_commit_count + 1)
        self.assertNotEqual(_git(self.vault, "rev-parse", "HEAD"), post_converge_head)
        changed_paths = _git(self.vault, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn("README.md", changed_paths)
        self.assertIn("ops/script-output-surfaces.json", changed_paths)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-final-guard-amend.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["status"], "amended")
        self.assertEqual(report["amend_of_status"], "amended")
        self.assertEqual(report["expected_head_before_amend"], post_converge_head)

    def test_amend_rejects_intervening_head_change(self) -> None:
        (self.vault / "README.md").write_text("# Test\n\nChanged.\n", encoding="utf-8")
        commit_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )
        (self.vault / "README.md").write_text("# Test\n\nChanged again.\n", encoding="utf-8")
        _git(self.vault, "add", "README.md")
        _git(self.vault, "commit", "-m", "intervening")
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass", "phase": "post-converge"}\n',
            encoding="utf-8",
        )

        amend_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-amend.json",
                "--amend",
                "--amend-of",
                "tmp/release-source-ready-commit.json",
            ]
        )

        self.assertEqual(commit_rc, 0)
        self.assertEqual(amend_rc, 1)
        self.assertIn("ops/script-output-surfaces.json", _git(self.vault, "status", "--short"))
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-amend.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "amend_base_head_mismatch")

    def test_amend_rejects_late_public_source_changes(self) -> None:
        (self.vault / "README.md").write_text("# Test\n\nChanged.\n", encoding="utf-8")
        commit_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )
        (self.vault / "README.md").write_text("# Test\n\nChanged after commit.\n", encoding="utf-8")

        amend_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-amend.json",
                "--amend",
                "--amend-of",
                "tmp/release-source-ready-commit.json",
            ]
        )

        self.assertEqual(commit_rc, 0)
        self.assertEqual(amend_rc, 1)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-amend.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "amend_contains_public_source_changes")
        self.assertEqual(report["late_public_source_paths"], ["README.md"])

    def test_amend_noops_when_release_source_ready_commit_had_no_changes_and_tree_stays_clean(self) -> None:
        commit_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )

        amend_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-amend.json",
                "--amend",
                "--amend-of",
                "tmp/release-source-ready-commit.json",
            ]
        )

        self.assertEqual(commit_rc, 0)
        self.assertEqual(amend_rc, 0)
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-amend.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "no_changes")
        self.assertEqual(report["amend_of_status"], "no_changes")

    def test_amend_rejects_dirty_paths_when_release_source_ready_commit_had_no_changes(self) -> None:
        commit_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-commit.json",
                "--message",
                "release: ready",
            ]
        )
        (self.vault / "ops" / "script-output-surfaces.json").write_text(
            '{"status": "pass", "phase": "post-converge"}\n',
            encoding="utf-8",
        )

        amend_rc = main(
            [
                "--vault",
                str(self.vault),
                "--out",
                "tmp/release-source-ready-amend.json",
                "--amend",
                "--amend-of",
                "tmp/release-source-ready-commit.json",
            ]
        )

        self.assertEqual(commit_rc, 0)
        self.assertEqual(amend_rc, 1)
        self.assertIn("ops/script-output-surfaces.json", _git(self.vault, "status", "--short"))
        report = json.loads(
            (self.vault / "tmp" / "release-source-ready-amend.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "amend_base_not_committed")
        self.assertEqual(report["amend_of_status"], "no_changes")
        self.assertEqual(
            report["paths_after_uncommitted_base"],
            ["ops/script-output-surfaces.json"],
        )


if __name__ == "__main__":
    unittest.main()
